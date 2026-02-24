import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")

# --------------------------------------------------
# CACHED MONGO CONNECTION
# --------------------------------------------------
@st.cache_resource
def get_client():
    return MongoClient(st.secrets["MONGO_URI"])

client = get_client()
db = client["test"]

# --------------------------------------------------
# CACHED COLLECTION LIST
# --------------------------------------------------
@st.cache_data(ttl=600)
def get_collections():
    return db.list_collection_names()

collections = get_collections()
selected_collection = st.selectbox("Select Collection", collections)

# --------------------------------------------------
# CACHED DATA LOAD
# --------------------------------------------------
@st.cache_data(ttl=600)
def load_data(collection):
    return pd.DataFrame(list(db[collection].find({}, {"_id": 0})))

df = load_data(selected_collection)

if df.empty:
    st.warning("This collection is empty!")
    st.stop()

st.success(f"Loaded {len(df)} records from `{selected_collection}` collection.")

# --------------------------------------------------
# FIELD MAP
# --------------------------------------------------
if selected_collection == 'Freshmen':
    field_map = {
        "name": "HS_Name",
        "type": "HS_Type",
        "city": "HS_City",
        "state": "HS_State",
        "gpa": "HS_GPA",
        "admitted": "admitted",
        "matriculated": "matriculated",
        "enrolled": "enrolled",
        "department": "Department",
        "term": "ADMIT_TERM"
    }
else:
    field_map = {
        "name": "LAST_COL_UGRD_DESCR",
        "city": "Coll_City",
        "state": "Coll_State",
        "gpa": "Coll_GPA",
        "admitted": "admitted",
        "matriculated": "matriculated",
        "enrolled": "enrolled",
        "department": "Department",
        "term": "ADMIT_TERM"
    }

for key, val in list(field_map.items()):
    if val not in df.columns:
        field_map.pop(key)

# --------------------------------------------------
# PREPROCESS + SCHOOL AGGREGATION (CACHED)
# --------------------------------------------------
@st.cache_data(ttl=600)
def preprocess_and_aggregate(df, field_map):

    TUITION_PER_SEM = 3465
    semesters_lost_map = {1229:7,1232:6,1239:5,1242:4,1249:3,1252:2,1259:1}

    df = df.copy()

    df['semesters_lost'] = df[field_map["term"]].map(semesters_lost_map)

    for col in ["admitted","matriculated","enrolled"]:
        df[field_map[col]] = df[field_map[col]].replace({"Y":1,"N":0}).astype(int)

    df['money_lost'] = (
        (df[field_map["admitted"]] - df[field_map["enrolled"]])
        * df['semesters_lost']
        * TUITION_PER_SEM
    )

    group_cols = [field_map["name"], field_map["city"], field_map["state"]]

    agg_dict = {
        field_map["admitted"]: "sum",
        field_map["matriculated"]: "sum",
        field_map["enrolled"]: "sum",
        field_map["gpa"]: "mean",
        "money_lost": "sum"
    }

    applicant_counts = df.groupby(field_map["name"]).size().rename("applicants")

    hs = (
        df.groupby(group_cols)
        .agg(agg_dict)
        .join(applicant_counts, on=field_map["name"])
        .reset_index()
    )

    hs['yield'] = hs[field_map["enrolled"]] / hs[field_map["admitted"]]
    hs['specific_yield'] = hs[field_map["enrolled"]] / hs[field_map["matriculated"]]
    hs['ROI'] = hs[field_map["enrolled"]] / hs['applicants']

    global_roi = hs[field_map["enrolled"]].sum() / hs['applicants'].sum()
    k = 5
    hs['bayes_ROI'] = (hs[field_map["enrolled"]] + global_roi*k) / (hs['applicants'] + k)

    return df, hs

df, hs = preprocess_and_aggregate(df, field_map)

# --------------------------------------------------
# SEMESTER BASE (CACHED)
# --------------------------------------------------
@st.cache_data(ttl=600)
def build_semester_base(df, field_map):
    return (
        df.groupby([field_map["name"], field_map["term"]])
        .agg(
            admitted=(field_map["admitted"], "sum"),
            enrolled=(field_map["enrolled"], "sum"),
            semesters_lost=('semesters_lost', 'first')
        )
        .reset_index()
    )

semester_base = build_semester_base(df, field_map)

# --------------------------------------------------
# YIELD SIMULATION (FAST PART ONLY)
# --------------------------------------------------
st.sidebar.header("⚙ Yield Simulation")
relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10)/100

semester_yield = semester_base.copy()
semester_yield = semester_yield[semester_yield['admitted'] > 0]

semester_yield['new_yield'] = (
    semester_yield['enrolled']/semester_yield['admitted']*(1+relative_increase)
).clip(upper=1)

semester_yield['expected_enrolled'] = semester_yield['admitted']*semester_yield['new_yield']
semester_yield['additional_students'] = semester_yield['expected_enrolled'] - semester_yield['enrolled']
semester_yield['additional_revenue'] = (
    semester_yield['additional_students'] *
    semester_yield['semesters_lost'] * 3465
)

additional_revenue_hs = semester_yield.groupby(field_map["name"])['additional_revenue'].sum().reset_index()
hs = hs.merge(additional_revenue_hs, on=field_map["name"], how="left")
hs['additional_revenue'] = hs['additional_revenue'].fillna(0)
total_additional = hs['additional_revenue'].sum()

# --------------------------------------------------
# CLASSIFICATION
# --------------------------------------------------
vol_thresh = hs['applicants'].mean()
roi_thresh = hs['bayes_ROI'].mean()

def classify(row):
    if row['applicants'] >= vol_thresh and row['bayes_ROI'] >= roi_thresh:
        return 'Flagship'
    elif row['applicants'] < vol_thresh and row['bayes_ROI'] >= roi_thresh:
        return 'Fringe Gem'
    elif row['applicants'] >= vol_thresh and row['bayes_ROI'] < roi_thresh:
        return 'Over-recruited'
    else:
        return 'Low Priority'

hs['Recruitment_Category'] = hs.apply(classify, axis=1)

# --------------------------------------------------
# DISPLAY
# --------------------------------------------------
category = st.selectbox("Filter by Recruitment Category", ["All"] + list(hs['Recruitment_Category'].unique()))
display_df = hs if category == "All" else hs[hs['Recruitment_Category']==category]

st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
st.dataframe(display_df)

# --------------------------------------------------
# YEARLY PROJECTION (CACHED PRE-AGG)
# --------------------------------------------------
@st.cache_data(ttl=600)
def build_yearly_projection(df, field_map):

    term_to_year = {1229: 2022, 1232: 2023, 1239: 2023,
                    1242: 2024, 1249: 2024,
                    1252: 2025, 1259: 2025}

    df = df.copy()
    df['Year'] = df[field_map['term']].map(term_to_year)
    df = df.dropna(subset=['Year'])

    yearly = (
        df.groupby([field_map['name'], 'Year'])
          .agg(
              applicants=(field_map['name'], 'count'),
              admitted=(field_map['admitted'], 'sum'),
              enrolled=(field_map['enrolled'], 'sum')
          )
          .reset_index()
    )

    return yearly

yearly = build_yearly_projection(df, field_map)

# --------------------------------------------------
# PROJECTION SECTION
# --------------------------------------------------
st.header("📈 3-Year Growth Projection")

selected_school = st.selectbox("Select School for Projection", yearly[field_map['name']].unique())
school_data = yearly[yearly[field_map['name']] == selected_school].sort_values('Year')

def calculate_cagr(first, last, years):
    if first <= 0 or years <= 0:
        return 0
    rate = (last / first) ** (1 / years) - 1
    return max(min(rate, 0.25), -0.25)

if len(school_data) >= 2:

    first_year = school_data['Year'].iloc[0]
    last_year = school_data['Year'].iloc[-1]
    years_diff = last_year - first_year

    app_growth = calculate_cagr(
        school_data['applicants'].iloc[0],
        school_data['applicants'].iloc[-1],
        years_diff
    )

    enroll_growth = calculate_cagr(
        school_data['enrolled'].iloc[0],
        school_data['enrolled'].iloc[-1],
        years_diff
    )

    last_app = school_data['applicants'].iloc[-1]
    last_enroll = school_data['enrolled'].iloc[-1]

    future_years = [last_year+i for i in range(1,4)]
    future_apps = [last_app*((1+app_growth)**i) for i in range(1,4)]
    future_enrolls = [last_enroll*((1+enroll_growth)**i) for i in range(1,4)]

    fig_app = go.Figure()
    fig_app.add_trace(go.Scatter(x=school_data['Year'], y=school_data['applicants'],
                                 mode='lines+markers', name='Historical Applicants'))
    fig_app.add_trace(go.Scatter(x=future_years, y=future_apps,
                                 mode='lines+markers', name='Projected Applicants',
                                 line=dict(dash='dash')))
    st.plotly_chart(fig_app, use_container_width=True)

    fig_enroll = go.Figure()
    fig_enroll.add_trace(go.Scatter(x=school_data['Year'], y=school_data['enrolled'],
                                    mode='lines+markers', name='Historical Enrolled'))
    fig_enroll.add_trace(go.Scatter(x=future_years, y=future_enrolls,
                                    mode='lines+markers', name='Projected Enrolled',
                                    line=dict(dash='dash')))
    st.plotly_chart(fig_enroll, use_container_width=True)

    st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
    st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")
