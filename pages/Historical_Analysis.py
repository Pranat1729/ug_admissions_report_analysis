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


if not df_school.empty:
    hs_school = process_school_data(df_school)
    st.header(f"🏫 {dataset_type} - School-level Analysis")
    st.dataframe(hs_school)


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
    semester_yield["new_yield"]           = (semester_yield["current_yield"] * (1 + relative_increase)).clip(upper=1)
    semester_yield["expected_enrolled"]   = semester_yield["admitted"] * semester_yield["new_yield"]
    semester_yield["additional_students"] = semester_yield["expected_enrolled"] - semester_yield["enrolled"]
    semester_yield["additional_revenue"]  = (
        semester_yield["additional_students"] * semester_yield["semesters_lost"] * TUITION_PER_SEM
    )

    total_additional = semester_yield["additional_revenue"].sum()

    st.header(f"📅 {dataset_type} - Term-level Yield & Revenue")
    st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
    st.dataframe(semester_yield)

    df_term["max_realistic_enrolled"] = df_term["admitted"] * MAX_YIELD
    df_term["realistic_gap"]          = (df_term["max_realistic_enrolled"] - df_term["enrolled"]).clip(lower=0)
    df_term["realistic_money_lost"]   = df_term["realistic_gap"] * df_term["semesters_lost"] * TUITION_PER_SEM

    st.metric("💰 Total Money Lost (historical max yield 60%)", f"${df_term['realistic_money_lost'].sum():,.0f}")

    if "Recruitment_Category" in df_term.columns:
        category_options  = ["All"] + sorted(df_term["Recruitment_Category"].dropna().unique())
        selected_category = st.selectbox("Select Recruitment Category", category_options)
        df_filtered = df_term if selected_category == "All" else df_term[df_term["Recruitment_Category"] == selected_category].copy()
        if not df_filtered.empty:
            st.metric(f"💰 Total Money Lost ({selected_category})", f"${df_filtered['realistic_money_lost'].sum():,.0f}")


if not df_term.empty:
    df_term["Year"] = df_term["ADMIT_TERM"].map({
        1229:2022, 1232:2023, 1239:2023,
        1242:2024, 1249:2024, 1252:2025, 1259:2025
    })
    df_term = df_term.dropna(subset=["Year"])

    yearly = df_term.groupby([name_field, "Year"]).agg(
        applicants=("admitted", "sum"),
        admitted  =("admitted", "sum"),
        enrolled  =("enrolled", "sum"),
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
        years_diff    = school_data["Year"].iloc[-1] - school_data["Year"].iloc[0]
        app_growth    = calculate_cagr(school_data["applicants"].iloc[0], school_data["applicants"].iloc[-1], years_diff)
        enroll_growth = calculate_cagr(school_data["enrolled"].iloc[0],   school_data["enrolled"].iloc[-1],   years_diff)

        last_app    = school_data["applicants"].iloc[-1]
        last_enroll = school_data["enrolled"].iloc[-1]
        future_years   = [school_data["Year"].iloc[-1] + i for i in range(1, 4)]
        future_apps    = [last_app    * ((1 + app_growth)    ** i) for i in range(1, 4)]
        future_enrolls = [last_enroll * ((1 + enroll_growth) ** i) for i in range(1, 4)]

        fig_app = go.Figure()
        fig_app.add_trace(go.Scatter(x=school_data["Year"], y=school_data["applicants"],
                                      mode="lines+markers", name="Historical Applicants"))
        fig_app.add_trace(go.Scatter(x=future_years, y=future_apps,
                                      mode="lines+markers", name="Projected Applicants",
                                      line=dict(dash="dash")))
        st.plotly_chart(fig_app, use_container_width=True)

        fig_enroll = go.Figure()
        fig_enroll.add_trace(go.Scatter(x=school_data["Year"], y=school_data["enrolled"],
                                         mode="lines+markers", name="Historical Enrolled"))
        fig_enroll.add_trace(go.Scatter(x=future_years, y=future_enrolls,
                                         mode="lines+markers", name="Projected Enrolled",
                                         line=dict(dash="dash")))
        st.plotly_chart(fig_enroll, use_container_width=True)

        st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
        st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")
    else:
        st.warning("Not enough historical data for projection.")


# ================================================================
# 26-CYCLE CHARTS (from code piece 1)
# Requires school-level data with MATRIC_PROB, ADMITTED_COUNT,
# MATRICULATED_COUNT, ADMIT_RATE, YIELD_RATE, MOST_COMMON_PROGRAM_26
# ================================================================
st.markdown("---")
st.header(f"🔭 26-Cycle Matriculation Analysis")

up_key   = "up_fresh_p2" if dataset_type == "Freshmen" else "up_trans_p2"
uploaded = st.file_uploader(
    f"Upload {dataset_type}_26_categorized.csv",
    type="csv",
    key=up_key
)

if uploaded is not None:
    df_26 = pd.read_csv(uploaded)
    school_col_26 = "LAST_SCH_HS_DESCR" if dataset_type == "Freshmen" else "LAST_COL_UGRD_DESCR"

    # Attach hist category if available
    if not df_school.empty:
        cat_lookup = dict(zip(hs_school[name_field], hs_school["Recruitment_Category"]))
        df_26["Hist_Category"] = df_26[school_col_26].map(cat_lookup).fillna("Unclassified")
        if "Recruitment_Category" not in df_26.columns:
            df_26["Recruitment_Category"] = df_26["Hist_Category"]
        else:
            df_26["Recruitment_Category"] = df_26["Recruitment_Category"].fillna("Unclassified")

    # Dedup to one row per school
    dedup_26 = df_26.drop_duplicates(subset=school_col_26).copy()

    # Compute matriculation fields (same logic as code piece 1)
    if "MATRIC_PROB" in dedup_26.columns:
        dedup_26["Remaining_Admitted"]             = dedup_26["ADMITTED_COUNT"] - dedup_26["MATRICULATED_COUNT"]
        dedup_26["Expected_Additional_Matriculated"] = dedup_26["Remaining_Admitted"] * dedup_26["MATRIC_PROB"]
        dedup_26["Expected_Matriculation"]           = dedup_26["MATRICULATED_COUNT"] + dedup_26["Expected_Additional_Matriculated"]
        dedup_26["Expected_Money_Loss"]              = (dedup_26["MATRICULATED_COUNT"] - dedup_26["ADMITTED_COUNT"]) * 2 * 3465 * 0.5

    # ---------- SUMMARY METRICS ----------
    st.markdown("### 📋 Summary Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Admitted",        f"{dedup_26['ADMITTED_COUNT'].sum():,.0f}")
    c2.metric("Already Matriculated",  f"{dedup_26['MATRICULATED_COUNT'].sum():,.0f}")
    if "Expected_Additional_Matriculated" in dedup_26.columns:
        c3.metric("Expected Additional",   f"{dedup_26['Expected_Additional_Matriculated'].sum():,.1f}")
        c4.metric("Expected Matriculation",f"{dedup_26['Expected_Matriculation'].sum():,.1f}")
        st.metric("💸 Expected Money Loss", f"${dedup_26['Expected_Money_Loss'].sum():,.0f}")

    st.markdown("---")

    # ---------- CATEGORY: total expected matriculation ----------
    if "Recruitment_Category" in dedup_26.columns and "Expected_Matriculation" in dedup_26.columns:
        st.markdown("### 🏷️ Matriculation by Category")

        cat = dedup_26.groupby("Recruitment_Category").agg(
            Already   =("MATRICULATED_COUNT",              "sum"),
            Additional=("Expected_Additional_Matriculated","sum"),
            Total     =("Expected_Matriculation",          "sum")
        ).reset_index()

        fig_cat = px.bar(
            cat,
            x="Recruitment_Category",
            y="Total",
            color="Recruitment_Category",
            text=cat["Total"].apply(lambda x: f"{x:.0f}"),
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_cat.update_traces(textposition="outside")
        fig_cat.update_layout(showlegend=False)
        st.plotly_chart(fig_cat, use_container_width=True)

        # Stacked: already vs additional
        fig_stack = px.bar(
            cat,
            x="Recruitment_Category",
            y=["Already", "Additional"],
            barmode="stack",
            color_discrete_map={"Already": "#2ecc71", "Additional": "#3498db"}
        )
        st.plotly_chart(fig_stack, use_container_width=True)

    # ---------- ADMIT VS YIELD ----------
    if "ADMIT_RATE" in dedup_26.columns and "YIELD_RATE" in dedup_26.columns:
        st.markdown("### 📉 Admit vs Yield Rate")

        fig_gap = go.Figure()
        fig_gap.add_trace(go.Bar(x=dedup_26[school_col_26], y=dedup_26["ADMIT_RATE"], name="Admit Rate"))
        fig_gap.add_trace(go.Bar(x=dedup_26[school_col_26], y=dedup_26["YIELD_RATE"], name="Yield Rate"))
        fig_gap.update_layout(barmode="group", xaxis_tickangle=-45)
        st.plotly_chart(fig_gap, use_container_width=True)

    # ---------- PROGRAMS ----------
    if "MOST_COMMON_PROGRAM_26" in dedup_26.columns and "Expected_Matriculation" in dedup_26.columns:
        st.markdown("### 🎓 Programs")

        prog = dedup_26.groupby("MOST_COMMON_PROGRAM_26")["Expected_Matriculation"].sum().reset_index()
        fig_prog = px.bar(
            prog.sort_values("Expected_Matriculation", ascending=False).head(10),
            x="MOST_COMMON_PROGRAM_26",
            y="Expected_Matriculation",
            color="Expected_Matriculation",
            color_continuous_scale="Blues",
            text_auto=".1f"
        )
        fig_prog.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_prog, use_container_width=True)

    # ---------- TOP SCHOOLS ----------
    if "Expected_Matriculation" in dedup_26.columns:
        st.markdown("### 🏆 Top Schools by Expected Matriculation")

        top_n = st.slider("Top N Schools", 5, 50, 15, key="top_n_p2")
        top   = dedup_26.sort_values("Expected_Matriculation", ascending=False).head(top_n)

        fig_top = px.bar(
            top,
            x=school_col_26,
            y="Expected_Matriculation",
            text=top["Expected_Matriculation"].apply(lambda x: f"{x:.0f}"),
            color="Expected_Matriculation",
            color_continuous_scale="Viridis",
        )
        fig_top.update_traces(textposition="outside")
        fig_top.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_top, use_container_width=True)
        st.dataframe(top, use_container_width=True, hide_index=True)

    # ---------- FULL TABLE ----------
    st.markdown("### 🏫 Full Table")
    sort_col = "Expected_Matriculation" if "Expected_Matriculation" in dedup_26.columns else school_col_26
    st.dataframe(
        dedup_26.sort_values(sort_col, ascending=False),
        use_container_width=True
    )
