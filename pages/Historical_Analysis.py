import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import hashlib
from io import BytesIO

if not st.session_state.get("logged_in", False):
    st.warning("Please log in from the Home page.")
    st.stop()
    
st.set_page_config(
    page_title="High School Recruitment Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

with st.sidebar:
    st.header("Dataset Upload")
    uploaded_file = st.file_uploader("Upload your CSV", type=["csv"])
    st.markdown("---")
    st.caption("Upload the dataset to refresh the dashboard.")

@st.cache_data
def load(file_hash, file_bytes):
    return pd.read_csv(BytesIO(file_bytes))

if uploaded_file is not None:
    uploaded_bytes = uploaded_file.read()
    file_hash = hashlib.md5(uploaded_bytes).hexdigest()
    df = load(file_hash, uploaded_bytes)
    uploaded_file.seek(0)
else:
    st.sidebar.warning("Please upload a CSV file to proceed.")
    st.title("High School Recruitment Analytics")
    st.warning("Please upload a CSV file using the sidebar to see the dashboard.")
    st.stop()

@st.cache_data
def metrics(df):
    # Parse ADMIT_TERM_DESCR to extract year and term
    df[['year', 'term']] = df['ADMIT_TERM_DESCR'].str.extract(r'(\d{4})\s+(Fall|Spring)')
    
    # Dataset 1: Per HS per year (spring + fall combined)
    yearly_metrics = df.groupby(['HS_Name', 'year']).agg(
        admitted_count=('EMPLID', 'count'),
        enrolled_count=('enrolled', lambda x: (x == 'Y').sum()),
        matriculated_count=('matriculated', lambda x: (x == 'Y').sum()),
    ).reset_index()
    
    yearly_metrics['yield'] = yearly_metrics['enrolled_count'] / yearly_metrics['admitted_count']
    yearly_metrics['drip'] = yearly_metrics['matriculated_count'] / yearly_metrics['admitted_count']
    
    # Dataset 2: Term-by-term data
    term_data = df.groupby(['HS_Name', 'year', 'term']).agg(
        admitted_count=('EMPLID', 'count'),
        enrolled_count=('enrolled', lambda x: (x == 'Y').sum()),
        matriculated_count=('matriculated', lambda x: (x == 'Y').sum()),
    ).reset_index()
    
    term_data['yield'] = term_data['enrolled_count'] / term_data['admitted_count']
    term_data['drip'] = term_data['matriculated_count'] / term_data['admitted_count']
    
    # Add semesters_lost (assuming 2 semesters per year from admit year to 2026)
    term_data['semesters_lost'] = (2026 - term_data['year'].astype(int)) * 2
    
    # Money lost per term with 30% yield cap
    term_data['money_lost'] = (term_data['admitted_count'] - term_data['enrolled_count']) * 3465 * 0.3 * term_data['semesters_lost']
    
    # Dataset 3: Overall summary (4-year totals + averaged metrics)
    overall_summary = df.groupby('HS_Name').agg(
        total_admitted=('EMPLID', 'count'),
        total_enrolled=('enrolled', lambda x: (x == 'Y').sum()),
        total_matriculated=('matriculated', lambda x: (x == 'Y').sum()),
    ).reset_index()
    
    # Average metrics over the years
    avg_metrics = yearly_metrics.groupby('HS_Name')[['yield', 'drip']].mean().reset_index()
    avg_metrics.columns = ['HS_Name', 'avg_yield', 'avg_drip']
    
    overall_summary = overall_summary.merge(avg_metrics, on='HS_Name')
    
    # Add total money lost per HS
    money_lost_per_hs = term_data.groupby('HS_Name')['money_lost'].sum().reset_index()
    overall_summary = overall_summary.merge(money_lost_per_hs, on='HS_Name')

    # Proxy classification using volume + matriculation quality
    overall_summary['avg_matriculation_rate'] = overall_summary['total_matriculated'] / overall_summary['total_admitted']

    vol_thresh = 30
    quality_thresh = 0.20

    def classify_school(row):
        high_volume = row["total_admitted"] >= vol_thresh
        high_quality = row["avg_matriculation_rate"] >= quality_thresh

        if high_volume and high_quality:
            return "Flagship"
        elif not high_volume and high_quality:
            return "Fringe Gem"
        elif high_volume and not high_quality:
            return "Over-recruited"
        else:
            return "Low Priority"

    def heat_label(row):
        lost = row['money_lost']
        if lost > 10_000_000:
            return 'Extra Hot'
        elif lost > 5_000_000:
            return 'Hot'
        elif lost > 1_000_000:
            return 'Mild'
        else:
            return 'Cold'

    overall_summary["Recruitment_Category"] = overall_summary.apply(classify_school, axis=1)
    overall_summary["Heat_Label"] = overall_summary.apply(heat_label, axis=1)
    
    # Save to CSV
    term_data.to_csv('hs_metrics_by_term.csv', index=False)
    overall_summary.to_csv('hs_metrics_overall.csv', index=False)
    
    print("CSV files created:")
    print("1. hs_metrics_by_term.csv - Yearly data with term breakdown")
    print("2. hs_metrics_overall.csv - Averaged metrics by HS (no term info)")
    
    return overall_summary, term_data

@st.cache_data
def compute_preference_ranking(df):
    choice_cols = [f'Choice{i}' for i in range(1, 7) if f'Choice{i}' in df.columns]
    if not choice_cols:
        choice_cols = [f'choice{i}' for i in range(1, 7) if f'choice{i}' in df.columns]
    if not choice_cols:
        return None

    weights = {col: 7 - int(col.replace('Choice', '').replace('choice', '')) for col in choice_cols}
    weighted_scores = {}

    for col in choice_cols:
        counts = df[col].fillna('').astype(str).replace({'nan': ''}).value_counts()
        for college, count in counts.items():
            if college == '':
                continue
            weighted_scores[college] = weighted_scores.get(college, 0) + count * weights[col]

    ranking = pd.Series(weighted_scores).sort_values(ascending=False).reset_index()
    ranking.columns = ['college', 'weighted_score']
    return ranking

@st.cache_data
def compute_preference_ranking_by_hs(df, hs_name):
    if 'HS_Name' not in df.columns:
        return None
    hs_df = df[df['HS_Name'] == hs_name]
    if hs_df.empty:
        return None
    return compute_preference_ranking(hs_df)

overall_summary, term_data = metrics(df)

st.title("High School Recruitment Analytics")
st.markdown("A dashboard for high school admissions, enrollment, and preference analysis.")

st.header("Key Metrics")
total_hs = overall_summary['HS_Name'].nunique()
total_admitted = overall_summary['total_admitted'].sum()
total_enrolled = overall_summary['total_enrolled'].sum()
total_matriculated = overall_summary['total_matriculated'].sum()
overall_yield = total_enrolled / total_admitted if total_admitted else np.nan
overall_matric_rate = total_matriculated / total_admitted if total_admitted else np.nan

col1, col2, col3, col4 = st.columns(4)
col1.metric('High schools', f'{total_hs}')
col2.metric('Total admitted', f'{total_admitted:,}')
col3.metric('Total enrolled', f'{total_enrolled:,}')
col4.metric('Total matriculated', f'{total_matriculated:,}')

col5, col6 = st.columns(2)
col5.metric('Overall enrollment yield', f'{overall_yield:.1%}')
col6.metric('Overall matriculation rate', f'{overall_matric_rate:.1%}')

st.divider()

tab_overview, tab_trends, tab_recruit, tab_preferences, tab_details = st.tabs([
    'Overview',
    'Trend analysis',
    'Recruitment',
    'Preferences',
    'Student details'
])

with tab_overview:
    st.subheader('Overall summary by high school')
    st.write('High-level summary of admitted, enrolled, and matriculated students by high school.')
    st.dataframe(overall_summary, use_container_width=True)

    st.subheader('Term-by-term metrics')
    st.write('Enrollment and matriculation counts broken down by school, year, and term.')
    st.dataframe(term_data, use_container_width=True)

with tab_trends:
    st.subheader('Enrollment trends by high school')
    hs_names = sorted(overall_summary['HS_Name'].dropna().unique())
    selected_hs_trends = st.selectbox('Select high school for trend analysis', hs_names)
    hs_term_data = term_data[term_data['HS_Name'] == selected_hs_trends].copy()
    if hs_term_data.empty:
        st.warning(f'No term data available for {selected_hs_trends}.')
    else:
        hs_term_data['year'] = pd.to_numeric(hs_term_data['year'], errors='coerce')
        hs_term_data = hs_term_data.sort_values(['year', 'term'])
        trend_chart = alt.Chart(hs_term_data).mark_line(point=True).encode(
            x=alt.X('year:O', title='Year'),
            y=alt.Y('enrolled_count:Q', title='Enrolled count'),
            color=alt.Color('term:N', title='Term'),
            tooltip=['year:O', 'term:N', 'enrolled_count:Q']
        ).properties(width=800, height=420)
        st.altair_chart(trend_chart, use_container_width=True)

with tab_recruit:
    st.subheader('Recruitment and money loss')
    heat_data = overall_summary[['HS_Name', 'money_lost', 'Heat_Label']].copy()
    heat_data = heat_data[heat_data['Heat_Label'] == 'Hot'].sort_values('money_lost', ascending=False)
    category_data = overall_summary.groupby('Recruitment_Category')['money_lost'].sum().reset_index()
    category_stats = overall_summary.groupby('Recruitment_Category').agg(
        total_money_lost=('money_lost', 'sum'),
        schools_in_category=('HS_Name', 'count'),
        total_admitted=('total_admitted', 'sum')
    ).reset_index()
    category_stats['avg_money_lost_per_school'] = category_stats['total_money_lost'] / category_stats['schools_in_category']
    category_stats['avg_money_lost_per_admitted'] = category_stats['total_money_lost'] / category_stats['total_admitted']

    st.markdown('### Heat map and recruitment category')
    col1, col2 = st.columns(2)
    with col1:
        st.write('Hot schools by lost money')
        if heat_data.empty:
            st.warning('No schools labeled "Hot" were found in the current dataset.')
        else:
            heat_chart = alt.Chart(heat_data).mark_bar().encode(
                x=alt.X('money_lost:Q', title='Money lost ($)'),
                y=alt.Y('HS_Name:N', sort='-x', title='High school'),
                tooltip=['HS_Name:N', 'money_lost:Q']
            ).properties(width=700, height=420)
            st.altair_chart(heat_chart, use_container_width=True)

    with col2:
        st.write('Money lost by recruitment category')
        category_chart = alt.Chart(category_data).mark_bar().encode(
            x=alt.X('Recruitment_Category:N', title='Recruitment category'),
            y=alt.Y('money_lost:Q', title='Total money lost ($)'),
            color=alt.Color('Recruitment_Category:N', legend=None),
            tooltip=['Recruitment_Category:N', 'money_lost:Q']
        ).properties(width=700, height=420)
        st.altair_chart(category_chart, use_container_width=True)

    st.markdown('### Recruitment category breakdown')
    st.dataframe(category_stats, use_container_width=True)
    avg_category_chart = alt.Chart(category_stats).mark_bar().encode(
        x=alt.X('Recruitment_Category:N', title='Recruitment category'),
        y=alt.Y('avg_money_lost_per_school:Q', title='Average money lost per school ($)'),
        color=alt.Color('Recruitment_Category:N', legend=None),
        tooltip=['Recruitment_Category:N', 'avg_money_lost_per_school:Q']
    ).properties(width=900, height=420)
    st.altair_chart(avg_category_chart, use_container_width=True)

with tab_preferences:
    st.subheader('CUNY preference ranking')
    preference_ranking = compute_preference_ranking(df)
    if preference_ranking is None or preference_ranking.empty:
        st.warning('No choice1-6 columns found in the uploaded dataset.')
    else:
        pref_chart = alt.Chart(preference_ranking).mark_bar().encode(
            x=alt.X('weighted_score:Q', title='Weighted preference score'),
            y=alt.Y('college:N', sort='-x', title='College'),
            tooltip=['college:N', 'weighted_score:Q']
        ).properties(width=900, height=520)
        st.altair_chart(pref_chart, use_container_width=True)
        st.dataframe(preference_ranking, use_container_width=True)

    st.markdown('### School-specific preference ranking')
    if 'HS_Name' not in df.columns:
        st.warning('No HS_Name column present to filter by high school.')
    else:
        hs_names = sorted(df['HS_Name'].dropna().unique())
        selected_hs = st.selectbox('Select a high school for preference ranking', hs_names)
        hs_ranking = compute_preference_ranking_by_hs(df, selected_hs)
        if hs_ranking is None or hs_ranking.empty:
            st.warning(f'No preference data available for {selected_hs}.')
        else:
            hs_chart = alt.Chart(hs_ranking).mark_bar().encode(
                x=alt.X('weighted_score:Q', title='Weighted preference score'),
                y=alt.Y('college:N', sort='-x', title='College'),
                tooltip=['college:N', 'weighted_score:Q']
            ).properties(width=900, height=520)
            st.altair_chart(hs_chart, use_container_width=True)
            st.dataframe(hs_ranking, use_container_width=True)

with tab_details:
    st.subheader('Ethnicity distribution per high school')
    if 'HS_Name' not in df.columns:
        st.warning('No HS_Name column present to filter ethnicity by high school.')
    else:
        hs_names = sorted(df['HS_Name'].dropna().unique())
        selected_eth_hs = st.selectbox('Select high school for ethnicity distribution', hs_names)
        ethnicity_data_hs = df[(df['enrolled'] == 'Y') & (df['HS_Name'] == selected_eth_hs)]
        if ethnicity_data_hs.empty:
            st.warning(f'No enrolled students found for {selected_eth_hs}.')
        else:
            ethnicity_counts = ethnicity_data_hs.groupby('ethnicity').size().reset_index(name='count')
            ethnicity_chart = alt.Chart(ethnicity_counts).mark_bar().encode(
                x=alt.X('ethnicity:N', title='Ethnicity'),
                y=alt.Y('count:Q', title='Enrolled student count'),
                tooltip=['ethnicity:N', 'count:Q']
            ).properties(width=900, height=420)
            st.altair_chart(ethnicity_chart, use_container_width=True)
            st.dataframe(ethnicity_counts, use_container_width=True)

    st.markdown('### Lost students: first choice vs intended ACAD_PLAN')
    if 'HS_Name' not in df.columns:
        st.warning('No HS_Name column present to filter lost-student analysis.')
    else:
        hs_names = sorted(df['HS_Name'].dropna().unique())
        selected_hs_lost = st.selectbox(
            'Select high school for lost student analysis',
            hs_names,
            index=hs_names.index('BKL01') if 'BKL01' in hs_names else 0
        )
        lost_df = df[(df['enrolled'] == 'N') & (df['HS_Name'] == selected_hs_lost)]
        if lost_df.empty:
            st.warning(f'No lost students found for {selected_hs_lost}.')
        else:
            first_choice_col = 'Choice1' if 'Choice1' in df.columns else 'choice1' if 'choice1' in df.columns else None
            major_col = 'ACAD_PLAN' if 'ACAD_PLAN' in df.columns else None
            if first_choice_col is None:
                st.warning('First choice column not found (expected Choice1 or choice1).')
            elif major_col is None:
                st.warning('Major column not found (expected ACAD_PLAN).')
            else:
                lost_df = lost_df.copy()
                lost_df[first_choice_col] = lost_df[first_choice_col].fillna('Unknown')
                lost_df[major_col] = lost_df[major_col].fillna('Unknown')

                lost_choice_major = (
                    lost_df.groupby([first_choice_col, major_col])
                    .size()
                    .reset_index(name='lost_count')
                )

                top_choices = (
                    lost_choice_major.groupby(first_choice_col)['lost_count']
                    .sum()
                    .reset_index()
                    .sort_values('lost_count', ascending=False)
                    .head(20)
                )
                top_choice_list = top_choices[first_choice_col].tolist()
                plot_data = lost_choice_major[lost_choice_major[first_choice_col].isin(top_choice_list)]

                summary_chart = alt.Chart(plot_data).mark_bar().encode(
                    x=alt.X('lost_count:Q', title='Lost student count'),
                    y=alt.Y(f'{first_choice_col}:N', sort='-x', title='First choice school'),
                    color=alt.Color(f'{major_col}:N', title='Intended ACAD_PLAN'),
                    tooltip=[f'{first_choice_col}:N', f'{major_col}:N', 'lost_count:Q']
                ).properties(width=900, height=520)
                st.altair_chart(summary_chart, use_container_width=True)

                summary_table = (
                    plot_data
                    .sort_values('lost_count', ascending=False)
                    .rename(columns={
                        first_choice_col: 'First choice school',
                        major_col: 'Intended ACAD_PLAN',
                        'lost_count': 'Lost student count'
                    })
                )
                st.dataframe(summary_table, use_container_width=True)
