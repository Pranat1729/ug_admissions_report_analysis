import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

if not st.session_state.get("logged_in", False):
    st.warning("Please log in from the Home page.")
    st.stop()

st.title("🔭 Looking Forward: 2027 Cycle")
st.markdown("Prospective student data from NACAC College Fairs")


up = st.file_uploader("Upload prospectives CSV", type="csv")

if up is None:
    st.info("Upload the prospectives CSV to get started.")
    st.stop()

df_raw = pd.read_csv(up)

df27 = df_raw[
    (df_raw['StartingTerm'] == 'Fall 2027') |
    (df_raw['StartingTerm'] == 'Spring 2027')
].copy()

if df27.empty:
    st.warning("No 2027 cycle records found.")
    st.stop()



eth_counts = df27['Ethnicity'].value_counts(dropna=False)


def clean_school(name):
    if pd.isna(name): return 'Unknown'
    parts = str(name).split(',')
    return parts[0].strip()

df27['SchoolNameClean'] = df27['SchoolName'].apply(clean_school)


df27['Flag_GradYear'] = ~df27['HSGradYear'].isin([2027.0, np.nan])


df27['Has_Email']   = df27['Email'].notna() & (df27['Email'] != '')
df27['Has_Phone']   = df27['CellPhone'].notna() & (df27['CellPhone'] != '')
df27['Contactable'] = df27['Has_Email'] | df27['Has_Phone']


df27['LeadRank_Clean'] = df27['LeadRank'].fillna('Unranked')


AREA_KNOWN = [
    'Health and Medicine','Health Professions and Related Clinical Sciences',
    'Biological and Biomedical Sciences','Arts','Psychology',
    'Computer and Information Sciences','Business','Arts and Humanities',
    'Architecture and Planning','Hospitality Administration and Management',
    'Engineering','Education','Law and Legal Studies',
    'Liberal Arts and Sciences','Public and Social Services',
    'Communication and Journalism','Social Sciences','Physical Sciences',
    'Math and Statistics','Philosophy and Religion','History',
    'English Language and Literature','Science Technologies',
    'Natural Resources and Conservation','Security and Protective Services',
    'Multi-/Interdisciplinary Studies','Visual and Performing Arts',
]

def parse_areas(val):
    if pd.isna(val): return []
    found = [a for a in AREA_KNOWN if a in val]
    return found if found else [val.split(',')[0].strip()]

df27['AreasList'] = df27['AreasOfStudy'].apply(parse_areas)
areas_exploded = df27['AreasList'].explode().dropna()
areas_freq = areas_exploded.value_counts().reset_index()
areas_freq.columns = ['Area', 'Count']


with st.sidebar:
    st.markdown("### 🔍 27 Cycle Filters")
    term_filter = st.multiselect("Starting Term", df27['StartingTerm'].unique().tolist(),
                                  default=df27['StartingTerm'].unique().tolist())
    eth_filter  = st.multiselect("Ethnicity", df27['Ethnicity'].dropna().unique().tolist(),
                                  default=df27['Ethnicity'].dropna().unique().tolist())
    rank_filter = st.multiselect("Lead Rank", df27['LeadRank_Clean'].unique().tolist(),
                                  default=df27['LeadRank_Clean'].unique().tolist())

df_f = df27[
    df27['StartingTerm'].isin(term_filter) &
    (df27['Ethnicity'].isin(eth_filter) | df27['Ethnicity'].isna()) &
    df27['LeadRank_Clean'].isin(rank_filter)
]


st.markdown("---")
st.header("📋 Overview")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Prospects",    len(df_f))
c2.metric("Hot Leads",          int((df_f['LeadRank_Clean'] == 'Hot').sum()))
c3.metric("Contactable",        int(df_f['Contactable'].sum()))
c4.metric("Unique HS Schools",  df_f['SchoolNameClean'].nunique())
c5.metric("Flagged Records",    int(df_f['Flag_GradYear'].sum()),
          help="Grad year not 2027 — may be adult learners or data entry errors")

st.markdown("---")


st.header("🎯 Pipeline Quality")

col1, col2 = st.columns(2)

with col1:
    
    rank_counts = df_f['LeadRank_Clean'].value_counts().reset_index()
    rank_counts.columns = ['Rank', 'Count']
    fig_rank = px.pie(rank_counts, names='Rank', values='Count',
                      title='Lead Rank Breakdown',
                      hole=0.45,
                      color='Rank',
                      color_discrete_map={'Hot':'#D85A30','Medium':'#F0A500','Unranked':'#D3D1C7'})
    fig_rank.update_traces(textinfo='label+value')
    st.plotly_chart(fig_rank, use_container_width=True)

with col2:
   
    contact_data = pd.DataFrame({
        'Type':  ['Email + Phone', 'Email Only', 'Phone Only', 'Neither'],
        'Count': [
            int((df_f['Has_Email'] & df_f['Has_Phone']).sum()),
            int((df_f['Has_Email'] & ~df_f['Has_Phone']).sum()),
            int((~df_f['Has_Email'] & df_f['Has_Phone']).sum()),
            int((~df_f['Has_Email'] & ~df_f['Has_Phone']).sum()),
        ]
    })
    fig_contact = px.pie(contact_data, names='Type', values='Count',
                         title='Contact Info Completeness',
                         hole=0.45,
                         color_discrete_sequence=px.colors.qualitative.Set2)
    fig_contact.update_traces(textinfo='label+value')
    st.plotly_chart(fig_contact, use_container_width=True)


term_counts = df_f['StartingTerm'].value_counts().reset_index()
term_counts.columns = ['Term', 'Count']
fig_term = px.bar(term_counts, x='Term', y='Count', text='Count',
                  title='Prospects by Starting Term',
                  color='Term', color_discrete_sequence=px.colors.qualitative.Pastel)
fig_term.update_traces(textposition='outside')
fig_term.update_layout(showlegend=False)
st.plotly_chart(fig_term, use_container_width=True)

st.markdown("---")


st.header("👥 Demographics")

col1, col2 = st.columns(2)

with col1:
    # Ethnicity bar — fixed (was using nunique which was wrong)
    eth = df_f['Ethnicity'].value_counts(dropna=False).reset_index()
    eth.columns = ['Ethnicity', 'Count']
    eth['Ethnicity'] = eth['Ethnicity'].fillna('No Answer')
    fig_eth = px.bar(eth, x='Count', y='Ethnicity', orientation='h',
                     text='Count', title='Ethnicity Breakdown',
                     color='Ethnicity',
                     color_discrete_sequence=px.colors.qualitative.Set3)
    fig_eth.update_traces(textposition='outside')
    fig_eth.update_layout(showlegend=False, yaxis={'categoryorder':'total ascending'})
    st.plotly_chart(fig_eth, use_container_width=True)

with col2:

    gen = df_f['Gender'].value_counts(dropna=False).reset_index()
    gen.columns = ['Gender', 'Count']
    gen['Gender'] = gen['Gender'].fillna('No Answer')
    fig_gen = px.pie(gen, names='Gender', values='Count',
                     title='Gender Breakdown', hole=0.45,
                     color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_gen.update_traces(textinfo='label+percent')
    st.plotly_chart(fig_gen, use_container_width=True)


st.markdown("#### Gender × Ethnicity")
cross = pd.crosstab(
    df_f['Ethnicity'].fillna('No Answer'),
    df_f['Gender'].fillna('No Answer')
)
st.dataframe(cross, use_container_width=True)

st.markdown("---")


st.header("🎓 Academic Interests")

col1, col2 = st.columns(2)

with col1:
    
    ai1 = df_f['AcademicInterest1'].value_counts(dropna=False).reset_index()
    ai1.columns = ['Interest', 'Count']
    ai1['Interest'] = ai1['Interest'].fillna('Not specified')
    fig_ai = px.bar(ai1.head(12), x='Count', y='Interest', orientation='h',
                    text='Count', title='Primary Academic Interest',
                    color='Count', color_continuous_scale='Blues')
    fig_ai.update_traces(textposition='outside')
    fig_ai.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
    st.plotly_chart(fig_ai, use_container_width=True)

with col2:
  
    if not areas_freq.empty:
        fig_areas = px.bar(areas_freq.head(12), x='Count', y='Area', orientation='h',
                           text='Count', title='Areas of Study Interest',
                           color='Count', color_continuous_scale='Greens')
        fig_areas.update_traces(textposition='outside')
        fig_areas.update_layout(yaxis={'categoryorder':'total ascending'}, coloraxis_showscale=False)
        st.plotly_chart(fig_areas, use_container_width=True)

# Gender x primary interest crosstab
st.markdown("#### Gender × Academic Interest")
if df_f['AcademicInterest1'].notna().sum() > 0:
    cross_interest = pd.crosstab(
        df_f['AcademicInterest1'].fillna('Not specified'),
        df_f['Gender'].fillna('No Answer')
    )
    st.dataframe(cross_interest, use_container_width=True)

st.markdown("---")


st.header("🏫 High School Outreach")

school_counts = (
    df_f.groupby('SchoolNameClean')
         .agg(
             prospects=('AttendeeID', 'count'),
             hot_leads=('LeadRank_Clean', lambda x: (x == 'Hot').sum()),
             contactable=('Contactable', 'sum'),
             top_interest=('AcademicInterest1', lambda x: x.mode().iloc[0] if not x.mode().empty else 'N/A')
         )
         .reset_index()
         .sort_values('prospects', ascending=False)
)

fig_school = px.bar(
    school_counts.head(15),
    x='SchoolNameClean', y='prospects',
    text='prospects', title='Top 15 Schools by Prospect Count',
    color='prospects', color_continuous_scale='Viridis'
)
fig_school.update_traces(textposition='outside')
fig_school.update_layout(xaxis_tickangle=-45, coloraxis_showscale=False)
st.plotly_chart(fig_school, use_container_width=True)

st.dataframe(school_counts, use_container_width=True, hide_index=True)

st.markdown("---")


st.header("📝 Rep Notes & Insights")

insights = df_f[df_f['RepInsights'].notna()][
    ['FirstName','LastName','SchoolNameClean','LeadRank_Clean','AcademicInterest1','RepInsights']
].copy()

if not insights.empty:
    st.dataframe(insights, use_container_width=True, hide_index=True)
else:
    st.info("No rep insights recorded for filtered prospects.")

st.markdown("---")


st.header("⚠️ Flagged Records")

flagged = df_f[df_f['Flag_GradYear']][
    ['FirstName','LastName','SchoolNameClean','HSGradYear','StudentType','RepInsights']
]
if not flagged.empty:
    st.warning(f"{len(flagged)} records have unexpected grad years — may be adult learners or data entry errors.")
    st.dataframe(flagged, use_container_width=True, hide_index=True)
else:
    st.success("No flagged records in current filter.")

st.markdown("---")


st.header("📣 Outreach Recommendations")

hot_leads = df_f[df_f['LeadRank_Clean'] == 'Hot'][
    ['FirstName','LastName','Email','CellPhone','SchoolNameClean','AcademicInterest1','RepInsights']
]
if not hot_leads.empty:
    st.markdown("#### 🔥 Hot Leads — Priority Follow-up")
    st.dataframe(hot_leads, use_container_width=True, hide_index=True)

st.markdown("#### 📊 Interest-Based Outreach Targets")
outreach = (
    df_f.groupby('AcademicInterest1')
         .agg(count=('AttendeeID','count'),
              contactable=('Contactable','sum'),
              hot=('LeadRank_Clean', lambda x: (x=='Hot').sum()))
         .reset_index()
         .sort_values('count', ascending=False)
         .rename(columns={'AcademicInterest1':'Interest'})
)
outreach['Interest'] = outreach['Interest'].fillna('Not specified')
st.dataframe(outreach, use_container_width=True, hide_index=True)

st.markdown("#### 📋 Full 2027 Prospect List")
show_cols = ['FirstName','LastName','Email','CellPhone','SchoolNameClean',
             'Ethnicity','Gender','AcademicInterest1','StartingTerm',
             'LeadRank_Clean','Contactable','RepInsights']
available = [c for c in show_cols if c in df_f.columns]
st.dataframe(df_f[available].sort_values('LeadRank_Clean'), use_container_width=True, hide_index=True)
