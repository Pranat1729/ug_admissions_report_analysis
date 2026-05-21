import re
import sqlite3
from datetime import datetime
from io import BytesIO
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

if not st.session_state.get("logged_in", False):
    st.warning("Please log in from the Home page.")
    st.stop()
 
#st.set_page_config(page_title="SQL + Filter Dashboard", layout="wide")

st.title("SQL + Filter Dashboard")
st.markdown(
    "Upload a CSV, then explore it with SQL queries or a block-style filter builder."
)

with st.sidebar:
    st.header("Upload dataset")
    uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])
    st.markdown("---")


@st.cache_data
def load_csv(file_bytes):
    return pd.read_csv(BytesIO(file_bytes))


@st.cache_data
def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if 'ADMIT_TERM_DESCR' in df.columns:
        extracted = df['ADMIT_TERM_DESCR'].astype(str).str.extract(r'(\d{4})\s+(Fall|Spring)')
        if extracted.shape[1] == 2:
            df['year'] = extracted[0]
            df['term'] = extracted[1]

    if 'enrolled' in df.columns:
        df['enrolled_flag'] = df['enrolled'].astype(str).str.upper() == 'Y'
    if 'matriculated' in df.columns:
        df['matriculated_flag'] = df['matriculated'].astype(str).str.upper() == 'Y'

    return df


@st.cache_data
def prepare_sql_df(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    mapping: Dict[str, str] = {}
    safe_names: List[str] = []

    for col in df.columns:
        safe = re.sub(r'\W+', '_', col.strip())
        if re.match(r'^\d', safe):
            safe = '_' + safe
        if not safe:
            safe = 'col'

        original_safe = safe
        i = 1
        while safe in safe_names:
            safe = f'{original_safe}_{i}'
            i += 1

        safe_names.append(safe)
        mapping[col] = safe

    sql_df = df.copy()
    sql_df.columns = [mapping[col] for col in df.columns]
    return sql_df, mapping


def run_sql_query(df: pd.DataFrame, query: str) -> pd.DataFrame:
    conn = sqlite3.connect(':memory:')
    df.to_sql('data', conn, index=False, if_exists='replace')
    result = pd.read_sql_query(query, conn)
    conn.close()
    return result


def translate_expression_to_sql(expr: str, mapping: Dict[str, str]) -> str:
    sql_expr = expr
    for original, safe in sorted(mapping.items(), key=lambda item: -len(item[0])):
        pattern = r'(?<!\w)' + re.escape(original) + r'(?!\w)'
        sql_expr = re.sub(pattern, safe, sql_expr)
    return sql_expr


def build_filter_panel(df: pd.DataFrame, sql_mapping: Dict[str, str]) -> Tuple[pd.DataFrame, str]:
    st.write('Add filters block-by-block to narrow the dataset.')
    filtered = df.copy()
    filter_columns = st.multiselect('Select columns to filter', df.columns.tolist())
    query_fragments: List[str] = []
    sql_fragments: List[str] = []

    for col in filter_columns:
        series = df[col]

        if pd.api.types.is_numeric_dtype(series):
            min_val, max_val = float(series.min()), float(series.max())
            if min_val == max_val:
                st.write(f'**{col}** has a constant value: {min_val}')
                continue
            selected_range = st.slider(
                f'{col} range', min_val, max_val, (min_val, max_val)
            )
            if selected_range[0] != min_val or selected_range[1] != max_val:
                query_fragments.append(
                    f'({col} >= {selected_range[0]} and {col} <= {selected_range[1]})'
                )

        elif pd.api.types.is_datetime64_any_dtype(series):
            values = series.dropna()
            if not values.empty:
                start, end = st.date_input(
                    f'{col} range', [values.min().date(), values.max().date()]
                )
                if len(start) == 2:
                    query_fragments.append(
                        f'({col} >= "{start[0]}" and {col} <= "{start[1]}")'
                    )

        else:
            unique_values = series.dropna().astype(str).unique().tolist()
            unique_values = sorted(unique_values)[:100]
            selected_values = st.multiselect(
                f'{col} values', unique_values, default=unique_values[:5]
            )
            if selected_values and len(selected_values) < len(unique_values):
                safe_values = [v.replace('"', '""') for v in selected_values]
                quoted = [f'"{v}"' for v in safe_values]
                query_fragments.append(f'{col} in ({", ".join(quoted)})')

    custom_expr = st.text_input(
        'Advanced expression (optional)',
        placeholder='e.g. year == "2022" and enrolled == "Y"'
    )
    if custom_expr:
        query_fragments.append(custom_expr)
        sql_fragments.append(translate_expression_to_sql(custom_expr, sql_mapping))

    if query_fragments:
        combined = ' and '.join(query_fragments)
        try:
            filtered = filtered.query(combined, engine='python')
            st.success(f'Filtered to {len(filtered):,} rows')
        except Exception as exc:
            st.error(f'Filter error: {exc}')
            st.write('Filter expression used:', combined)
    else:
        st.info('No filters applied. Showing full dataset.')

    if sql_fragments:
        sql_where = ' and '.join(sql_fragments)
        sql_query = f'SELECT * FROM data WHERE {sql_where}'
    else:
        sql_query = 'SELECT * FROM data'

    return filtered, sql_query
def render_insights(df: pd.DataFrame, title: str = 'Insights') -> None:
    st.markdown(f'### {title}')
    if df.empty:
        st.info('No rows available to generate insights.')
        return

    st.write(f'*Rows: {len(df):,}*  \n*Columns: {len(df.columns)}*')

    ignored_columns = {col for col in df.columns if col.upper() == 'EMPLID'}
    analysis_columns = [col for col in df.columns if col not in ignored_columns]
    numeric_cols = [c for c in analysis_columns if pd.api.types.is_numeric_dtype(df[c])]

    if numeric_cols:
        num_metrics = df[numeric_cols].describe().transpose()
        st.subheader('Numeric summary')
        st.dataframe(num_metrics, use_container_width=True)
    else:
        st.info('No numeric columns found for summary.')


if uploaded_file is None:
    st.sidebar.warning('Upload a CSV to begin exploring your data.')
    st.warning('Please upload a CSV file in the sidebar.')
    st.stop()

raw_df = load_csv(uploaded_file.read())
df = preprocess(raw_df)
sql_df, sql_mapping = prepare_sql_df(df)

if 'saved_queries' not in st.session_state:
    st.session_state['saved_queries'] = []
if 'saved_block_queries' not in st.session_state:
    st.session_state['saved_block_queries'] = []
if 'sql_query_text' not in st.session_state:
    st.session_state['sql_query_text'] = 'SELECT * FROM data LIMIT 100'

tabs = st.tabs(['SQL Query', 'Block Filtering', 'Data Preview'])

with tabs[0]:
    st.subheader('SQL Query')
    st.markdown(
        'Query the uploaded data using raw SQL. The table name is `data`.'
    )

    mapping_table = pd.DataFrame(
        {'Original column': list(sql_mapping.keys()), 'SQL column': list(sql_mapping.values())}
    )
    with st.expander('Column mapping for SQL'):
        st.dataframe(mapping_table, use_container_width=True)

    query_text = st.text_area(
        'SQL query',
        value=st.session_state['sql_query_text'],
        height=180,
        key='sql_query_text',
    )

    st.markdown('### Saved queries')
    with st.expander('Manage saved SQL queries', expanded=True):
        if st.session_state['saved_queries']:
            saved_labels = [
                f"{q['name']} — {q['timestamp']}"
                for q in st.session_state['saved_queries']
            ]
            selected_saved = st.selectbox('Load a saved query', ['', *saved_labels])

            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button('Load saved query') and selected_saved:
                    index = saved_labels.index(selected_saved)
                    st.session_state['sql_query_text'] = st.session_state['saved_queries'][index]['query']
                    st.experimental_rerun()
            with col2:
                if st.button('Delete selected query') and selected_saved:
                    index = saved_labels.index(selected_saved)
                    st.session_state['saved_queries'].pop(index)
                    st.success('Saved query deleted.')
                    st.experimental_rerun()

            st.write('Saved query list:')
            for item in st.session_state['saved_queries']:
                st.write(f"- **{item['name']}** — {item['timestamp']}")
        else:
            st.info('No saved queries yet.')

        save_name = st.text_input('Save current query as', placeholder='Enter a friendly name')
        if st.button('Save current query'):
            if query_text.strip():
                label = save_name.strip() or f'Saved query {len(st.session_state["saved_queries"]) + 1}'
                st.session_state['saved_queries'].insert(
                    0,
                    {
                        'name': label,
                        'query': query_text.strip(),
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    },
                )
                st.success(f'Query saved as "{label}"')
                
            else:
                st.error('Cannot save an empty query.')

    if st.button('Run SQL query'):
        try:
            result_df = run_sql_query(sql_df, query_text)
            st.success(f'Query returned {len(result_df):,} rows')
            st.dataframe(result_df, use_container_width=True)
            render_insights(result_df, title='SQL result insights')
            csv = result_df.to_csv(index=False)
            st.download_button(
                'Download SQL result as CSV',
                data=csv,
                file_name='sql_query_results.csv',
                mime='text/csv',
            )
        except Exception as exc:
            st.error(f'SQL error: {exc}')
            st.code(query_text, language='sql')

with tabs[1]:
    st.subheader('Block Filtering')
    filtered_df, block_sql = build_filter_panel(df, sql_mapping)

    st.markdown('### SQL preview for this block query')
    st.code(block_sql, language='sql')
    st.divider()
    st.dataframe(filtered_df, use_container_width=True)
    render_insights(filtered_df, title='Filtered subset insights')

    st.markdown('### Saved block queries')
    if st.session_state['saved_block_queries']:
        saved_labels = [
            f"{q['name']} — {q['timestamp']}"
            for q in st.session_state['saved_block_queries']
        ]
        selected_saved = st.selectbox('Load a saved block query', ['', *saved_labels], key='load_saved_block_query')

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button('Run saved block query', key='run_saved_block_query') and selected_saved:
                index = saved_labels.index(selected_saved)
                saved_query = st.session_state['saved_block_queries'][index]['query']
                try:
                    saved_result = run_sql_query(sql_df, saved_query)
                    st.success(f'Saved block query returned {len(saved_result):,} rows')
                    st.dataframe(saved_result, use_container_width=True)
                    render_insights(saved_result, title='Saved block query insights')
                    csv = saved_result.to_csv(index=False)
                    st.download_button(
                        'Download saved block query result as CSV',
                        data=csv,
                        file_name='saved_block_query_results.csv',
                        mime='text/csv',
                    )
                except Exception as exc:
                    st.error(f'SQL error: {exc}')
                    st.code(saved_query, language='sql')
        with col2:
            if st.button('Delete selected block query', key='delete_saved_block_query') and selected_saved:
                index = saved_labels.index(selected_saved)
                st.session_state['saved_block_queries'].pop(index)
                st.success('Saved block query deleted.')
                st.experimental_rerun()

        st.write('Saved block query list:')
        for item in st.session_state['saved_block_queries']:
            st.write(f"- **{item['name']}** — {item['timestamp']}")
    else:
        st.info('No saved block queries yet.')

    save_name = st.text_input('Save current block query as', key='save_block_query_name')
    if st.button('Save current block query', key='save_block_query'):
        if block_sql.strip():
            label = save_name.strip() or f'Block query {len(st.session_state['saved_block_queries']) + 1}'
            st.session_state['saved_block_queries'].insert(
                0,
                {
                    'name': label,
                    'query': block_sql,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                },
            )
            st.success(f'Block query saved as "{label}"')
        else:
            st.error('Cannot save an empty block query.')

    if not filtered_df.empty:
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            'Download filtered result as CSV',
            data=csv,
            file_name='filtered_data.csv',
            mime='text/csv',
        )

with tabs[2]:
    st.subheader('Data Preview')
    st.markdown(f'*Rows: {len(df):,}*  \n*Columns: {len(df.columns)}*')
    st.dataframe(df.head(200), use_container_width=True)
    st.markdown('**Columns**')
    st.write(list(df.columns))

    if st.checkbox('Show summary statistics'):
        st.write(df.describe(include='all').transpose())
