import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pymongo import MongoClient

st.set_page_config(layout="wide")
st.title("📊 Recruitment Analytics Dashboard")

# --------------------------------------------------
# CACHED MONGO CONNECTION
# --------------------------------------------------
@st.cache_resource
def get_client():
    return MongoClient(st.secrets["MONGO_URI"])

client = get_client()
db = client["test"]

# --------------------------------------------------
# COLLECTION SELECT
# --------------------------------------------------
collections = db.list_collection_names()
selected_collection = st.selectbox("Select Collection", collections)
collection = db[selected_collection]

# --------------------------------------------------
# FIELD MAP
# --------------------------------------------------
if selected_collection == "Freshmen":
    field_map = {
        "name": "HS_Name",
        "city": "HS_City",
        "state": "HS_State",
        "gpa": "HS_GPA",
        "admitted": "admitted",
        "matriculated": "matriculated",
        "enrolled": "enrolled",
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
        "term": "ADMIT_TERM"
    }

# --------------------------------------------------
# SCHOOL-LEVEL AGGREGATION (Mongo does the work)
# --------------------------------------------------
@st.cache_data(ttl=600)
def get_school_agg(collection_name, field_map):

    pipeline = [
        {
            "$addFields": {
                "admitted_int": {"$cond": [{"$eq": [f"${field_map['admitted']}", "Y"]}, 1, 0]},
                "enrolled_int": {"$cond": [{"$eq": [f"${field_map['enrolled']}", "Y"]}, 1, 0]},
                "matriculated_int": {"$cond": [{"$eq": [f"${field_map['matriculated']}", "Y"]}, 1, 0]},
            }
        },
        {
            "$group": {
                "_id": {
                    "name": f"${field_map['name']}",
                    "city": f"${field_map['city']}",
                    "state": f"${field_map['state']}"
                },
                "applicants": {"$sum": 1},
                "admitted": {"$sum": "$admitted_int"},
                "matriculated": {"$sum": "$matriculated_int"},
                "enrolled": {"$sum": "$enrolled_int"},
                "avg_gpa": {"$avg": f"${field_map['gpa']}"}
            }
        }
    ]

    result = list(db[collection_name].aggregate(pipeline))
    df = pd.json_normalize(result)
    df.rename(columns={
        "_id.name": "name",
        "_id.city": "city",
        "_id.state": "state"
    }, inplace=True)

    return df

hs = get_school_agg(selected_collection, field_map)

if hs.empty:
    st.warning("No data found.")
    st.stop()

# --------------------------------------------------
# DERIVED METRICS (Same Logic)
# --------------------------------------------------
hs["yield"] = hs["enrolled"] / hs["admitted"]
hs["specific_yield"] = hs["enrolled"] / hs["matriculated"]
hs["ROI"] = hs["enrolled"] / hs["applicants"]

global_roi = hs["enrolled"].sum() / hs["applicants"].sum()
k = 5
hs["bayes_ROI"] = (hs["enrolled"] + global_roi*k) / (hs["applicants"] + k)

# --------------------------------------------------
# YIELD SIMULATION (Mongo Aggregated by Term)
# --------------------------------------------------
@st.cache_data(ttl=600)
def get_semester_base(collection_name, field_map):

    pipeline = [
        {
            "$addFields": {
                "admitted_int": {"$cond": [{"$eq": [f"${field_map['admitted']}", "Y"]}, 1, 0]},
                "enrolled_int": {"$cond": [{"$eq": [f"${field_map['enrolled']}", "Y"]}, 1, 0]},
            }
        },
        {
            "$group": {
                "_id": {
                    "name": f"${field_map['name']}",
                    "term": f"${field_map['term']}"
                },
                "admitted": {"$sum": "$admitted_int"},
                "enrolled": {"$sum": "$enrolled_int"}
            }
        }
    ]

    result = list(db[collection_name].aggregate(pipeline))
    df = pd.json_normalize(result)
    df.rename(columns={
        "_id.name": "name",
        "_id.term": "term"
    }, inplace=True)

    return df

semester_base = get_semester_base(selected_collection, field_map)

st.sidebar.header("⚙ Yield Simulation")
relative_increase = st.sidebar.slider("Increase Yield (%)", 0, 50, 10)/100

semester_base = semester_base[semester_base["admitted"] > 0]
semester_base["new_yield"] = (
    semester_base["enrolled"]/semester_base["admitted"]*(1+relative_increase)
).clip(upper=1)

semester_base["expected_enrolled"] = semester_base["admitted"]*semester_base["new_yield"]
semester_base["additional_students"] = semester_base["expected_enrolled"] - semester_base["enrolled"]

additional_revenue_hs = (
    semester_base.groupby("name")["additional_students"]
    .sum()
    .reset_index()
)

hs = hs.merge(additional_revenue_hs, on="name", how="left")
hs["additional_students"] = hs["additional_students"].fillna(0)

total_additional = hs["additional_students"].sum()

# --------------------------------------------------
# CLASSIFICATION
# --------------------------------------------------
vol_thresh = hs["applicants"].mean()
roi_thresh = hs["bayes_ROI"].mean()

def classify(row):
    if row["applicants"] >= vol_thresh and row["bayes_ROI"] >= roi_thresh:
        return "Flagship"
    elif row["applicants"] < vol_thresh and row["bayes_ROI"] >= roi_thresh:
        return "Fringe Gem"
    elif row["applicants"] >= vol_thresh and row["bayes_ROI"] < roi_thresh:
        return "Over-recruited"
    else:
        return "Low Priority"

hs["Recruitment_Category"] = hs.apply(classify, axis=1)

# --------------------------------------------------
# DISPLAY
# --------------------------------------------------
category = st.selectbox("Filter by Recruitment Category",
                        ["All"] + list(hs["Recruitment_Category"].unique()))

display_df = hs if category == "All" else hs[hs["Recruitment_Category"]==category]

st.metric("📈 Additional Students (Simulated)", f"{int(total_additional)}")
st.dataframe(display_df)

# --------------------------------------------------
# YEARLY PROJECTION (Mongo Aggregated)
# --------------------------------------------------
@st.cache_data(ttl=600)
def get_yearly_projection(collection_name, field_map):

    term_to_year = {
        1229: 2022, 1232: 2023, 1239: 2023,
        1242: 2024, 1249: 2024,
        1252: 2025, 1259: 2025
    }

    pipeline = [
        {
            "$addFields": {
                "admitted_int": {"$cond": [{"$eq": [f"${field_map['admitted']}", "Y"]}, 1, 0]},
                "enrolled_int": {"$cond": [{"$eq": [f"${field_map['enrolled']}", "Y"]}, 1, 0]},
                "year": {
                    "$switch": {
                        "branches": [
                            {"case": {"$eq": [f"${field_map['term']}", k]}, "then": v}
                            for k, v in term_to_year.items()
                        ],
                        "default": None
                    }
                }
            }
        },
        {"$match": {"year": {"$ne": None}}},
        {
            "$group": {
                "_id": {"name": f"${field_map['name']}", "year": "$year"},
                "applicants": {"$sum": 1},
                "enrolled": {"$sum": "$enrolled_int"}
            }
        }
    ]

    result = list(db[collection_name].aggregate(pipeline))
    df = pd.json_normalize(result)
    df.rename(columns={"_id.name": "name", "_id.year": "Year"}, inplace=True)
    return df

yearly = get_yearly_projection(selected_collection, field_map)

st.header("📈 3-Year Growth Projection")

selected_school = st.selectbox("Select School", yearly["name"].unique())
school_data = yearly[yearly["name"] == selected_school].sort_values("Year")

if len(school_data) >= 2:

    first = school_data.iloc[0]
    last = school_data.iloc[-1]
    years = last["Year"] - first["Year"]

    growth = (last["enrolled"]/first["enrolled"])**(1/years)-1 if years>0 else 0
    growth = max(min(growth, 0.25), -0.25)

    future_years = [last["Year"]+i for i in range(1,4)]
    future_vals = [last["enrolled"]*((1+growth)**i) for i in range(1,4)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=school_data["Year"],
                             y=school_data["enrolled"],
                             mode="lines+markers",
                             name="Historical"))
    fig.add_trace(go.Scatter(x=future_years,
                             y=future_vals,
                             mode="lines+markers",
                             name="Projected",
                             line=dict(dash="dash")))

    st.plotly_chart(fig, use_container_width=True)
    st.write(f"🎓 Estimated Enrolled Growth: {growth*100:.2f}%")
    
