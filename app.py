import streamlit as st
from pymongo import MongoClient

st.set_page_config(page_title="Recruitment Analytics", layout="wide")


# DB

@st.cache_resource
def get_db():
    client = MongoClient(st.secrets["MONGO_URI"])
    return client["test"]

db = get_db()
users_col = db["users"]


# SESSION INIT

for key, default in [("logged_in", False), ("username", ""), ("role", "user")]:
    if key not in st.session_state:
        st.session_state[key] = default

# LOGIN PAGE

if not st.session_state.logged_in:
    st.title("📊 Recruitment Analytics")

    st.markdown("""
    ### Welcome
    Sign in to access:
    - Historical school intelligence
    - 2026 cycle analysis
    - Strategy planning tools
    """)

    with st.form("login_form"):
        uname = st.text_input("Username")
        pwd   = st.text_input("Password", type="password")

        if st.form_submit_button("Login"):
            user = users_col.find_one({"username": uname, "password": pwd})

            if user:
                st.session_state.logged_in = True
                st.session_state.username  = uname
                st.session_state.role      = user.get("role", "user")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.stop()


# MAIN APP HOME
st.title("📊 Recruitment Analytics Dashboard")

st.success(f"Logged in as **{st.session_state.username}**")


# ABOUT SECTION

with st.expander("ℹ️ About This System", expanded=True):
    st.markdown("""
This dashboard is designed to support **university recruitment strategy and forecasting**.

It combines:
- Historical admissions performance (multi-year MongoDB data)
- Current cycle 2026 projections
- Program-level demand insights
- Yield and matriculation modeling

### Core goal:
Help recruitment teams decide:
- Where to invest outreach
- Which schools are high ROI
- Which programs drive enrollment
- Where money is being lost or gained
""")


# HOW TO USE

with st.expander("🧭 How to Use This App", expanded=True):
    st.markdown("""
### Step 1 — Upload Data
Go to sidebar in each page and upload:
- Freshmen_26_categorized.csv
- Transfers_26_categorized.csv

### Step 2 — Choose Analysis Page
- **🏫 Historical Analysis**
  → Understand long-term school performance, ROI, yield patterns

- **🔭 2026 Cycle**
  → Analyze current cycle outcomes:
  - Expected matriculation
  - Money loss estimates
  - Admit vs yield gaps
  - Program demand

- **📌 Strategy**
  → Schedule meetings, upload strategy PDFs, track outreach plans

### Step 3 — Filter & Explore
Use:
- Category filters (Flagship / Fringe / Over-recruited)
- School lookup search
- Program breakdowns
- Yield simulations
""")


# PAGE OVERVIEW (clean navigation)

st.markdown("## 🗂️ Pages Overview")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
### 🏫 Historical
- 3-year + MongoDB intelligence
- Bayesian ROI classification
- School categorization
""")

with col2:
    st.markdown("""
### 🔭 2026 Cycle
- Current admissions cycle
- Expected matriculation
- Money loss estimation
- Program demand
""")

with col3:
    st.markdown("""
### 📌 Strategy
- Calendar scheduling
- Email meeting setup
- Upload strategy documents (PDF/DOCX)
- Team coordination hub
""")

st.markdown("---")

