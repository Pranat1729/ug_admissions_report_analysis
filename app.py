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
    """
    Returns a dict: school_name -> Recruitment_Category
    built from historical MongoDB data. Unknown schools → 'Unclassified'.
    """
    if is_fresh:
        col_name   = "Freshmen"
        name_field = "HS_Name"
    else:
        col_name   = "Transfers"
        name_field = "LAST_COL_UGRD_DESCR"

    raw = pd.DataFrame(list(db[col_name].find({}, {"_id": 0})))
    if raw.empty:
        return {}

    raw["yield"]    = raw["enrolled"] / raw["admitted"]
    raw["ROI"]      = raw["enrolled"] / raw["applicants"]
    raw.replace([np.inf, -np.inf], np.nan, inplace=True)

    global_roi      = raw["enrolled"].sum() / raw["applicants"].sum()
    k               = 5
    raw["bayes_ROI"] = (raw["enrolled"] + global_roi * k) / (raw["applicants"] + k)

    vol_thresh = raw["applicants"].mean()
    roi_thresh = raw["bayes_ROI"].mean()

    def classify(row):
        if   row["applicants"] >= vol_thresh and row["bayes_ROI"] >= roi_thresh: return "Flagship"
        elif row["applicants"] <  vol_thresh and row["bayes_ROI"] >= roi_thresh: return "Fringe Gem"
        elif row["applicants"] >= vol_thresh and row["bayes_ROI"] <  roi_thresh: return "Over-recruited"
        else:                                                                      return "Low Priority"

    raw["Recruitment_Category"] = raw.apply(classify, axis=1)
    return dict(zip(raw[name_field], raw["Recruitment_Category"]))


with st.sidebar:
    st.title("📊 Recruitment Analytics")
    st.success(f"Logged in as **{st.session_state.username}**")
    st.markdown("---")
    st.header("📂 Upload 2026 Files")
    up_fresh = st.file_uploader("Freshmen_26_categorized.csv",  type="csv", key="up_fresh")
    up_trans = st.file_uploader("Transfers_26_categorized.csv", type="csv", key="up_trans")
    st.markdown("---")
    if st.button("Log Out", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username  = ""
        st.session_state.role      = "user"
        st.rerun()
    st.markdown("---")
    st.caption("Bugs? pranat32@gmail.com")


st.title("🔭 2026 Cycle Analysis")

dataset_type  = st.selectbox("Select Dataset Type", ["Freshmen", "Transfers"])
is_fresh      = dataset_type == "Freshmen"
school_col_26 = "LAST_SCH_HS_DESCR" if is_fresh else "LAST_COL_UGRD_DESCR"
uploaded      = up_fresh if is_fresh else up_trans

if uploaded is None:
    st.info(f"Upload **{'Freshmen' if is_fresh else 'Transfers'}_26_categorized.csv** in the sidebar.")
    st.stop()


df_26 = pd.read_csv(uploaded)


category_lookup = load_category_lookup(is_fresh)


df_26["Hist_Category"] = df_26[school_col_26].map(category_lookup).fillna("Unclassified")


if "Recruitment_Category" not in df_26.columns:
    df_26["Recruitment_Category"] = df_26["Hist_Category"]
else:
    # Override with Unclassified where the file has NaN
    df_26["Recruitment_Category"] = df_26["Recruitment_Category"].fillna("Unclassified")

dedup_26 = df_26.drop_duplicates(subset=school_col_26).copy()

# ── Compute remaining matriculation potential ──
dedup_26['Expected_Money_Loss'] = (dedup_26['MATRICULATED_COUNT']-dedup_26['ADMITTED_COUNT'])*2*3465*0.5
dedup_26["Remaining_Admitted"]               = dedup_26["ADMITTED_COUNT"] - dedup_26["MATRICULATED_COUNT"]
dedup_26["Expected_Additional_Matriculated"]  = dedup_26["Remaining_Admitted"] * dedup_26["MATRIC_PROB"]
dedup_26["Total_Expected_Matriculated"]       = dedup_26["MATRICULATED_COUNT"] + dedup_26["Expected_Additional_Matriculated"]


st.markdown("## 📋 Summary Metrics")

total_admitted            = dedup_26["ADMITTED_COUNT"].sum()
total_matriculated        = dedup_26["MATRICULATED_COUNT"].sum()
total_expected_additional = dedup_26["Expected_Additional_Matriculated"].sum()
total_expected_total      = dedup_26["Total_Expected_Matriculated"].sum()
#total_expected_enroll     = dedup_26["Expected_Enrollment"].sum()
total_money_loss          = dedup_26["Expected_Money_Loss"].sum()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Admitted",                    f"{total_admitted:,.0f}")
c2.metric("Already Matriculated",              f"{total_matriculated:,.0f}")
c3.metric("Expected Additional Matriculated",  f"{total_expected_additional:,.1f}")
c4.metric("Total Expected Matriculated",       f"{total_expected_total:,.1f}")

m1, m2, m3 = st.columns(3)
#m1.metric("Expected to Enroll",     f"{total_expected_enroll:,.1f}")
#m2.metric("Expected NOT to Enroll", f"{total_admitted - total_expected_enroll:,.1f}")
m3.metric("💸 Expected Money Loss", f"${total_money_loss:,.0f}")

st.markdown("---")


st.markdown("## 🏷️ Matriculation by Recruitment Category")
st.caption("Categories sourced from historical MongoDB data. New schools not in history are marked **Unclassified**.")

cat_summary = (
    dedup_26.groupby("Recruitment_Category")
            .agg(
                Admitted                    =("ADMITTED_COUNT",                  "sum"),
                Already_Matriculated        =("MATRICULATED_COUNT",              "sum"),
                Expected_Additional         =("Expected_Additional_Matriculated", "sum"),
                Total_Expected_Matriculated =("Total_Expected_Matriculated",      "sum"),
                Expected_Money_Loss         =("Expected_Money_Loss",              "sum"),
            )
            .sort_values("Total_Expected_Matriculated", ascending=False)
            .reset_index()
)

# Total expected matriculation bar
fig_mat = px.bar(
    cat_summary, x="Recruitment_Category", y="Total_Expected_Matriculated",
    color="Recruitment_Category",
    text=cat_summary["Total_Expected_Matriculated"].apply(lambda x: f"{x:.0f}"),
    color_discrete_sequence=px.colors.qualitative.Set2,
    title="Total Expected Matriculation by Recruitment Category",
)
fig_mat.update_traces(textposition="outside")
fig_mat.update_layout(showlegend=False, yaxis_title="Expected Matriculated Students")
st.plotly_chart(fig_mat, use_container_width=True)

# Stacked: already vs additional
fig_stack = px.bar(
    cat_summary,
    x="Recruitment_Category",
    y=["Already_Matriculated", "Expected_Additional"],
    title="Already Matriculated vs Expected Additional by Category",
    labels={"value": "Students", "variable": "Type"},
    color_discrete_map={
        "Already_Matriculated": "#2ecc71",
        "Expected_Additional":  "#3498db",
    },
    barmode="stack",
)
fig_stack.update_layout(xaxis_title="Category", yaxis_title="Students")
st.plotly_chart(fig_stack, use_container_width=True)


fig_loss = px.bar(
    cat_summary.sort_values("Expected_Money_Loss", ascending=False),
    x="Recruitment_Category", y="Expected_Money_Loss",
    color="Recruitment_Category",
    text=cat_summary.sort_values("Expected_Money_Loss", ascending=False)["Expected_Money_Loss"].apply(lambda x: f"${x:,.0f}"),
    color_discrete_sequence=px.colors.qualitative.Pastel,
    title="Expected Money Loss by Recruitment Category",
)
fig_loss.update_traces(textposition="outside")
fig_loss.update_layout(showlegend=False, yaxis_title="Expected Money Loss ($)")
st.plotly_chart(fig_loss, use_container_width=True)

display_cat = cat_summary.copy()
display_cat["Expected_Additional"]          = display_cat["Expected_Additional"].round(1)
display_cat["Total_Expected_Matriculated"]  = display_cat["Total_Expected_Matriculated"].round(1)
display_cat["Expected_Money_Loss"]          = display_cat["Expected_Money_Loss"].apply(lambda x: f"${x:,.0f}")
st.dataframe(display_cat, use_container_width=True, hide_index=True)

st.markdown("---")


st.markdown("## 📉 Admit Rate vs Yield Rate Gap")

df_gap = (
    dedup_26[[school_col_26, "ADMITTED_COUNT", "ADMIT_RATE", "YIELD_RATE", "Recruitment_Category"]]
    .copy()
    .rename(columns={
        "ADMITTED_COUNT":       "applicants",
        "ADMIT_RATE":           "admit_rate",
        "YIELD_RATE":           "yield_rate",
        "Recruitment_Category": "category",
    })
)
df_gap["admit_yield_gap"] = (df_gap["admit_rate"] - df_gap["yield_rate"]).round(4)

col_l, col_r = st.columns(2)
with col_l:
    min_apps = st.slider("Minimum applicants", 1, 50, 5, key="gap_min")
with col_r:
    top_n = st.slider("Top N schools to chart", 5, 50, 15, key="gap_topn")

df_gap_f   = df_gap[df_gap["applicants"] >= min_apps].copy()
df_gap_top = df_gap_f.sort_values("admit_yield_gap", ascending=False).head(top_n)

fig_gap = go.Figure()
fig_gap.add_trace(go.Bar(
    name="Admit Rate", x=df_gap_top[school_col_26],
    y=df_gap_top["admit_rate"], marker_color="#4C78A8",
))
fig_gap.add_trace(go.Bar(
    name="Yield Rate", x=df_gap_top[school_col_26],
    y=df_gap_top["yield_rate"], marker_color="#F58518",
))
fig_gap.update_layout(
    barmode="group",
    title=f"Top {top_n} Schools — Admit vs Yield Rate",
    xaxis_tickangle=-45, yaxis_title="Rate",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_gap, use_container_width=True)

cats    = ["All"] + sorted(df_gap_f["category"].dropna().unique().tolist())
sel_cat = st.selectbox("Filter table by Recruitment Category", cats, key="gap_cat")
if sel_cat != "All":
    df_gap_f = df_gap_f[df_gap_f["category"] == sel_cat]

st.dataframe(
    df_gap_f.sort_values("admit_yield_gap", ascending=False).reset_index(drop=True),
    use_container_width=True, hide_index=True,
)

st.markdown("---")


st.markdown("## 🎓 Program-level Expected Enrollment")

#prog_col = "MOST_COMMON_PROGRAM_26"
#    df_prog  = (
#        dedup_26.groupby(prog_col)
#                .agg(
#                    expected_enrollment =("Expected_Enrollment", "sum"),
#                    avg_yield           =("predicted_avg_yield", "mean"),
#                )
#                .reset_index()
#                .rename(columns={prog_col: "ACAD_PLAN"})
#                .sort_values("expected_enrollment", ascending=False)
#)

#top_prog    = st.slider("Top N programs to chart", 5, 30, 15, key="prog_topn")
#df_prog_top = df_prog.head(top_prog)

#fig_prog = px.bar(
#    df_prog_top, x="ACAD_PLAN", y="expected_enrollment",
#    color="avg_yield", color_continuous_scale="Blues",
#    text=df_prog_top["expected_enrollment"].apply(lambda x: f"{x:.1f}"),
#    title=f"Top {top_prog} Programs by Expected Enrollment",
#    labels={"ACAD_PLAN": "Program", "expected_enrollment": "Expected Enrollment",
#            "avg_yield": "Avg Yield"},
#)
#fig_prog.update_traces(textposition="outside")
#fig_prog.update_layout(xaxis_tickangle=-45)
#st.plotly_chart(fig_prog, use_container_width=True)

#st.dataframe(df_prog.reset_index(drop=True), use_container_width=True, hide_index=True)

st.markdown("---")


st.markdown("## 🏫 School-level Detail")

display_cols = [
    school_col_26, "Recruitment_Category", "Hist_Category",
    "ADMITTED_COUNT", "MATRICULATED_COUNT",
    "Remaining_Admitted", "predicted_matric_prob",
    "Expected_Additional_Matriculated", "Total_Expected_Matriculated",
    "Expected_Enrollment", "Expected_Money_Loss",
]
display_cols = [c for c in display_cols if c in dedup_26.columns]

cat_filter_opts = ["All"] + sorted(dedup_26["Recruitment_Category"].dropna().unique().tolist())
cat_filter      = st.selectbox("Filter by Recruitment Category", cat_filter_opts, key="detail_cat")

df_display = dedup_26 if cat_filter == "All" else dedup_26[dedup_26["Recruitment_Category"] == cat_filter]
df_display = df_display[display_cols].sort_values("Total_Expected_Matriculated", ascending=False).reset_index(drop=True)

for col in ["Expected_Additional_Matriculated", "Total_Expected_Matriculated",
            "Expected_Enrollment", "predicted_matric_prob"]:
    if col in df_display.columns:
        df_display[col] = df_display[col].round(2)

st.dataframe(df_display, use_container_width=True, hide_index=True)
