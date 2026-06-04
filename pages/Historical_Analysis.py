import re
import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import hashlib
from io import BytesIO

#if not st.session_state.get("logged_in", False):
#    st.warning("Please log in from the Home page.")
#    st.stop()
    
st.set_page_config(
    page_title="High School Recruitment Analytics",
    layout="wide",
    initial_sidebar_state="expanded"
)

with st.sidebar:
    st.header("Dataset Upload")
    uploaded_file = st.file_uploader("Upload your CSV", type=["csv"], key="csv_upload")
    dataset_type = st.selectbox(
        "Dataset type",
        ["Freshmen", "Transfer"],
        index=0 if st.session_state.get("dataset_type", "Freshmen") == "Freshmen" else 1,
        key="dataset_type",
        help="Choose which dataset format to load so the app can map fields consistently."
    )
    if st.session_state.get("uploaded_file_name"):
        st.markdown(f"**Current dataset:** {st.session_state['uploaded_file_name']}")
    if st.button("Clear uploaded dataset", key="clear_dataset"):
        for key in ["uploaded_file_bytes", "uploaded_file_name", "dataset_type", "uploaded_file_hash"]:
            if key in st.session_state:
                del st.session_state[key]
        st.experimental_rerun()
    st.markdown("---")
    st.caption("Upload the dataset to refresh the dashboard.")

@st.cache_data
def extract_year(value):
    if pd.isna(value):
        return np.nan
    match = re.search(r'(\d{4})', str(value))
    return match.group(1) if match else np.nan


def extract_term(value):
    if pd.isna(value):
        return np.nan
    match = re.search(r'(Fall|Spring)', str(value), flags=re.IGNORECASE)
    return match.group(1).title() if match else np.nan


def normalize_dataset(df, dataset_type):
    column_mapping = {
        'ADMIT_TERM_DESCR': [
            'ADMIT_TERM_DESCR', 'ADMIT_TERM', 'TERM_DESC', 'Admit Term Description',
            'admit_term_descr', 'AdmitTermDescr', 'TERM_DESCRIPTION'
        ],
        'EMPLID': [
            'EMPLID', 'STUDENT_ID', 'Student_ID', 'Student ID', 'SID', 'STUDENT NUMBER',
            'STUDENT_NUMBER'
        ],
        'enrolled': [
            'enrolled', 'ENROLLED', 'enrolled_flag', 'Enrolled', 'ENROLLMENT_STATUS',
            'Enroll', 'ENROLL_STATUS'
        ],
        'matriculated': [
            'matriculated', 'MATRICULATED', 'matriculated_flag', 'Matriculated',
            'MATRICULATION_STATUS', 'Matriculation'
        ],
        'HS_Name': [
            'HS_Name', 'HS_NAME', 'HS Name', 'High School', 'high_school_name',
            'High_School', 'high_school', 'HighSchool'
        ],
        'ethnicity': [
            'ethnicity', 'ETHNICITY', 'Ethnicity', 'Ethnic_Group', 'ethnic_group'
        ],
        'ACAD_PLAN': [
            'ACAD_PLAN', 'Acad_Plan', 'ACAD PLAN', 'INTENDED_MAJOR', 'Intended_Major',
            'intended_major', 'Major', 'Intended Major'
        ]
    }

    if dataset_type == 'Transfer':
        column_mapping['HS_Name'] += ['Current_HS', 'School_Name']
        column_mapping['enrolled'] += ['Admit_Status', 'Enrollment_Status']
        column_mapping['matriculated'] += ['Matriculation_Status', 'Matric_Status']
        column_mapping['ADMIT_TERM_DESCR'] += ['AdmitTerm', 'Term']

    rename_map = {}
    for standard_name, alternatives in column_mapping.items():
        for alt_name in alternatives:
            if alt_name in df.columns:
                rename_map[alt_name] = standard_name
                break

    df = df.rename(columns=rename_map)

    for i in range(1, 7):
        for alt_name in [
            f'Choice{i}', f'choice{i}', f'CHOICE{i}',
            f'choice_{i}', f'Choice_{i}', f'choice {i}', f'Choice {i}',
            f'C{i}', f'Pref{i}', f'pref{i}'
        ]:
            if alt_name in df.columns:
                df = df.rename(columns={alt_name: f'Choice{i}'})
                break

    if dataset_type == 'Transfer' and 'HS_Name' not in df.columns:
        if 'LAST_COL_UGRD_DESCR' in df.columns:
            df['HS_Name'] = df['LAST_COL_UGRD_DESCR']
        elif 'LAST_COL_UGRD_SYS' in df.columns:
            df['HS_Name'] = df['LAST_COL_UGRD_SYS']
        elif 'Coll_City' in df.columns:
            df['HS_Name'] = df['Coll_City']
        else:
            df['HS_Name'] = 'Unknown'

    if 'enrolled' in df.columns:
        df['enrolled'] = df['enrolled'].astype(str).str.strip().str.upper().replace(
            {
                'YES': 'Y', 'YEA': 'Y', 'Y': 'Y', '1': 'Y', 'TRUE': 'Y', 'T': 'Y',
                'NO': 'N', 'N': 'N', '0': 'N', 'FALSE': 'N', 'F': 'N'
            }
        )

    if 'matriculated' in df.columns:
        df['matriculated'] = df['matriculated'].astype(str).str.strip().str.upper().replace(
            {
                'YES': 'Y', 'YEA': 'Y', 'Y': 'Y', '1': 'Y', 'TRUE': 'Y', 'T': 'Y',
                'NO': 'N', 'N': 'N', '0': 'N', 'FALSE': 'N', 'F': 'N'
            }
        )

    return df

@st.cache_data
def load(file_hash, file_bytes, dataset_type):
    df = pd.read_csv(BytesIO(file_bytes))
    return normalize_dataset(df, dataset_type)

uploaded_bytes = None
if uploaded_file is not None:
    uploaded_bytes = uploaded_file.read()
    st.session_state["uploaded_file_bytes"] = uploaded_bytes
    st.session_state["uploaded_file_name"] = uploaded_file.name
    st.session_state["dataset_type"] = dataset_type
elif st.session_state.get("uploaded_file_bytes") is not None:
    uploaded_bytes = st.session_state["uploaded_file_bytes"]
    dataset_type = st.session_state.get("dataset_type", dataset_type)
    st.sidebar.success(f"Loaded dataset: {st.session_state.get('uploaded_file_name', 'uploaded dataset')}")
    st.sidebar.write(f"Using saved dataset type: **{dataset_type}**")

if uploaded_bytes is not None:
    file_hash = hashlib.md5(uploaded_bytes).hexdigest()
    df = load(file_hash, uploaded_bytes, dataset_type)
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
    st.subheader('Application & Enrollment Trends by High School')
    hs_names = sorted(overall_summary['HS_Name'].dropna().unique())
    selected_hs_trends = st.selectbox('Select high school for trend analysis', hs_names)
    hs_term_data = term_data[term_data['HS_Name'] == selected_hs_trends].copy()
    if hs_term_data.empty:
        st.warning(f'No term data available for {selected_hs_trends}.')
    else:
        hs_term_data['year'] = pd.to_numeric(hs_term_data['year'], errors='coerce')
        hs_term_data = hs_term_data.sort_values(['year', 'term'])
        
        # Calculate academic year totals for enrollment (Spring + Fall per year)
        yearly_enrollment = hs_term_data.groupby('year')['enrolled_count'].sum().reset_index()
        yearly_enrollment.columns = ['year', 'total_enrolled']
        yearly_enrollment = yearly_enrollment.sort_values('year')
        yearly_enrollment['pct_change'] = yearly_enrollment['total_enrolled'].pct_change() * 100
        yearly_enrollment['direction'] = yearly_enrollment['pct_change'].apply(lambda x: 'ahead' if x >= 0 else 'dip')
        yearly_enrollment['prev_enrolled'] = yearly_enrollment['total_enrolled'].shift(1)
        
        # Calculate academic year totals for applicants (Spring + Fall per year)
        hs_applicants = df[df['HS_Name'] == selected_hs_trends].copy()
        hs_applicants['year'] = hs_applicants['ADMIT_TERM_DESCR'].str.extract(r'(\d{4})')
        hs_applicants['term'] = hs_applicants['ADMIT_TERM_DESCR'].str.extract(r'(Fall|Spring)')
        
        yearly_applicants = hs_applicants.groupby('year')['EMPLID'].count().reset_index()
        yearly_applicants.columns = ['year', 'total_applicants']
        yearly_applicants = yearly_applicants.sort_values('year')
        yearly_applicants['pct_change'] = yearly_applicants['total_applicants'].pct_change() * 100
        yearly_applicants['direction'] = yearly_applicants['pct_change'].apply(lambda x: 'ahead' if x >= 0 else 'dip')
        yearly_applicants['prev_applicants'] = yearly_applicants['total_applicants'].shift(1)
        
        term_applicants = hs_applicants.groupby(['year', 'term'])['EMPLID'].count().reset_index()
        term_applicants.columns = ['year', 'term', 'applicant_count']
        
        # Display Applicant Trends
        st.markdown('### **Applicant Trends (Spring + Fall Combined)**')
        metrics_data_app = yearly_applicants[yearly_applicants['pct_change'].notna()].copy()
        if len(metrics_data_app) > 0:
            cols = st.columns(len(metrics_data_app))
            for idx, (_, row) in enumerate(metrics_data_app.iterrows()):
                with cols[idx]:
                    pct_text = f"{row['pct_change']:.1f}% {row['direction'].upper()}"
                    st.metric(
                        label=f"{int(row['year'])} YoY Change",
                        value=pct_text,
                        delta=f"{int(row['total_applicants'] - row['prev_applicants']):+d} applicants"
                    )
        
        st.dataframe(yearly_applicants[['year', 'total_applicants', 'pct_change', 'direction']], 
                     use_container_width=True, hide_index=True)
        
        # Applicant Year Trend Chart
        yearly_applicants_chart = yearly_applicants[['year', 'total_applicants']].copy()
        yearly_applicants_chart['year'] = yearly_applicants_chart['year'].astype(str)
        
        app_year_chart = alt.Chart(yearly_applicants_chart).mark_line(point=True).encode(
            x=alt.X('year:O', title='Academic Year'),
            y=alt.Y('total_applicants:Q', title='Total Applicants (Spring + Fall)'),
            tooltip=['year:O', 'total_applicants:Q']
        ).properties(width=800, height=420, title='Applicants by Academic Year')
        st.altair_chart(app_year_chart, use_container_width=True)
        
        # Applicant Term-by-term Chart
        st.subheader('Applicants: Term-by-term breakdown')
        term_applicants_chart = term_applicants.copy()
        term_applicants_chart['year'] = term_applicants_chart['year'].astype(str)
        
        app_term_chart = alt.Chart(term_applicants_chart).mark_line(point=True).encode(
            x=alt.X('year:O', title='Year'),
            y=alt.Y('applicant_count:Q', title='Applicant count'),
            color=alt.Color('term:N', title='Term'),
            tooltip=['year:O', 'term:N', 'applicant_count:Q']
        ).properties(width=800, height=420)
        st.altair_chart(app_term_chart, use_container_width=True)

        st.subheader('Program yield by selected ACAD_PLAN')
        if 'ACAD_PLAN' not in df.columns:
            st.warning('No ACAD_PLAN column present to compute program yield.')
        else:
            plan_options = sorted(df['ACAD_PLAN'].dropna().unique())
            selected_plan = st.selectbox('Select program for yield analysis', plan_options, key='program_yield_plan')

            if 'restrict_program_metrics' not in st.session_state:
                st.session_state['restrict_program_metrics'] = False
            if st.button('Toggle CNY community/CC restriction', key='restrict_program_metrics_button'):
                st.session_state['restrict_program_metrics'] = not st.session_state['restrict_program_metrics']

            restriction_enabled = st.session_state['restrict_program_metrics']
            if restriction_enabled:
                st.info('CNY + community/CC restriction is active for program metrics.')
            else:
                st.info('Program metrics are not restricted by LAST_COL_UGRD_SYS / LAST_COL_UGRD_DESCR.')

            plan_df = df[df['ACAD_PLAN'] == selected_plan].copy()
            if restriction_enabled:
                if 'LAST_COL_UGRD_SYS' in plan_df.columns and 'LAST_COL_UGRD_DESCR' in plan_df.columns:
                    plan_df = plan_df[
                        (plan_df['LAST_COL_UGRD_SYS'].astype(str).str.upper() == 'CNY') &
                        (
                            plan_df['LAST_COL_UGRD_DESCR'].astype(str).str.contains('community', case=False, na=False) |
                            plan_df['LAST_COL_UGRD_DESCR'].astype(str).str.contains('CC', case=False, na=False)
                        )
                    ]
                    if plan_df.empty:
                        st.warning('No records match the CNY + community/CC restriction for this program.')
                else:
                    st.warning('Cannot apply restriction: LAST_COL_UGRD_SYS or LAST_COL_UGRD_DESCR column is missing.')

            plan_df['year'] = plan_df['ADMIT_TERM_DESCR'].apply(extract_year)
            plan_df['term'] = plan_df['ADMIT_TERM_DESCR'].apply(extract_term).fillna('Unknown')
            plan_df['enrolled_flag'] = plan_df['enrolled'] == 'Y'
            plan_df['matriculated_flag'] = plan_df['matriculated'] == 'Y'

            program_yield = (
                plan_df
                .groupby(['year', 'term'], dropna=False, as_index=False)
                .agg(
                    admitted=('EMPLID', 'count'),
                    enrolled=('enrolled_flag', 'sum'),
                    matriculated=('matriculated_flag', 'sum')
                )
            )
            program_yield['yield'] = program_yield['enrolled'] / program_yield['admitted']
            program_yield['retention'] = np.where(
                program_yield['matriculated'] > 0,
                program_yield['enrolled'] / program_yield['matriculated'],
                np.nan
            )
            program_yield['commitment'] = np.where(
                program_yield['admitted'] > 0,
                program_yield['matriculated'] / program_yield['admitted'],
                np.nan
            )
            program_yield['year'] = program_yield['year'].fillna('Unknown')

            total_admitted = int(program_yield['admitted'].sum())
            total_enrolled = int(program_yield['enrolled'].sum())
            total_matriculated = int(program_yield['matriculated'].sum())
            total_yield = total_enrolled / total_admitted if total_admitted else np.nan
            total_retention = total_enrolled / total_matriculated if total_matriculated else np.nan
            total_commitment = total_matriculated / total_admitted if total_admitted else np.nan

            col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
            col_a.metric('Program admitted', f'{total_admitted:,}')
            col_b.metric('Program enrolled', f'{total_enrolled:,}')
            col_c.metric('Program matriculated', f'{total_matriculated:,}')
            col_d.metric('Program yield', f'{total_yield:.1%}' if total_admitted else 'N/A')
            col_e.metric('Program retention', f'{total_retention:.1%}' if total_matriculated else 'N/A')
            col_f.metric('Program commitment', f'{total_commitment:.1%}' if total_admitted else 'N/A')

            program_display = program_yield.copy()
            program_display['yield_pct'] = program_display['yield'].map(lambda x: f'{x:.1%}' if pd.notna(x) else 'N/A')
            program_display['retention_pct'] = program_display['retention'].map(lambda x: f'{x:.1%}' if pd.notna(x) else 'N/A')
            program_display['commitment_pct'] = program_display['commitment'].map(lambda x: f'{x:.1%}' if pd.notna(x) else 'N/A')

            st.dataframe(
                program_display[['year', 'term', 'admitted', 'enrolled', 'matriculated', 'yield_pct', 'retention_pct', 'commitment_pct']],
                use_container_width=True
            )

            program_chart = alt.Chart(program_yield).mark_line(point=True).encode(
                x=alt.X('year:O', title='Year'),
                y=alt.Y('yield:Q', title='Yield', axis=alt.Axis(format='.0%')),
                color=alt.Color('term:N', title='Term'),
                tooltip=['year:O', 'term:N', 'admitted:Q', 'enrolled:Q', 'matriculated:Q', 'yield:Q', 'retention:Q', 'commitment:Q']
            ).properties(width=900, height=420, title=f'Yield by term for {selected_plan}')
            st.altair_chart(program_chart, use_container_width=True)

        # Display Enrollment Trends
        st.markdown('### **Enrollment Trends (Spring + Fall Combined)**')
        metrics_data_enroll = yearly_enrollment[yearly_enrollment['pct_change'].notna()].copy()
        if len(metrics_data_enroll) > 0:
            cols = st.columns(len(metrics_data_enroll))
            for idx, (_, row) in enumerate(metrics_data_enroll.iterrows()):
                with cols[idx]:
                    pct_text = f"{row['pct_change']:.1f}% {row['direction'].upper()}"
                    st.metric(
                        label=f"{int(row['year'])} YoY Change",
                        value=pct_text,
                        delta=f"{int(row['total_enrolled'] - row['prev_enrolled']):+d} enrolled"
                    )
        
        st.dataframe(yearly_enrollment[['year', 'total_enrolled', 'pct_change', 'direction']], 
                     use_container_width=True, hide_index=True)
        
        # Enrollment Year Trend Chart
        yearly_enrollment_chart = yearly_enrollment[['year', 'total_enrolled']].copy()
        yearly_enrollment_chart['year'] = yearly_enrollment_chart['year'].astype(str)
        
        enroll_year_chart = alt.Chart(yearly_enrollment_chart).mark_line(point=True).encode(
            x=alt.X('year:O', title='Academic Year'),
            y=alt.Y('total_enrolled:Q', title='Total Enrolled (Spring + Fall)'),
            tooltip=['year:O', 'total_enrolled:Q']
        ).properties(width=800, height=420, title='Enrollment by Academic Year')
        st.altair_chart(enroll_year_chart, use_container_width=True)
        
        # Enrollment Term-by-term Chart
        st.subheader('Enrollment: Term-by-term breakdown')
        hs_term_data_chart = hs_term_data[['year', 'term', 'enrolled_count']].copy()
        hs_term_data_chart['year'] = hs_term_data_chart['year'].astype(str)
        
        enroll_term_chart = alt.Chart(hs_term_data_chart).mark_line(point=True).encode(
            x=alt.X('year:O', title='Year'),
            y=alt.Y('enrolled_count:Q', title='Enrolled count'),
            color=alt.Color('term:N', title='Term'),
            tooltip=['year:O', 'term:N', 'enrolled_count:Q']
        ).properties(width=800, height=420)
        st.altair_chart(enroll_term_chart, use_container_width=True)

        st.markdown(
            """
            **How to read the last chart:** this chart shows enrollment counts for each term (Spring and Fall) across academic years.
            A rising line means that more students enrolled in that term compared to previous years, while a falling line means enrollment dropped.
            Use it together with the combined year totals above to see whether changes are driven by one term or by both terms.
            """
        )
        
        # Comparative Analysis & Conclusions
        st.markdown('### **Comparative Analysis & Conclusions**')
        
        # Merge data for comparison
        comparison_df = yearly_applicants[['year', 'total_applicants', 'pct_change']].copy()
        comparison_df.columns = ['year', 'total_applicants', 'applicant_pct_change']
        comparison_df['year'] = comparison_df['year'].astype(int)
        
        enrollment_for_merge = yearly_enrollment[['year', 'total_enrolled', 'pct_change']].copy()
        enrollment_for_merge['year'] = enrollment_for_merge['year'].astype(int)
        
        comparison_df = comparison_df.merge(
            enrollment_for_merge,
            on='year'
        )
        comparison_df.columns = ['year', 'total_applicants', 'applicant_pct_change', 'total_enrolled', 'enrollment_pct_change']
        
        # Calculate conversion rate
        comparison_df['conversion_rate'] = (comparison_df['total_enrolled'] / comparison_df['total_applicants'] * 100).round(2)
        
        st.dataframe(comparison_df, use_container_width=True, hide_index=True)
        
        # Generate insights
        st.subheader('Key Insights')
        
        latest_year_idx = len(comparison_df) - 1
        if latest_year_idx > 0:
            latest_row = comparison_df.iloc[latest_year_idx]
            prev_row = comparison_df.iloc[latest_year_idx - 1]
            
            insights = []
            
            app_trend = "increased" if latest_row['applicant_pct_change'] >= 0 else "decreased"
            enroll_trend = "increased" if latest_row['enrollment_pct_change'] >= 0 else "decreased"
            
            if latest_row['applicant_pct_change'] >= 0 and latest_row['enrollment_pct_change'] >= 0:
                insights.append(f"✅ **Positive trajectory**: Both applications ({latest_row['applicant_pct_change']:.1f}%) and enrollments ({latest_row['enrollment_pct_change']:.1f}%) are growing.")
            elif latest_row['applicant_pct_change'] < 0 and latest_row['enrollment_pct_change'] < 0:
                insights.append(f"⚠️ **Concerning trend**: Both applications ({latest_row['applicant_pct_change']:.1f}%) and enrollments ({latest_row['enrollment_pct_change']:.1f}%) are declining.")
            elif latest_row['applicant_pct_change'] >= 0 and latest_row['enrollment_pct_change'] < 0:
                insights.append(f"📊 **Conversion issue**: Applications are up ({latest_row['applicant_pct_change']:.1f}%) but enrollments are down ({latest_row['enrollment_pct_change']:.1f}%) - conversion rate may be declining.")
            elif latest_row['applicant_pct_change'] < 0 and latest_row['enrollment_pct_change'] >= 0:
                insights.append(f"📈 **Strong conversion**: Despite fewer applications ({latest_row['applicant_pct_change']:.1f}%), enrollment is up ({latest_row['enrollment_pct_change']:.1f}%) - higher conversion efficiency.")
            
            current_conversion = latest_row['conversion_rate']
            prev_conversion = prev_row['conversion_rate']
            conversion_change = current_conversion - prev_conversion
            
            if conversion_change > 0:
                insights.append(f"📈 **Improved conversion**: Conversion rate increased from {prev_conversion:.1f}% to {current_conversion:.1f}%.")
            elif conversion_change < 0:
                insights.append(f"📉 **Declining conversion**: Conversion rate decreased from {prev_conversion:.1f}% to {current_conversion:.1f}%.")
            
            for insight in insights:
                st.info(insight)

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
            st.markdown(
                """
                **How to read the lost-student chart:** this chart shows the number of students who did not enroll
                after being admitted, grouped by their first choice school and their intended academic plan.
                A taller bar means more lost students selected that first choice and intended that major, which helps
                identify which programs or schools are losing the most admitted students.
                """
            )
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



