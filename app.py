import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(layout="wide")
st.title("📊 High School Recruitment Analytics Dashboard")

# ----------------------------
# FILE UPLOAD
# ----------------------------

uploaded_file = st.file_uploader("Upload Freshmen CSV File", type=["csv"])

if uploaded_file is not None:

    df = pd.read_csv(uploaded_file)

    # Keep only relevant HS types
    df = df[df['HS_Type'].isin(['PUBLIC', 'PRIVATE', 'CHARTER'])]

    TUITION_PER_SEM = 3465

    semesters_lost_map = {
        1229: 7,
        1232: 6,
        1239: 5,
        1242: 4,
        1249: 3,
        1252: 2,
        1259: 1,
    }

    df['semesters_lost'] = df['ADMIT_TERM'].map(semesters_lost_map)

    # Encode columns safely
    df['HS_Type'] = df['HS_Type'].replace({"PUBLIC": 0, "PRIVATE": 1, "CHARTER": 2})
    df['admitted'] = df['admitted'].replace({"Y": 1, "N": 0})
    df['matriculated'] = df['matriculated'].replace({"Y": 1, "N": 0})
    df['enrolled'] = df['enrolled'].replace({"Y": 1, "N": 0})

    df[['HS_Type','admitted','matriculated','enrolled']] = \
        df[['HS_Type','admitted','matriculated','enrolled']].astype(int)

    df['HS_GPA'] = pd.to_numeric(df['HS_GPA'], errors="coerce")

    # Money lost calculation
    df['money_lost'] = (
        (df['admitted'] - df['enrolled'])
        * df['semesters_lost']
        * TUITION_PER_SEM
    )

    # ----------------------------
    # HIGH SCHOOL LEVEL METRICS
    # ----------------------------

    applicant_counts = df.groupby('HS_Name').size().rename('applicants')

    hs = (
        df.groupby(['HS_Name','HS_Type','HS_City','HS_State'])
          .agg(
              admitted=('admitted','sum'),
              matriculated=('matriculated','sum'),
              enrolled=('enrolled','sum'),
              HS_quality=('HS_GPA','mean'),
              most_common_program=('Department',
                                   lambda x: x.mode()[0] if not x.mode().empty else None),
              money_lost=('money_lost','sum')
          )
          .join(applicant_counts, on='HS_Name')
          .reset_index()
    )

    hs['yield'] = hs['enrolled'] / hs['admitted']
    hs['specific_yield'] = hs['enrolled'] / hs['matriculated']
    hs['ROI'] = hs['enrolled'] / hs['applicants']
    hs.replace([np.inf, -np.inf], np.nan, inplace=True)

    global_roi = hs['enrolled'].sum() / hs['applicants'].sum()
    k = 5
    hs['bayes_ROI'] = (hs['enrolled'] + global_roi*k) / (hs['applicants'] + k)

    # ----------------------------
    # YIELD SIMULATION
    # ----------------------------

    st.sidebar.header("⚙ Yield Simulation")
    relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10) / 100

    semester_yield = (
        df.groupby(['HS_Name','ADMIT_TERM'])
          .agg(admitted=('admitted','sum'),
               enrolled=('enrolled','sum'),
               semesters_lost=('semesters_lost','first'))
          .reset_index()
    )

    semester_yield = semester_yield[semester_yield['admitted'] > 0]

    semester_yield['new_yield'] = (
        (semester_yield['enrolled'] / semester_yield['admitted'])
        * (1 + relative_increase)
    ).clip(upper=1)

    semester_yield['expected_enrolled'] = \
        semester_yield['admitted'] * semester_yield['new_yield']

    semester_yield['additional_students'] = \
        semester_yield['expected_enrolled'] - semester_yield['enrolled']

    semester_yield['additional_revenue'] = (
        semester_yield['additional_students']
        * semester_yield['semesters_lost']
        * TUITION_PER_SEM
    )

    additional_revenue_hs = (
        semester_yield.groupby('HS_Name')['additional_revenue']
        .sum()
        .reset_index()
    )

    hs = hs.merge(additional_revenue_hs, on='HS_Name', how='left')
    hs['additional_revenue'] = hs['additional_revenue'].fillna(0)

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
    # FILTER + METRICS
    # ----------------------------

    category = st.selectbox(
        "Filter by Recruitment Category",
        ["All"] + list(hs['Recruitment_Category'].unique())
    )

    display_df = hs if category == "All" else \
        hs[hs['Recruitment_Category'] == category]

    st.metric("💰 Total Additional Revenue Potential",
              f"${total_additional:,.0f}")

    st.dataframe(display_df)

    # ============================
    # PROJECTION SECTION
    # ============================

    st.header("📈 3-Year Growth Projection")

    term_to_year = {
        1229: 2022,
        1232: 2023,
        1239: 2023,
        1242: 2024,
        1249: 2024,
        1252: 2025,
        1259: 2025,
    }

    df['Year'] = df['ADMIT_TERM'].map(term_to_year)
    df = df.dropna(subset=['Year'])

    yearly = (
        df.groupby(['HS_Name', 'Year'])
          .agg(
              applicants=('HS_Name', 'count'),
              admitted=('admitted', 'sum'),
              enrolled=('enrolled', 'sum')
          )
          .reset_index()
    )

    if not yearly.empty:

        selected_hs = st.selectbox(
            "Select High School for Projection",
            yearly['HS_Name'].unique()
        )

        hs_data = yearly[yearly['HS_Name'] == selected_hs]\
                  .sort_values('Year')

        def calculate_cagr(first, last, years):
            if first <= 0 or years <= 0:
                return 0
            rate = (last / first) ** (1 / years) - 1
            return max(min(rate, 0.25), -0.25)

        if len(hs_data) >= 2:

            first_year = hs_data['Year'].iloc[0]
            last_year = hs_data['Year'].iloc[-1]
            years_diff = last_year - first_year

            app_growth = calculate_cagr(
                hs_data['applicants'].iloc[0],
                hs_data['applicants'].iloc[-1],
                years_diff
            )

            enroll_growth = calculate_cagr(
                hs_data['enrolled'].iloc[0],
                hs_data['enrolled'].iloc[-1],
                years_diff
            )

            last_app = hs_data['applicants'].iloc[-1]
            last_enroll = hs_data['enrolled'].iloc[-1]

            future_years = [last_year + i for i in range(1, 4)]
            future_apps = [
                last_app * ((1 + app_growth) ** i)
                for i in range(1, 4)
            ]
            future_enrolls = [
                last_enroll * ((1 + enroll_growth) ** i)
                for i in range(1, 4)
            ]

            # Applicant Projection
            fig_app = go.Figure()
            fig_app.add_trace(go.Scatter(
                x=hs_data['Year'],
                y=hs_data['applicants'],
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

            fig_app.update_layout(
                title=f"{selected_hs} - Applicant Projection",
                xaxis_title="Year",
                yaxis_title="Applicants",
                hovermode="x unified"
            )

            st.plotly_chart(fig_app, use_container_width=True)

            # Enrolled Projection
            fig_enroll = go.Figure()
            fig_enroll.add_trace(go.Scatter(
                x=hs_data['Year'],
                y=hs_data['enrolled'],
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

            fig_enroll.update_layout(
                title=f"{selected_hs} - Enrolled Projection",
                xaxis_title="Year",
                yaxis_title="Enrolled",
                hovermode="x unified"
            )

            st.plotly_chart(fig_enroll, use_container_width=True)

            st.write(f"📊 Estimated Applicant Growth: {app_growth*100:.2f}%")
            st.write(f"🎓 Estimated Enrolled Growth: {enroll_growth*100:.2f}%")

else:
    st.info("Please upload a CSV file to begin.")
