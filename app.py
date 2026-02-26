import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

client = MongoClient(st.secrets["MONGO_URI"])
db = client["test"]
users_col = db['users']

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""


def login(username, password):
    return users_col.find_one({
        "username": username,
        "password": password
    })

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
# MONGO DB CONNECTION
# ----------------------------

# Select collection
collections = db.list_collection_names()
selected_collection = st.selectbox("Select Collection", collections)

# Load pre-aggregated data
df = pd.DataFrame(list(db[selected_collection].find()))

if df.empty:
    st.warning("This collection is empty!")
else:
    st.success(f"Loaded {len(df)} records from `{selected_collection}` collection.")
    
category = st.selectbox(
    "Filter by Recruitment Category",
    ["All"] + df["Recruitment_Category"].dropna().unique().tolist()
)

# Filter the data
if category != "All":
    display_df = df[df["Recruitment_Category"] == category]
else:
    display_df = df
    # ----------------------------
    # FIELD MAPPING
    # ----------------------------
    if selected_collection == "Freshmen":
        field_map = {
            "name": "HS_Name",
            "admitted": "admitted",
            "enrolled": "enrolled",
            "term": "ADMIT_TERM",
            "applicants": "applicants"
        }
    else:
        field_map = {
            "name": "LAST_COL_UGRD_DESCR",
            "admitted": "admitted",
            "enrolled": "enrolled",
            "term": "ADMIT_TERM",
            "applicants": "applicants"
        }

    # ----------------------------
    # SEMESTERS LOST MAP
    # ----------------------------
    semesters_lost_map = {1229:7, 1232:6, 1239:5, 1242:4, 1249:3, 1252:2, 1259:1}

    # Compute semesters lost if not already present
    if "semesters_lost" not in df.columns:
        df["semesters_lost"] = df[field_map["term"]].map(semesters_lost_map)

    # ----------------------------
    # YIELD SIMULATION
    # ----------------------------
    TUITION_PER_SEM = 3465
    st.sidebar.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10)/100

    # Use pre-aggregated data
    semester_yield = df[[field_map["name"], field_map["term"], 
                         field_map["admitted"], field_map["enrolled"], 
                         "semesters_lost"]].copy()
    semester_yield = semester_yield[semester_yield[field_map["admitted"]] > 0]

    # Current yield
    semester_yield["current_yield"] = semester_yield[field_map["enrolled"]] / semester_yield[field_map["admitted"]]

    # Apply relative increase
    semester_yield["new_yield"] = (semester_yield["current_yield"] * (1 + relative_increase)).clip(upper=1)

    # Expected enrolled after increase
    semester_yield["expected_enrolled"] = semester_yield[field_map["admitted"]] * semester_yield["new_yield"]

    # Additional students & revenue
    semester_yield["additional_students"] = semester_yield["expected_enrolled"] - semester_yield[field_map["enrolled"]]
    semester_yield["additional_revenue"] = semester_yield["additional_students"] * semester_yield["semesters_lost"] * TUITION_PER_SEM

    # Aggregate revenue per school
    additional_revenue_hs = semester_yield.groupby(field_map["name"])["additional_revenue"].sum().reset_index()
    total_additional = additional_revenue_hs["additional_revenue"].sum()

    st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
    st.metric("Total Historical Money Lost:", f"${df['money_lost'].sum():,.0f}")
    st.dataframe(semester_yield)

    # ----------------------------
    # 3-YEAR GROWTH PROJECTION
    # ----------------------------
    st.header("📈 3-Year Growth Projection")
    term_to_year = {1229: 2022, 1232: 2023, 1239: 2023, 1242: 2024,
                    1249: 2024, 1252: 2025, 1259: 2025}
    df["Year"] = df[field_map["term"]].map(term_to_year)
    df = df.dropna(subset=["Year"])

    yearly = (
        df.groupby([field_map["name"], "Year"])
          .agg(
              applicants=("applicants", "sum"),
              admitted=(field_map["admitted"], "sum"),
              enrolled=(field_map["enrolled"], "sum")
          )
          .reset_index()
    )

    selected_school = st.selectbox("Select School for Projection", yearly[field_map["name"]].unique())
    school_data = yearly[yearly[field_map["name"]] == selected_school].sort_values("Year")

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

        # Applicant plot
        fig_app = go.Figure()
        fig_app.add_trace(go.Scatter(x=school_data["Year"], y=school_data["applicants"],
                                     mode="lines+markers", name="Historical Applicants"))
        fig_app.add_trace(go.Scatter(x=future_years, y=future_apps,
                                     mode="lines+markers", name="Projected Applicants", line=dict(dash="dash")))
        fig_app.update_layout(title=f"{selected_school} - Applicant Projection",
                              xaxis_title="Year", yaxis_title="Applicants",
                              hovermode="x unified")
        st.plotly_chart(fig_app, use_container_width=True)

        # Enrolled plot
        fig_enroll = go.Figure()
        fig_enroll.add_trace(go.Scatter(x=school_data["Year"], y=school_data["enrolled"],
                                        mode="lines+markers", name="Historical Enrolled"))
        fig_enroll.add_trace(go.Scatter(x=future_years, y=future_enrolls,
                                        mode="lines+markers", name="Projected Enrolled", line=dict(dash="dash")))
        fig_enroll.update_layout(title=f"{selected_school} - Enrolled Projection",
                                 xaxis_title="Year", yaxis_title="Enrolled",
                                 hovermode="x unified")
        st.plotly_chart(fig_enroll, use_container_width=True)

        st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
        st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")
    else:
        st.warning("Not enough historical data for projection.")






