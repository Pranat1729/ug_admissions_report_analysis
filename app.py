import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")


client = MongoClient(st.secrets["MONGO_URI"])
db = client["test"]  

# List all collections
collections = db.list_collection_names()
selected_collection = st.selectbox("Select Collection", collections)

# Fetch entire collection as DataFrame
df = pd.DataFrame(list(db[selected_collection].find()))

if df.empty:
    st.warning("This collection is empty!")
else:
    st.success(f"Loaded {len(df)} records from `{selected_collection}` collection.")

    # ----------------------------
    # FIELD MAPPING LOGIC
    # ----------------------------
    # Map standard names for the app
    # Adjust depending on collection
    if selected_collection == 'Freshmen':  # Freshman CSV
        field_map = {
            "name": "HS_Name",
            "type": "HS_Type",
            "city": "HS_City",
            "state": "HS_State",
            "gpa": "HS_GPA",
            "admitted": "admitted",
            "matriculated": "matriculated",
            "enrolled": "enrolled",
            #"department": "Department",
            "term": "ADMIT_TERM"
        }
    else:  # Transfer CSV
        field_map = {
            "name": "LAST_COL_UGRD_DESCR",
  # not present in transfer, will skip
            "city": "Coll_City",
            "state": "Coll_State",
            "gpa": "Coll_GPA",
            "admitted": "admitted",
            "matriculated": "matriculated",
            "enrolled": "enrolled",
            #"department": "Department",
            "term": "ADMIT_TERM"
        }

    # Optional: drop missing columns
    for key, val in list(field_map.items()):
        if val not in df.columns:
            st.warning(f"Column `{val}` not found in this collection; skipping mapping.")
            field_map.pop(key)
# ----------------------------
# PROCESS METRICS
# ----------------------------
TUITION_PER_SEM = 3465
semesters_lost_map = {1229:7,1232:6,1239:5,1242:4,1249:3,1252:2,1259:1}

if field_map.get("term"):
    df["semesters_lost"] = df[field_map["term"]].map(semesters_lost_map)

# ---------------------------------------------------
# -------- YIELD INCREASE SIMULATION (FIXED) -------
# ---------------------------------------------------

st.sidebar.header("⚙ Yield Simulation")
relative_increase = st.sidebar.slider(
    "Increase Yield (%)", 0, 50, 10
) / 100

# IMPORTANT:
# Dataset is already pre-aggregated.
# DO NOT group again.

semester_yield = df[[
    field_map["name"],
    field_map["term"],
    field_map["admitted"],
    field_map["enrolled"],
    "semesters_lost"
]].copy()

semester_yield = semester_yield[
    semester_yield[field_map["admitted"]] > 0
]

# Current yield
semester_yield["current_yield"] = (
    semester_yield[field_map["enrolled"]] /
    semester_yield[field_map["admitted"]]
)

# Apply relative increase
semester_yield["new_yield"] = (
    semester_yield["current_yield"] *
    (1 + relative_increase)
).clip(upper=1)

# Expected enrolled after increase
semester_yield["expected_enrolled"] = (
    semester_yield[field_map["admitted"]] *
    semester_yield["new_yield"]
)

# Additional students
semester_yield["additional_students"] = (
    semester_yield["expected_enrolled"] -
    semester_yield[field_map["enrolled"]]
)

# Additional revenue
semester_yield["additional_revenue"] = (
    semester_yield["additional_students"] *
    semester_yield["semesters_lost"] *
    TUITION_PER_SEM
)

# Aggregate revenue per school
additional_revenue_hs = (
    semester_yield
    .groupby(field_map["name"])["additional_revenue"]
    .sum()
    .reset_index()
)

# Merge safely
hs = hs.merge(
    additional_revenue_hs,
    on=field_map["name"],
    how="left"
)

hs["additional_revenue"] = hs["additional_revenue"].fillna(0)

total_additional = hs["additional_revenue"].sum()

# ----------------------------------------
# CATEGORY FILTER
# ----------------------------------------

category = st.selectbox(
    "Filter by Recruitment Category",
    ["All"] + list(hs["Recruitment_Category"].dropna().unique())
)

if category != "All":
    display_df = hs[hs["Recruitment_Category"] == category]
else:
    display_df = hs

st.metric(
    "💰 Total Additional Revenue Potential",
    f"${total_additional:,.0f}"
)

st.dataframe(display_df)

# ---------------------------------------------------
# ---------------- PROJECTION SECTION --------------
# ---------------------------------------------------

st.header("📈 3-Year Growth Projection")

term_to_year = {
    1229: 2022,
    1232: 2023,
    1239: 2023,
    1242: 2024,
    1249: 2024,
    1252: 2025,
    1259: 2025
}

df["Year"] = df[field_map["term"]].map(term_to_year)
df = df.dropna(subset=["Year"])

# Since dataset is pre-aggregated,
# we can safely sum across years

yearly = (
    df.groupby([field_map["name"], "Year"])
      .agg(
          applicants=("applicants", "sum"),
          admitted=(field_map["admitted"], "sum"),
          enrolled=(field_map["enrolled"], "sum")
      )
      .reset_index()
)

# FIXED: correct column reference
selected_school = st.selectbox(
    "Select School for Projection",
    yearly[field_map["name"]].unique()
)

school_data = (
    yearly[yearly[field_map["name"]] == selected_school]
    .sort_values("Year")
)

def calculate_cagr(first, last, years):
    if first <= 0 or years <= 0:
        return 0
    rate = (last / first) ** (1 / years) - 1
    return max(min(rate, 0.25), -0.25)

if len(school_data) >= 2:

    first_year = school_data["Year"].iloc[0]
    last_year = school_data["Year"].iloc[-1]
    years_diff = last_year - first_year

    app_growth = calculate_cagr(
        school_data["applicants"].iloc[0],
        school_data["applicants"].iloc[-1],
        years_diff
    )

    enroll_growth = calculate_cagr(
        school_data["enrolled"].iloc[0],
        school_data["enrolled"].iloc[-1],
        years_diff
    )

    last_app = school_data["applicants"].iloc[-1]
    last_enroll = school_data["enrolled"].iloc[-1]

    future_years = []
    future_apps = []
    future_enrolls = []

    for i in range(1, 4):
        future_years.append(last_year + i)
        future_apps.append(last_app * ((1 + app_growth) ** i))
        future_enrolls.append(last_enroll * ((1 + enroll_growth) ** i))

    # Applicants Plot
    fig_app = go.Figure()
    fig_app.add_trace(go.Scatter(
        x=school_data["Year"],
        y=school_data["applicants"],
        mode="lines+markers",
        name="Historical Applicants"
    ))
    fig_app.add_trace(go.Scatter(
        x=future_years,
        y=future_apps,
        mode="lines+markers",
        name="Projected Applicants",
        line=dict(dash="dash")
    ))

    fig_app.update_layout(
        title=f"{selected_school} - Applicant Projection",
        xaxis_title="Year",
        yaxis_title="Applicants",
        hovermode="x unified"
    )

    st.plotly_chart(fig_app, use_container_width=True)

    # Enrolled Plot
    fig_enroll = go.Figure()
    fig_enroll.add_trace(go.Scatter(
        x=school_data["Year"],
        y=school_data["enrolled"],
        mode="lines+markers",
        name="Historical Enrolled"
    ))
    fig_enroll.add_trace(go.Scatter(
        x=future_years,
        y=future_enrolls,
        mode="lines+markers",
        name="Projected Enrolled",
        line=dict(dash="dash")
    ))

    fig_enroll.update_layout(
        title=f"{selected_school} - Enrolled Projection",
        xaxis_title="Year",
        yaxis_title="Enrolled",
        hovermode="x unified"
    )

    st.plotly_chart(fig_enroll, use_container_width=True)

    st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
    st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")

else:
    st.warning("Not enough historical data for projection.")
