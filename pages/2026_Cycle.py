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
        if row["applicants"] >= vol_thresh and row["bayes_ROI"] >= roi_thresh: return "Flagship"
        elif row["applicants"] < vol_thresh and row["bayes_ROI"] >= roi_thresh: return "Fringe Gem"
        elif row["applicants"] >= vol_thresh and row["bayes_ROI"] < roi_thresh: return "Over-recruited"
        else: return "Low Priority"

    raw["Recruitment_Category"] = raw.apply(classify, axis=1)
    return dict(zip(raw[name_field], raw["Recruitment_Category"]))

# Sidebar
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

# Main
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

dedup_26 = df_26.drop_duplicates(subset=school_col_26).copy()

# ================= COMMUNITY COLLEGE DATA =================
dedup_cc = None

if not is_fresh:
    st.markdown("### 🎯 Community College Analysis")

    show_cc = st.checkbox("Show Community College Analysis")

    if show_cc:
        patterns = ["community college", "comm college", "cc", "c.c.", "county college"]

        def is_cc(name):
            if pd.isna(name): return False
            name = name.lower()
            if any(p in name for p in patterns): return True
            return any(w.endswith("cc") and len(w) <= 6 for w in name.split())

        dedup_cc = dedup_26[dedup_26[school_col_26].apply(is_cc)].copy()

        st.success(f"{len(dedup_cc)} community colleges detected")

# ================= COMMON CALCULATIONS =================
def compute_metrics(df):
    df['Expected_Money_Loss'] = (df['MATRICULATED_COUNT']-df['ADMITTED_COUNT'])*2*3465*0.5
    df["Remaining_Admitted"] = df["ADMITTED_COUNT"] - df["MATRICULATED_COUNT"]
    df["Expected_Additional_Matriculated"] = df["Remaining_Admitted"] * df["MATRIC_PROB"]
    df["Total_Expected_Matriculated"] = df["MATRICULATED_COUNT"] + df["Expected_Additional_Matriculated"]
    return df

dedup_26 = compute_metrics(dedup_26)
if dedup_cc is not None:
    dedup_cc = compute_metrics(dedup_cc)

# ================= FUNCTION TO RENDER DASHBOARD =================
def render_dashboard(df, title_suffix=""):
    st.markdown(f"## 📋 Summary Metrics {title_suffix}")

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Admitted", f"{df['ADMITTED_COUNT'].sum():,.0f}")
    c2.metric("Matriculated", f"{df['MATRICULATED_COUNT'].sum():,.0f}")
    c3.metric("Expected Add", f"{df['Expected_Additional_Matriculated'].sum():,.1f}")
    c4.metric("Total Expected", f"{df['Total_Expected_Matriculated'].sum():,.1f}")

    st.metric("💸 Money Loss", f"${df['Expected_Money_Loss'].sum():,.0f}")

    st.markdown("## 🏷️ Category Analysis")
    cat = df.groupby("Recruitment_Category")["Total_Expected_Matriculated"].sum().reset_index()
    st.plotly_chart(px.bar(cat, x="Recruitment_Category", y="Total_Expected_Matriculated"), use_container_width=True)

    st.markdown("## 📉 Admit vs Yield")
    df_gap = df.copy()
    df_gap["gap"] = df_gap["ADMIT_RATE"] - df_gap["YIELD_RATE"]
    st.plotly_chart(px.bar(df_gap.head(15), x=school_col_26, y="gap"), use_container_width=True)

    st.markdown("## 🎓 Programs")
    prog = df.groupby("MOST_COMMON_PROGRAM_26")["Total_Expected_Matriculated"].sum().reset_index()
    st.plotly_chart(px.bar(prog.head(10), x="MOST_COMMON_PROGRAM_26", y="Total_Expected_Matriculated"), use_container_width=True)

    st.markdown("## 🏫 Table")
    st.dataframe(df.sort_values("Total_Expected_Matriculated", ascending=False), use_container_width=True)

# ================= RENDER =================
render_dashboard(dedup_26)

if dedup_cc is not None and not dedup_cc.empty:
    st.markdown("---")
    st.markdown("# 🏫 Community College Dashboard")
    render_dashboard(dedup_cc, "(Community Colleges)")
