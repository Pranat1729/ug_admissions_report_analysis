import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")

pd.set_option('future.no_silent_downcasting', True)


uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])
if uploaded_file is not None:
    # Safe to access uploaded_file.name
    filename = uploaded_file.name.lower()

    if "transfer" in filename:
        is_transfer = True
    else:
        is_transfer = False

    if is_transfer:

        field_map = {
            "school": "LAST_COL_UGRD_DESCR",
            "term": "ADMIT_TERM",
            "admitted": "admitted",
            "matriculated": "matriculated",
            "enrolled": "enrolled",
            "gpa": "Coll_GPA",
            "program": "Department",
            "city": "Coll_City",
            "state": "Coll_State",
            # no 'type' field
        }
    else:

        field_map = {
            "school": "HS_Name",
            "term": "ADMIT_TERM",
            "admitted": "admitted",
            "matriculated": "matriculated",
            "enrolled": "enrolled",
            "gpa": "HS_GPA",
            "program": "Department",
            "city": "HS_City",
            "state": "HS_State",
            "type": "HS_Type"  
        }




if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    pd.set_option('future.no_silent_downcasting', True)


    
    # ----------------------------
    # TUITION AND SEMESTER LOSS
    # ----------------------------
    TUITION_PER_SEM = 3465
    semesters_lost_map = {
        1229: 7, 1232: 6, 1239: 5, 1242: 4, 1249: 3, 1252: 2, 1259: 1
    }

    df['semesters_lost'] = df[field_map['term']].map(semesters_lost_map)

 
    df[field_map['admitted']] = df[field_map['admitted']].replace({"Y":1,"N":0}).astype(int)
    df[field_map['matriculated']] = df[field_map['matriculated']].replace({"Y":1,"N":0}).astype(int)
    df[field_map['enrolled']] = df[field_map['enrolled']].replace({"Y":1,"N":0}).astype(int)
    if 'gpa' in field_map:
        df[field_map['gpa']] = df[field_map['gpa']].astype(float)

    # ----------------------------
    # MONEY LOST
    # ----------------------------
    df['money_lost'] = (
        (df[field_map['admitted']] - df[field_map['enrolled']]) *
        df['semesters_lost'] * TUITION_PER_SEM
    )

   
    applicant_counts = df.groupby(field_map['school']).size().rename('applicants')

    hs_groupby_fields = [field_map['school'], field_map['city'], field_map['state']]
    if 'type' in field_map and field_map['type'] in df.columns:
        hs_groupby_fields.insert(1, field_map['type']) 

    hs = (
        df.groupby(hs_groupby_fields)
          .agg(
              admitted=(field_map['admitted'], 'sum'),
              matriculated=(field_map['matriculated'], 'sum'),
              enrolled=(field_map['enrolled'], 'sum'),
              HS_quality=(field_map.get('gpa', field_map['admitted']), 'mean'),
              most_common_program=(field_map['program'], lambda x: x.mode()[0] if not x.mode().empty else None),
              money_lost=('money_lost', 'sum')
          )
          .join(applicant_counts, on=field_map['school'])
          .reset_index()
    )

    # ----------------------------
    # RATIOS AND BAYESIAN METRICS
    # ----------------------------
    hs['yield'] = hs['enrolled'] / hs['admitted']
    hs['specific_yield'] = hs['enrolled'] / hs['matriculated']
    hs['ROI'] = hs['enrolled'] / hs['applicants']
    hs.replace([np.inf, -np.inf], np.nan, inplace=True)

    global_roi = hs['enrolled'].sum() / hs['applicants'].sum()
    k = 5
    hs['bayes_ROI'] = (hs['enrolled'] + global_roi*k) / (hs['applicants'] + k)

    # ----------------------------
    # YIELD INCREASE SIMULATION
    # ----------------------------
    st.sidebar.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10) / 100

    semester_yield = (
        df.groupby([field_map['school'], field_map['term']])
          .agg(
              admitted=(field_map['admitted'],'sum'),
              enrolled=(field_map['enrolled'],'sum'),
              semesters_lost=('semesters_lost','first')
          )
          .reset_index()
    )
    semester_yield = semester_yield[semester_yield['admitted'] > 0]

    semester_yield['new_yield'] = (
        (semester_yield['enrolled'] / semester_yield['admitted']) * (1 + relative_increase)
    ).clip(upper=1)

    semester_yield['expected_enrolled'] = semester_yield['admitted'] * semester_yield['new_yield']
    semester_yield['additional_students'] = semester_yield['expected_enrolled'] - semester_yield['enrolled']

    semester_yield['additional_revenue'] = (
        semester_yield['additional_students'] *
        semester_yield['semesters_lost'] *
        TUITION_PER_SEM
    )

    additional_revenue_hs = (
        semester_yield.groupby(field_map['school'])['additional_revenue']
        .sum()
        .reset_index()
    )

    hs = hs.merge(additional_revenue_hs, on=field_map['school'], how='left')
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
    # CATEGORY FILTER
    # ----------------------------
    category = st.selectbox(
        "Filter by Recruitment Category",
        ["All"] + list(hs['Recruitment_Category'].unique())
    )
    display_df = hs if category == "All" else hs[hs['Recruitment_Category'] == category]

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
        df.groupby([field_map['school'], 'Year'])
          .agg(
              applicants=(field_map['school'], 'count'),
              admitted=(field_map['admitted'], 'sum'),
              enrolled=(field_map['enrolled'], 'sum')
          )
          .reset_index()
    )

    selected_school = st.selectbox("Select School for Projection", yearly[field_map['school']].unique())
    school_data = yearly[yearly[field_map['school']] == selected_school].sort_values('Year')

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

