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
def load_category_lookup(is_fresh: bool) -> dict:
    if is_fresh:
        col_name, name_field = "Freshmen", "HS_Name"
    else:
        col_name, name_field = "Transfers", "LAST_COL_UGRD_DESCR"

    raw = pd.DataFrame(list(db[col_name].find({}, {"_id": 0})))
    if raw.empty:
        return {}

    raw["yield"] = raw["enrolled"] / raw["admitted"]
    raw["ROI"] = raw["enrolled"] / raw["applicants"]
    raw.replace([np.inf, -np.inf], np.nan, inplace=True)

    global_roi = raw["enrolled"].sum() / raw["applicants"].sum()
    k = 5
    raw["bayes_ROI"] = (raw["enrolled"] + global_roi * k) / (raw["applicants"] + k)

    vol_thresh = raw["applicants"].mean()
    roi_thresh = raw["bayes_ROI"].mean()

    def classify(row):
        if row["applicants"] >= vol_thresh and row["bayes_ROI"] >= roi_thresh:
            return "Flagship"
        elif row["applicants"] < vol_thresh and row["bayes_ROI"] >= roi_thresh:
            return "Fringe Gem"
        elif row["applicants"] >= vol_thresh and row["bayes_ROI"] < roi_thresh:
            return "Over-recruited"
        else:
            return "Low Priority"

    raw["Recruitment_Category"] = raw.apply(classify, axis=1)
    return dict(zip(raw[name_field], raw["Recruitment_Category"]))

# ================= SIDEBAR =================
with st.sidebar:
    st.title("📊 Recruitment Analytics")
    st.success(f"Logged in as **{st.session_state.username}**")
    st.markdown("---")
    st.header("📂 Upload 2026 Files")
    up_fresh = st.file_uploader("Freshmen_26_categorized.csv", type="csv")
    up_trans = st.file_uploader("Transfers_26_categorized.csv", type="csv")
    st.markdown("---")
    if st.button("Log Out"):
        st.session_state.logged_in = False
        st.rerun()

# ================= MAIN =================
st.title("🔭 2026 Cycle Analysis")

dataset_type = st.selectbox("Select Dataset Type", ["Freshmen", "Transfers"])
is_fresh = dataset_type == "Freshmen"
school_col_26 = "LAST_SCH_HS_DESCR" if is_fresh else "LAST_COL_UGRD_DESCR"
uploaded = up_fresh if is_fresh else up_trans

if uploaded is None:
    st.stop()

df_26 = pd.read_csv(uploaded)
category_lookup = load_category_lookup(is_fresh)

df_26["Hist_Category"] = df_26[school_col_26].map(category_lookup).fillna("Unclassified")

if "Recruitment_Category" not in df_26.columns:
    df_26["Recruitment_Category"] = df_26["Hist_Category"]
else:
    df_26["Recruitment_Category"] = df_26["Recruitment_Category"].fillna("Unclassified")

# ================= PROPER AGGREGATION (NO EMPLID) =================
agg_dict = {
    "ADMITTED_COUNT": "sum",
    "MATRICULATED_COUNT": "sum",
    "MATRIC_PROB": "mean",
    "ADMIT_RATE": "mean",
    "YIELD_RATE": "mean",
    "MOST_COMMON_PROGRAM_26": "first",
    "Recruitment_Category": "first",
    "Hist_Category": "first"
}

dedup_26 = (
    df_26.groupby(school_col_26)
         .agg(agg_dict)
         .reset_index()
)

# ================= COMMUNITY COLLEGES =================
dedup_cc = None

if not is_fresh:
    st.markdown("### 🎯 Community College Analysis")
    show_cc = st.checkbox("Show Community College Analysis")

    if show_cc:
        patterns = ["community college", "comm college", "cc", "c.c.", "county college"]

        def is_cc(name):
            if pd.isna(name):
                return False
            name = name.lower()
            if any(p in name for p in patterns):
                return True
            return any(w.endswith("cc") and len(w) <= 6 for w in name.split())

        dedup_cc = dedup_26[dedup_26[school_col_26].apply(is_cc)].copy()

# ================= METRICS =================
def compute(df):
    df['Expected_Money_Loss'] = (df['MATRICULATED_COUNT'] - df['ADMITTED_COUNT']) * 2 * 3465 * 0.5
    df["Remaining_Admitted"] = df["ADMITTED_COUNT"] - df["MATRICULATED_COUNT"]
    df["Expected_Additional_Matriculated"] = df["Remaining_Admitted"] * df["MATRIC_PROB"]
    df["Expected_Matriculation"] = df["MATRICULATED_COUNT"] + df["Expected_Additional_Matriculated"]
    return df

dedup_26 = compute(dedup_26)
if dedup_cc is not None:
    dedup_cc = compute(dedup_cc)

# ================= DASHBOARD =================
def render_dashboard(df, title=""):

    st.markdown(f"# {title}")

    # ---------- SUMMARY ----------
    st.markdown("## 📋 Summary Metrics")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Admitted", f"{df['ADMITTED_COUNT'].sum():,.0f}")
    c2.metric("Already Matriculated", f"{df['MATRICULATED_COUNT'].sum():,.0f}")
    c3.metric("Expected Additional", f"{df['Expected_Additional_Matriculated'].sum():,.1f}")
    c4.metric("Expected Matriculation", f"{df['Expected_Matriculation'].sum():,.1f}")

    st.metric("💸 Expected Money Loss", f"${df['Expected_Money_Loss'].sum():,.0f}")

    st.markdown("---")

    # ---------- CATEGORY ----------
    st.markdown("## 🏷️ Matriculation by Category")

    cat = df.groupby("Recruitment_Category").agg(
        Already=("MATRICULATED_COUNT", "sum"),
        Additional=("Expected_Additional_Matriculated", "sum"),
        Total=("Expected_Matriculation", "sum")
    ).reset_index()

    fig = px.bar(
        cat,
        x="Recruitment_Category",
        y="Total",
        color="Recruitment_Category",
        text=cat["Total"].apply(lambda x: f"{x:.0f}"),
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    fig_stack = px.bar(
        cat,
        x="Recruitment_Category",
        y=["Already", "Additional"],
        barmode="stack",
        color_discrete_map={"Already": "#2ecc71", "Additional": "#3498db"}
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # ---------- ADMIT vs YIELD ----------
    st.markdown("## 📉 Admit vs Yield")

    fig_gap = go.Figure()
    fig_gap.add_trace(go.Bar(x=df[school_col_26], y=df["ADMIT_RATE"], name="Admit Rate"))
    fig_gap.add_trace(go.Bar(x=df[school_col_26], y=df["YIELD_RATE"], name="Yield Rate"))
    fig_gap.update_layout(barmode="group", xaxis_tickangle=-45)

    st.plotly_chart(fig_gap, use_container_width=True)

    # ---------- PROGRAMS ----------
    st.markdown("## 🎓 Programs")

    prog = df.groupby("MOST_COMMON_PROGRAM_26")["Expected_Matriculation"].sum().reset_index()

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
    st.markdown("## 🏆 Top Schools by Expected Matriculation")

    top_n = st.slider(f"Top N Schools ({title})", 5, 50, 15, key=f"top_{title}")

    top = (
        df.sort_values("Expected_Matriculation", ascending=False)
          .head(top_n)
    )

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

    # ---------- TABLE ----------
    st.markdown("## 🏫 Full Table")

    st.dataframe(
        df.sort_values("Expected_Matriculation", ascending=False),
        use_container_width=True
    )

# ================= RENDER =================
render_dashboard(dedup_26, "All Transfers / Dataset")

if dedup_cc is not None and not dedup_cc.empty:
    st.markdown("---")
    render_dashboard(dedup_cc, "Community Colleges Only")
