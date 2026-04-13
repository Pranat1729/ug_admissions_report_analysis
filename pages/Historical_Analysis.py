import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from pymongo import MongoClient

if not st.session_state.get("logged_in", False):
    st.warning("Please log in from the Home page.")
    st.stop()

@st.cache_resource
def get_db():
    client = MongoClient(st.secrets["MONGO_URI"])
    return client["test"]

db = get_db()


@st.cache_data(ttl=600)
def load_data(school_col, term_col):
    df_school = pd.DataFrame(list(db[school_col].find({}, {"_id": 0})))
    df_term   = pd.DataFrame(list(db[term_col].find({}, {"_id": 0})))
    return df_school, df_term

@st.cache_data
def process_school_data(df_school):
    hs_school = df_school.copy()
    hs_school["yield"] = hs_school["enrolled"] / hs_school["admitted"]
    hs_school["ROI"]   = hs_school["enrolled"] / hs_school["applicants"]
    hs_school.replace([np.inf, -np.inf], np.nan, inplace=True)

    global_roi = hs_school["enrolled"].sum() / hs_school["applicants"].sum()
    k = 5
    hs_school["bayes_ROI"] = (
        hs_school["enrolled"] + global_roi * k
    ) / (hs_school["applicants"] + k)

    vol_thresh = hs_school["applicants"].mean()
    roi_thresh = hs_school["bayes_ROI"].mean()

    def classify_school(row):
        if row["applicants"] >= vol_thresh and row["bayes_ROI"] >= roi_thresh:
            return "Flagship"
        elif row["applicants"] < vol_thresh and row["bayes_ROI"] >= roi_thresh:
            return "Fringe Gem"
        elif row["applicants"] >= vol_thresh and row["bayes_ROI"] < roi_thresh:
            return "Over-recruited"
        else:
            return "Low Priority"

    hs_school["Recruitment_Category"] = hs_school.apply(classify_school, axis=1)
    return hs_school

@st.cache_data
def merge_term_category(df_term, hs_school, name_field):
    return df_term.merge(
        hs_school[[name_field, "Recruitment_Category"]],
        on=name_field,
        how="left"
    )


with st.sidebar:
    st.title("📊 Recruitment Analytics")
    st.success(f"Logged in as **{st.session_state.username}**")
    st.markdown("---")
    st.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10) / 100
    st.markdown("---")
    if st.button("Log Out", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username  = ""
        st.session_state.role      = "user"
        st.rerun()
    st.markdown("---")
    st.caption("Bugs? pranat32@gmail.com")


st.title("📊 Recruitment Analytics Dashboard")

dataset_type = st.selectbox("Select Dataset Type", ["Freshmen", "Transfers"])

if dataset_type == "Freshmen":
    school_col = "Freshmen"
    term_col   = "Freshmen_F"
    name_field = "HS_Name"
else:
    school_col = "Transfers"
    term_col   = "Transfers_F"
    name_field = "LAST_COL_UGRD_DESCR"

df_school, df_term = load_data(school_col, term_col)

if df_school.empty:
    st.warning(f"{dataset_type} School-level collection is empty!")
if df_term.empty:
    st.warning(f"{dataset_type} Term-level collection is empty!")


# ================= SCHOOL LEVEL =================
if not df_school.empty:
    hs_school = process_school_data(df_school)
    st.header(f"🏫 {dataset_type} - School-level Analysis")
    st.dataframe(hs_school)


# ================= TERM LEVEL =================
if not df_term.empty:
    TUITION_PER_SEM    = 3465
    MAX_YIELD          = 0.6
    semesters_lost_map = {1229:7, 1232:6, 1239:5, 1242:4, 1249:3, 1252:2, 1259:1}

    df_term["semesters_lost"] = df_term["ADMIT_TERM"].map(semesters_lost_map)

    if not df_school.empty:
        df_term = merge_term_category(df_term, hs_school, name_field)

    semester_yield = df_term[
        [name_field, "ADMIT_TERM", "admitted", "enrolled", "semesters_lost"]
    ].copy()

    semester_yield = semester_yield[semester_yield["admitted"] > 0]

    semester_yield["current_yield"]      = semester_yield["enrolled"] / semester_yield["admitted"]
    semester_yield["new_yield"]          = (semester_yield["current_yield"] * (1 + relative_increase)).clip(upper=1)
    semester_yield["expected_enrolled"]  = semester_yield["admitted"] * semester_yield["new_yield"]
    semester_yield["additional_students"] = semester_yield["expected_enrolled"] - semester_yield["enrolled"]
    semester_yield["additional_revenue"] = (
        semester_yield["additional_students"] * semester_yield["semesters_lost"] * TUITION_PER_SEM
    )

    total_additional = semester_yield["additional_revenue"].sum()

    st.header(f"📅 {dataset_type} - Term-level Yield & Revenue")
    st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
    st.dataframe(semester_yield)

    # ================= CATEGORY GRAPH =================
    if "Recruitment_Category" in df_term.columns:
        st.markdown("## 🏷️ Enrollment by Category")

        cat = df_term.groupby("Recruitment_Category").agg(
            enrolled=("enrolled", "sum")
        ).reset_index()

        fig_cat = px.bar(
            cat,
            x="Recruitment_Category",
            y="enrolled",
            color="Recruitment_Category",
            text=cat["enrolled"].apply(lambda x: f"{x:.0f}")
        )

        fig_cat.update_traces(textposition="outside")
        fig_cat.update_layout(showlegend=False)

        st.plotly_chart(fig_cat, use_container_width=True)

    # ================= MAJOR GRAPH =================
    if "MOST_COMMON_PROGRAM" in df_school.columns:

        st.markdown("## 🎓 Most Common Majors")

        df_school_clean = df_school.dropna(subset=["MOST_COMMON_PROGRAM"])

        prog = df_school_clean.groupby("MOST_COMMON_PROGRAM").agg(
            total_enrolled=("enrolled", "sum"),
            school_count=(name_field, "count")
        ).reset_index()

        prog = prog.sort_values("total_enrolled", ascending=False).head(10)

        if not prog.empty:
            fig_prog = px.bar(
                prog,
                x="MOST_COMMON_PROGRAM",
                y="total_enrolled",
                color="total_enrolled",
                text=prog["total_enrolled"].apply(lambda x: f"{x:.0f}")
            )

            fig_prog.update_traces(textposition="outside")
            fig_prog.update_layout(xaxis_tickangle=-45)

            st.plotly_chart(fig_prog, use_container_width=True)
        else:
            st.warning("No valid major data available.")

        # ================= SCHOOL → MAJOR GRAPH =================
        st.markdown("## 🏫 Most Common Major by School")

        school_top_major = df_school_clean[
            [name_field, "MOST_COMMON_PROGRAM", "enrolled", "admitted"]
        ].copy()

        school_top_major = school_top_major[school_top_major["admitted"] > 100]

        top_n = st.slider("Top N Schools (Major Pipeline)", 5, 30, 10)

        school_top_major = school_top_major.sort_values("enrolled", ascending=False).head(top_n)

        if not school_top_major.empty:
            fig_school_major = px.bar(
                school_top_major,
                x=name_field,
                y="enrolled",
                color="MOST_COMMON_PROGRAM",
                text=school_top_major["MOST_COMMON_PROGRAM"]
            )

            fig_school_major.update_traces(textposition="outside")
            fig_school_major.update_layout(xaxis_tickangle=-45)

            st.plotly_chart(fig_school_major, use_container_width=True)
        else:
            st.warning("No school-major data available.")
    # ================= APPLICANTS VS ENROLLED BY CATEGORY =================
    st.markdown("## 📊 Applicants vs Enrolled by Category")

    if "Recruitment_Category" in df_term.columns:

        cat_conv = df_term.groupby("Recruitment_Category").agg(
            applicants=("admitted", "sum"),
            enrolled=("enrolled", "sum")
        ).reset_index()

        cat_conv["conversion_rate"] = cat_conv["enrolled"] / cat_conv["applicants"]

        fig_conv = px.scatter(
            cat_conv,
            x="applicants",
            y="enrolled",
            size="applicants",
            color="Recruitment_Category",
            text="Recruitment_Category",
            hover_data=["conversion_rate"],
            title="Applicants vs Enrolled by Recruitment Category"
        )

        fig_conv.update_traces(textposition="top center")

    st.plotly_chart(fig_conv, use_container_width=True)
    # ================= YIELD GRAPH =================
    st.markdown("## 🏆 Top Schools by Yield Rate")

    school_yield = df_term.groupby(name_field).agg(
        admitted=("admitted", "sum"),
        enrolled=("enrolled", "sum")
    ).reset_index()

    school_yield = school_yield[school_yield["admitted"] > 250]

    school_yield["yield_rate"] = school_yield["enrolled"] / school_yield["admitted"]

    top_n = st.slider("Top N Schools by Yield", 5, 30, 10)

    top_yield = school_yield.sort_values("yield_rate", ascending=False).head(top_n)

    fig_yield = px.bar(
        top_yield,
        x=name_field,
        y="yield_rate",
        text=top_yield["yield_rate"].apply(lambda x: f"{x:.2%}"),
        color="yield_rate"
    )

    fig_yield.update_traces(textposition="outside")
    fig_yield.update_layout(xaxis_tickangle=-45)

    st.plotly_chart(fig_yield, use_container_width=True)


# ================= PROJECTIONS =================
if not df_term.empty:
    df_term["Year"] = df_term["ADMIT_TERM"].map({
        1229:2022, 1232:2023, 1239:2023,
        1242:2024, 1249:2024, 1252:2025, 1259:2025
    })

    df_term = df_term.dropna(subset=["Year"])

    yearly = df_term.groupby([name_field, "Year"]).agg(
        applicants=("admitted", "sum"),
        enrolled=("enrolled", "sum"),
    ).reset_index()

    selected_school = st.selectbox(
        f"Select {dataset_type} School for Projection",
        yearly[name_field].unique()
    )

    school_data = yearly[yearly[name_field] == selected_school].sort_values("Year")

    def calculate_cagr(first, last, years):
        if first <= 0 or years <= 0:
            return 0
        rate = (last / first) ** (1 / years) - 1
        return max(min(rate, 0.25), -0.25)

    if len(school_data) >= 2:
        years_diff = school_data["Year"].iloc[-1] - school_data["Year"].iloc[0]

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

        future_years = [school_data["Year"].iloc[-1] + i for i in range(1, 4)]
        future_apps = [last_app * ((1 + app_growth) ** i) for i in range(1, 4)]
        future_enrolls = [last_enroll * ((1 + enroll_growth) ** i) for i in range(1, 4)]

        fig_app = go.Figure()
        fig_app.add_trace(go.Scatter(
            x=school_data["Year"], y=school_data["applicants"],
            mode="lines+markers", name="Historical Applicants"
        ))
        fig_app.add_trace(go.Scatter(
            x=future_years, y=future_apps,
            mode="lines+markers", name="Projected Applicants",
            line=dict(dash="dash")
        ))
        st.plotly_chart(fig_app, use_container_width=True)

        fig_enroll = go.Figure()
        fig_enroll.add_trace(go.Scatter(
            x=school_data["Year"], y=school_data["enrolled"],
            mode="lines+markers", name="Historical Enrolled"
        ))
        fig_enroll.add_trace(go.Scatter(
            x=future_years, y=future_enrolls,
            mode="lines+markers", name="Projected Enrolled",
            line=dict(dash="dash")
        ))
        st.plotly_chart(fig_enroll, use_container_width=True)

        st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
        st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")

    else:
        st.warning("Not enough historical data for projection.")
