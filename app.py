
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

# ----------------------------
# MONGO CONNECTION
# ----------------------------
client = MongoClient(st.secrets["MONGO_URI"])
db = client["test"]
users_col = db['users']

# ----------------------------
# LOGIN SESSION
# ----------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""

def login(username, password):
    return users_col.find_one({"username": username, "password": password})

if not st.session_state.logged_in:
    st.title("Recruitment Analysis Report Log In")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            user = login(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = user.get("role", "user")
            else:
                st.error("Invalid username or password")
    st.stop()

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")

# ----------------------------
# USER SELECTS DATASET TYPE
# ----------------------------
dataset_type = st.selectbox("Select Dataset Type", ["Freshmen", "Transfers"])

# ----------------------------
# AUTOMATIC COLLECTION MAPPING
# ----------------------------
if dataset_type == "Freshmen":
    school_col = "Freshmen"
    term_col = "Freshmen_F"
    name_field = "HS_Name"
else:
    school_col = "Transfers"
    term_col = "Transfers_F"
    name_field = "LAST_COL_UGRD_DESCR"

# ----------------------------
# LOAD COLLECTIONS
# ----------------------------
df_school = pd.DataFrame(list(db[school_col].find()))
df_term = pd.DataFrame(list(db[term_col].find()))

if df_school.empty:
    st.warning(f"{dataset_type} School-level collection is empty!")
if df_term.empty:
    st.warning(f"{dataset_type} Term-level collection is empty!")

# ----------------------------
# SCHOOL-LEVEL LOGIC
# ----------------------------
if not df_school.empty:
    hs_school = df_school.copy()
    hs_school['yield'] = hs_school['enrolled'] / hs_school['admitted']
    hs_school['ROI'] = hs_school['enrolled'] / hs_school['applicants']
    hs_school.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Bayesian smoothing
    global_roi = hs_school['enrolled'].sum() / hs_school['applicants'].sum()
    k = 5
    hs_school['bayes_ROI'] = (hs_school['enrolled'] + global_roi * k) / (hs_school['applicants'] + k)

    # Classification
    vol_thresh = hs_school['applicants'].mean()
    roi_thresh = hs_school['bayes_ROI'].mean()

    def classify_school(row):
        if row['applicants'] >= vol_thresh and row['bayes_ROI'] >= roi_thresh:
            return 'Flagship'
        elif row['applicants'] < vol_thresh and row['bayes_ROI'] >= roi_thresh:
            return 'Fringe Gem'
        elif row['applicants'] >= vol_thresh and row['bayes_ROI'] < roi_thresh:
            return 'Over-recruited'
        else:
            return 'Low Priority'

    hs_school['Recruitment_Category'] = hs_school.apply(classify_school, axis=1)

    st.header(f"🏫 {dataset_type} - School-level Analysis")
    st.dataframe(hs_school)

# ----------------------------
# TERM-LEVEL LOGIC
# ----------------------------
if not df_term.empty:
    TUITION_PER_SEM = 3465
    semesters_lost_map = {1229:7, 1232:6, 1239:5, 1242:4, 1249:3, 1252:2, 1259:1}

    df_term["semesters_lost"] = df_term["ADMIT_TERM"].map(semesters_lost_map)
    df_term['money_lost'] = ((df_term['admitted'] - df_term['enrolled']).clip(lower=0)
                             * df_term['semesters_lost'] * TUITION_PER_SEM)

    st.sidebar.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10)/100

    semester_yield = df_term[[name_field, "ADMIT_TERM", "admitted", "enrolled", "semesters_lost"]].copy()
    semester_yield = semester_yield[semester_yield['admitted'] > 0]

    semester_yield["current_yield"] = semester_yield["enrolled"] / semester_yield["admitted"]
    semester_yield["new_yield"] = (semester_yield["current_yield"] * (1 + relative_increase)).clip(upper=1)
    semester_yield["expected_enrolled"] = semester_yield["admitted"] * semester_yield["new_yield"]
    semester_yield["additional_students"] = semester_yield["expected_enrolled"] - semester_yield["enrolled"]
    semester_yield["additional_revenue"] = semester_yield["additional_students"] * semester_yield["semesters_lost"] * TUITION_PER_SEM

    total_additional = semester_yield["additional_revenue"].sum()
    st.header(f"📅 {dataset_type} - Term-level Yield & Revenue")
    st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
    st.dataframe(semester_yield)
total_admitted = df_term["admitted"].sum()
total_enrolled = df_term["enrolled"].sum()

current_yield = total_enrolled / total_admitted if total_admitted > 0 else 0

# ----------------------------
# REALISTIC MONEY LOST (based on 60% cap)
# ----------------------------
if not df_term.empty:
    df_term["max_realistic_enrolled"] = df_term["admitted"] * 0.6
    
    df_term["realistic_gap"] = (
        df_term["max_realistic_enrolled"] - df_term["enrolled"]
    ).clip(lower=0)
    
    df_term["realistic_money_lost"] = (
        df_term["realistic_gap"]
        * df_term["semesters_lost"]
        * TUITION_PER_SEM
    )
    
    total_realistic_lost = df_term["realistic_money_lost"].sum()
    st.metric("💰 Total Money Lost(with a historical max yield of 0.6)", f"${total_realistic_lost:,.0f}")
# ----------------------------
# FILTER BY RECRUITMENT CATEGORY
# ----------------------------
if "Recruitment_Category" in df_term.columns:
    category_options = ["All"] + sorted(df_term["Recruitment_Category"].dropna().unique())
    selected_category = st.selectbox("Select Recruitment Category", category_options)

    if selected_category != "All":
        df_filtered = df_term[df_term["Recruitment_Category"] == selected_category].copy()
    else:
        df_filtered = df_term.copy()
else:
    df_filtered = df_term.copy()

if not df_filtered.empty:
    df_filtered["semesters_lost"] = df_filtered["ADMIT_TERM"].map(semesters_lost_map)

    total_admitted = df_filtered["admitted"].sum()
    total_enrolled = df_filtered["enrolled"].sum()
    
    current_yield = total_enrolled / total_admitted if total_admitted > 0 else 0
    
    df_filtered["max_realistic_enrolled"] = df_filtered["admitted"] * 0.6
    df_filtered["realistic_gap"] = (
        df_filtered["max_realistic_enrolled"] - df_filtered["enrolled"]
    ).clip(lower=0)
    
    df_filtered["realistic_money_lost"] = (
        df_filtered["realistic_gap"]
        * df_filtered["semesters_lost"]
        * TUITION_PER_SEM
    )
    
    total_realistic_lost = df_filtered["realistic_money_lost"].sum()
    st.metric("💰 Total Money Lost(with a historical max yield of 0.6) for the chosen category", f"${total_realistic_lost:,.0f}")

# ----------------------------
# PROJECTIONS (can merge term-level per school)
# ----------------------------
if not df_term.empty:
    df_term["Year"] = df_term["ADMIT_TERM"].map({1229:2022,1232:2023,1239:2023,1242:2024,
                                                1249:2024,1252:2025,1259:2025})
    df_term = df_term.dropna(subset=["Year"])
    yearly = df_term.groupby([name_field,"Year"]).agg(
        applicants=("admitted","sum"),
        admitted=("admitted","sum"),
        enrolled=("enrolled","sum")
    ).reset_index()

    selected_school = st.selectbox(f"Select {dataset_type} School for Projection", yearly[name_field].unique())
    school_data = yearly[yearly[name_field]==selected_school].sort_values("Year")

    def calculate_cagr(first, last, years):
        if first <= 0 or years <= 0:
            return 0
        rate = (last / first) ** (1 / years) - 1
        return max(min(rate, 0.25), -0.25)

    if len(school_data) >= 2:
        years_diff = school_data["Year"].iloc[-1] - school_data["Year"].iloc[0]
        app_growth = calculate_cagr(school_data["applicants"].iloc[0], school_data["applicants"].iloc[-1], years_diff)
        enroll_growth = calculate_cagr(school_data["enrolled"].iloc[0], school_data["enrolled"].iloc[-1], years_diff)

        last_app = school_data["applicants"].iloc[-1]
        last_enroll = school_data["enrolled"].iloc[-1]
        future_years = [school_data["Year"].iloc[-1] + i for i in range(1,4)]
        future_apps = [last_app * ((1 + app_growth) ** i) for i in range(1,4)]
        future_enrolls = [last_enroll * ((1 + enroll_growth) ** i) for i in range(1,4)]

        # Plots
        fig_app = go.Figure()
        fig_app.add_trace(go.Scatter(x=school_data["Year"], y=school_data["applicants"],
                                     mode="lines+markers", name="Historical Applicants"))
        fig_app.add_trace(go.Scatter(x=future_years, y=future_apps,
                                     mode="lines+markers", name="Projected Applicants", line=dict(dash="dash")))
        fig_app.update_layout(title=f"{selected_school} - Applicant Projection", xaxis_title="Year", yaxis_title="Applicants")
        st.plotly_chart(fig_app, use_container_width=True)

        fig_enroll = go.Figure()
        fig_enroll.add_trace(go.Scatter(x=school_data["Year"], y=school_data["enrolled"],
                                        mode="lines+markers", name="Historical Enrolled"))
        fig_enroll.add_trace(go.Scatter(x=future_years, y=future_enrolls,
                                        mode="lines+markers", name="Projected Enrolled", line=dict(dash="dash")))
        fig_enroll.update_layout(title=f"{selected_school} - Enrolled Projection", xaxis_title="Year", yaxis_title="Enrolled")
        st.plotly_chart(fig_enroll, use_container_width=True)

        st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
        st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")
    else:
        st.warning("Not enough historical data for projection.")





