import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")


client = MongoClient(st.secrets["MONGO_URI"])
db = client["test"]  
collections = db.list_collection_names()
selected_collection = st.selectbox("Select Collection", collections)


df = pd.DataFrame(list(db[selected_collection].find()))

if df.empty:
    st.warning("This collection is empty!")
else:
    st.success(f"Loaded {len(df)} records from `{selected_collection}` collection.")

 
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
            "department": "Department",
            "term": "ADMIT_TERM"
        }
    else:  
        field_map = {
            "name": "LAST_COL_UGRD_DESCR", 
            "city": "Coll_City",
            "state": "Coll_State",
            "gpa": "Coll_GPA",
            "admitted": "admitted",
            "matriculated": "matriculated",
            "enrolled": "enrolled",
            "department": "Department",
            "term": "ADMIT_TERM"
        }

 
    for key, val in list(field_map.items()):
        if val not in df.columns:
            st.warning(f"Column `{val}` not found in this collection; skipping mapping.")
            field_map.pop(key)

    # ----------------------------
    #  METRICS
    # ----------------------------
    TUITION_PER_SEM = 3465
    semesters_lost_map = {1229:7,1232:6,1239:5,1242:4,1249:3,1252:2,1259:1}

    if field_map.get("term"):
        df['semesters_lost'] = df[field_map["term"]].map(semesters_lost_map)

    
    for col in ["admitted","matriculated","enrolled"]:
        if field_map.get(col) and field_map[col] in df.columns:
            df[field_map[col]] = df[field_map[col]].replace({"Y":1,"N":0}).astype(int)

    # Money lost
    df['money_lost'] = (df[field_map["admitted"]] - df[field_map["enrolled"]]) * df['semesters_lost'] * TUITION_PER_SEM

    # Aggregate by school
    group_cols = [field_map.get("name"), field_map.get("city"), field_map.get("state")]
    agg_dict = {
        field_map.get("admitted"): "sum",
        field_map.get("matriculated"): "sum",
        field_map.get("enrolled"): "sum",
        field_map.get("gpa"): "mean",
        "money_lost": "sum"
    }

    if field_map.get("department"):
        agg_dict[field_map["department"]] = lambda x: x.mode()[0] if not x.mode().empty else None

    applicant_counts = df.groupby(field_map.get("name")).size().rename("applicants")

    hs = df.groupby(group_cols).agg(agg_dict).join(applicant_counts, on=field_map.get("name")).reset_index()

    # Ratios
    hs['yield'] = hs[field_map["enrolled"]] / hs[field_map["admitted"]]
    hs['specific_yield'] = hs[field_map["enrolled"]] / hs[field_map["matriculated"]]
    hs['ROI'] = hs[field_map["enrolled"]] / hs['applicants']
    hs.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Bayesian ROI
    global_roi = hs[field_map["enrolled"]].sum() / hs['applicants'].sum()
    k = 5
    hs['bayes_ROI'] = (hs[field_map["enrolled"]] + global_roi*k) / (hs['applicants'] + k)

    # ----------------------------
    # YIELD INCREASE SIMULATION
    # ----------------------------
    st.sidebar.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10)/100

    semester_yield = df.groupby([field_map.get("name"), field_map.get("term")]).agg(
        admitted=(field_map.get("admitted"), "sum"),
        enrolled=(field_map.get("enrolled"), "sum"),
        semesters_lost=('semesters_lost', 'first')
    ).reset_index()

    semester_yield = semester_yield[semester_yield['admitted']>0]
    semester_yield['new_yield'] = (semester_yield['enrolled']/semester_yield['admitted']*(1+relative_increase)).clip(upper=1)
    semester_yield['expected_enrolled'] = semester_yield['admitted']*semester_yield['new_yield']
    semester_yield['additional_students'] = semester_yield['expected_enrolled'] - semester_yield['enrolled']
    semester_yield['additional_revenue'] = semester_yield['additional_students']*semester_yield['semesters_lost']*TUITION_PER_SEM

    additional_revenue_hs = semester_yield.groupby(field_map.get("name"))['additional_revenue'].sum().reset_index()
    hs = hs.merge(additional_revenue_hs, on=field_map.get("name"), how="left")
    total_additional = hs['additional_revenue'].sum()

    # ----------------------------
    # CLASSIFICATION
    # ----------------------------
    vol_thresh = hs['applicants'].mean()
    roi_thresh = hs['bayes_ROI'].mean()

    def classify(row):
        if row['applicants'] >= vol_thresh and row['bayes_ROI'] >= roi_thresh:
            return 'Flagship'
        elif row['applicants'] < vol_thresh and row['bayes_ROI'] >= roi_thresh:
            return 'Fringe Gem'
        elif row['applicants'] >= vol_thresh and row['bayes_ROI'] < roi_thresh:
            return 'Over-recruited'
        else:
            return 'Low Priority'

    hs['Recruitment_Category'] = hs.apply(classify, axis=1)

    # ----------------------------
    # DISPLAY
    # ----------------------------
    category = st.selectbox("Filter by Recruitment Category", ["All"] + list(hs['Recruitment_Category'].unique()))
    if category != "All":
        display_df = hs[hs['Recruitment_Category']==category]
    else:
        display_df = hs

    st.metric("💰 Total Additional Revenue Potential", f"${total_additional:,.0f}")
    st.dataframe(display_df)
    # ----------------------------
    # PROJECTION SECTION
    # ----------------------------
    st.header("📈 3-Year Growth Projection")

    term_to_year = {1229: 2022, 1232: 2023, 1239: 2023, 1242: 2024,
                    1249: 2024, 1252: 2025, 1259: 2025}

    df['Year'] = df[field_map['term']].map(term_to_year)
    df = df.dropna(subset=['Year'])

    yearly = (
        df.groupby([field_map['name'], 'Year'])
          .agg(
              applicants=(field_map['name'], 'count'),
              admitted=(field_map['admitted'], 'sum'),
              enrolled=(field_map['enrolled'], 'sum')
          )
          .reset_index()
    )

    selected_school = st.selectbox("Select School for Projection", yearly[field_map['name']].unique())
    school_data = yearly[yearly[field_map['name']] == selected_school].sort_values('Year')

    def calculate_cagr(first, last, years):
        if first <= 0 or years <= 0:
            return 0
        rate = (last / first) ** (1 / years) - 1
        return max(min(rate, 0.25), -0.25)

    if len(school_data) >= 2:
        first_year = school_data['Year'].iloc[0]
        last_year = school_data['Year'].iloc[-1]
        years_diff = last_year - first_year

        app_growth = calculate_cagr(
            school_data['applicants'].iloc[0],
            school_data['applicants'].iloc[-1],
            years_diff
        )

        enroll_growth = calculate_cagr(
            school_data['enrolled'].iloc[0],
            school_data['enrolled'].iloc[-1],
            years_diff
        )

        last_app = school_data['applicants'].iloc[-1]
        last_enroll = school_data['enrolled'].iloc[-1]

        future_years = []
        future_apps = []
        future_enrolls = []

        for i in range(1, 4):
            future_year = last_year + i
            future_years.append(future_year)
            future_apps.append(last_app * ((1 + app_growth) ** i))
            future_enrolls.append(last_enroll * ((1 + enroll_growth) ** i))

        # ----------------------------
        # APPLICANT PROJECTION (Interactive)
        # ----------------------------
        fig_app = go.Figure()
        fig_app.add_trace(go.Scatter(
            x=school_data['Year'],
            y=school_data['applicants'],
            mode='lines+markers',
            name='Historical Applicants'
        ))
        fig_app.add_trace(go.Scatter(
            x=future_years,
            y=future_apps,
            mode='lines+markers',
            name='Projected Applicants',
            line=dict(dash='dash')
        ))
        fig_app.update_layout(title=f"{selected_school} - Applicant Projection",
                              xaxis_title="Year", yaxis_title="Applicants",
                              hovermode="x unified")
        st.plotly_chart(fig_app, use_container_width=True)

        # ----------------------------
        # ENROLLED PROJECTION 
        # ----------------------------
        fig_enroll = go.Figure()
        fig_enroll.add_trace(go.Scatter(
            x=school_data['Year'],
            y=school_data['enrolled'],
            mode='lines+markers',
            name='Historical Enrolled'
        ))
        fig_enroll.add_trace(go.Scatter(
            x=future_years,
            y=future_enrolls,
            mode='lines+markers',
            name='Projected Enrolled',
            line=dict(dash='dash')
        ))
        fig_enroll.update_layout(title=f"{selected_school} - Enrolled Projection",
                                 xaxis_title="Year", yaxis_title="Enrolled",
                                 hovermode="x unified")
        st.plotly_chart(fig_enroll, use_container_width=True)

        st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
        st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")

