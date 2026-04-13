import streamlit as st
import pandas as pd
import numpy as np
from pymongo import MongoClient

# ================= AUTH =================
if not st.session_state.get("logged_in", False):
    st.warning("Please log in from Home page.")
    st.stop()

# ================= DB =================
@st.cache_resource
def get_db():
    client = MongoClient(st.secrets["MONGO_URI"])
    return client["test"]

db = get_db()


# ================= LOAD HISTORICAL =================
@st.cache_data
def load_history(is_fresh: bool):
    col = "Freshmen" if is_fresh else "Transfers"
    name_field = "HS_Name" if is_fresh else "LAST_COL_UGRD_DESCR"

    df = pd.DataFrame(list(db[col].find({}, {"_id": 0})))
    if df.empty:
        return df, name_field

    df["yield"] = df["enrolled"] / df["admitted"]
    df["roi"] = df["enrolled"] / df["applicants"]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    return df, name_field


# ================= UI =================
st.title("🧠 Recruitment Strategy Engine (v1)")

dataset_type = st.selectbox("Dataset Type", ["Freshmen", "Transfers"])
is_fresh = dataset_type == "Freshmen"

hist_df, name_field = load_history(is_fresh)

uploaded_file = st.file_uploader("Upload 2026 Cycle File (CSV)", type="csv")

if uploaded_file is None:
    st.stop()

cycle_df = pd.read_csv(uploaded_file)


# ================= CLEAN =================
school_col = "LAST_SCH_HS_DESCR" if is_fresh else "LAST_COL_UGRD_DESCR"

cycle_df = cycle_df.copy()
cycle_df["Expected_Money_Loss"] = (
    (cycle_df["MATRICULATED_COUNT"] - cycle_df["ADMITTED_COUNT"])
    * 2 * 3465 * 0.5
)

cycle_df["Remaining_Admitted"] = (
    cycle_df["ADMITTED_COUNT"] - cycle_df["MATRICULATED_COUNT"]
)

cycle_df["Expected_Additional"] = (
    cycle_df["Remaining_Admitted"] * cycle_df["MATRIC_PROB"]
)

cycle_df["Total_Expected_Matriculated"] = (
    cycle_df["MATRICULATED_COUNT"] + cycle_df["Expected_Additional"]
)


# ================= LOOKUP =================
school_name = st.text_input(f"Enter {dataset_type} School / College Name")


def build_strategy(df_hist, df_cycle, school):

    hist_match = df_hist[df_hist[name_field].str.lower() == school.lower()]
    cycle_match = df_cycle[df_cycle[school_col].str.lower() == school.lower()]

    if hist_match.empty and cycle_match.empty:
        return None

    hist = hist_match.iloc[0] if not hist_match.empty else None
    cycle = cycle_match.iloc[0] if not cycle_match.empty else None

    # ---------------- METRICS ----------------
    admitted = cycle["ADMITTED_COUNT"] if cycle is not None else 0
    enrolled = cycle["MATRICULATED_COUNT"] if cycle is not None else 0

    expected_additional = cycle["Expected_Additional"] if cycle is not None else 0
    total_expected = cycle["Total_Expected_Matriculated"] if cycle is not None else 0
    money_loss = cycle["Expected_Money_Loss"] if cycle is not None else 0

    yield_rate = enrolled / admitted if admitted > 0 else 0

    # ---------------- CLASSIFICATION ----------------
    if yield_rate > 0.6:
        status = "Strong Yield School"
    elif yield_rate > 0.4:
        status = "Stable School"
    elif yield_rate > 0.2:
        status = "At Risk School"
    else:
        status = "Critical Loss School"

    # ---------------- PROGRAM ----------------
    if cycle is not None and "MOST_COMMON_PROGRAM_26" in cycle:
        program = cycle["MOST_COMMON_PROGRAM_26"]
    else:
        program = "Unknown"

    # ---------------- STRATEGY RULES ----------------
    strategy = []

    if status == "Strong Yield School":
        strategy.append("Maintain current outreach levels.")
        strategy.append("Focus on premium programs and yield protection.")
        strategy.append("Consider early commitment incentives.")

    elif status == "Stable School":
        strategy.append("Maintain engagement but improve yield conversion.")
        strategy.append("Target high-performing programs for outreach.")
        strategy.append("Monitor admit-yield gap closely.")

    elif status == "At Risk School":
        strategy.append("Increase targeted outreach immediately.")
        strategy.append("Introduce scholarships / incentives.")
        strategy.append("Focus on high-yield programs.")

    else:
        strategy.append("Urgent intervention required.")
        strategy.append("Rebuild pipeline and engagement strategy.")
        strategy.append("Reduce over-reliance on this school.")

    # ---------------- RETURN ----------------
    return {
        "status": status,
        "admitted": admitted,
        "enrolled": enrolled,
        "yield_rate": yield_rate,
        "expected_additional": expected_additional,
        "total_expected": total_expected,
        "money_loss": money_loss,
        "top_program": program,
        "strategy": strategy
    }


# ================= OUTPUT =================
if school_name:

    result = build_strategy(hist_df, cycle_df, school_name)

    if result is None:
        st.warning("No matching school found in dataset.")
    else:

        st.markdown("## 📊 Strategy Overview")

        st.metric("Status", result["status"])
        st.metric("Yield Rate", f"{result['yield_rate']:.2%}")
        st.metric("Expected Money Loss", f"${result['money_loss']:,.0f}")
        st.metric("Top Program", result["top_program"])

        st.markdown("## 🧠 Recommended Strategy")

        for i, s in enumerate(result["strategy"], 1):
            st.write(f"{i}. {s}")

        st.markdown("---")

        st.markdown("## 📌 Raw Values")
        st.json(result)
