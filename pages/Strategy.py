import streamlit as st
import pandas as pd
from datetime import datetime
from pymongo import MongoClient
from gridfs import GridFS
from streamlit_calendar import calendar
import smtplib
from email.mime.text import MIMEText


if not st.session_state.get("logged_in", False):
    st.warning("Please log in from the Home page.")
    st.stop()


@st.cache_resource
def get_db():
    client = MongoClient(st.secrets["MONGO_URI"])
    return client["test"]

db = get_db()
fs = GridFS(db)

st.title("📌 Strategy Management")

#### CALENDAR ######## 


st.markdown("## 🗓️ Strategy Calendar")

try:
    meetings = list(db["strategy_meetings"].find({}, {"_id": 0}))
except:
    meetings = []
    st.error("⚠️ Could not load meetings")

if not meetings:
    st.info("No meetings yet — click a date to schedule one.")

events = []
for m in meetings:
    if m.get("date") and m.get("time"):
        events.append({
            "title": m.get("school_name", "Unknown"),
            "start": f"{m['date']}T{m['time']}",
            "color": "#2ecc71" if m.get("status") == "confirmed" else "#f39c12",
        })

calendar_options = {
    "initialView": "dayGridMonth",
    "selectable": True,
    "height": 650,
}

calendar_data = calendar(events=events, options=calendar_options)


selected_date = None
if calendar_data.get("dateClick"):
    selected_date = calendar_data["dateClick"]["date"]

if calendar_data.get("select"):
    selected_date = calendar_data["select"]["start"]

if selected_date:
    st.session_state["selected_date"] = selected_date

###### MEETING #######

st.markdown("### ➕ Schedule Strategy Meeting")

default_date = st.session_state.get("selected_date")

school_name = st.text_input("School Name")

col1, col2 = st.columns(2)

with col1:
    meeting_date = st.date_input(
        "Date",
        value=pd.to_datetime(default_date) if default_date else None
    )

with col2:
    meeting_time = st.time_input("Time")

status = st.selectbox("Status", ["pending", "confirmed"])
recipient_email = st.text_input("Recipient Email (optional)")

if st.button("Add Meeting"):

    if school_name and meeting_date and meeting_time:

        existing = db["strategy_meetings"].find_one({
            "date": str(meeting_date),
            "time": str(meeting_time)
        })

        if existing:
            st.error("⚠️ Time slot already booked.")
        else:
            db["strategy_meetings"].insert_one({
                "school_name": school_name,
                "date": str(meeting_date),
                "time": str(meeting_time),
                "status": status,
                "created_at": datetime.now()
            })

            st.success("✅ Meeting scheduled!")

            
            if recipient_email:
                try:
                    msg = MIMEText(f"""Strategy Meeting Scheduled School: {school_name} Date: {meeting_date} Time: {meeting_time} """)
                    msg["Subject"] = f"Strategy Meeting - {school_name}"
                    msg["From"] = st.secrets["GMAIL"]
                    msg["To"] = recipient_email

                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login(st.secrets["GMAIL"], st.secrets["PASSWORD"])
                    server.send_message(msg)
                    server.quit()

                    st.success("📨 Email sent!")

                except Exception as e:
                    st.warning(f"Email failed: {e}")

            st.rerun()

    else:
        st.warning("Please fill all fields.")

# EVENT DETAILS 

st.markdown("### 🔍 Event Details")

if calendar_data.get("eventClick"):
    event = calendar_data["eventClick"]["event"]

    st.info(f"""
**School:** {event.get('title')}  
**Start:** {event.get('start')}  
""")

    if st.button("🗑️ Delete This Event"):
        db["strategy_meetings"].delete_one({
            "school_name": event.get("title"),
            "date": event.get("start").split("T")[0]
        })
        st.rerun()


##### FILE UPLOAD #######


st.markdown("## 📂 Upload Strategy Document")

school_upload = st.text_input("School Name for Upload")
uploaded_file = st.file_uploader("Upload File", type=["pdf", "docx"])

if st.button("Upload File"):

    if uploaded_file and school_upload:

        file_id = fs.put(
            uploaded_file.read(),
            filename=uploaded_file.name,
            school_name=school_upload
        )

        db["strategy_files"].insert_one({
            "school_name": school_upload,
            "filename": uploaded_file.name,
            "file_id": file_id,
            "upload_date": datetime.now()
        })

        st.success("✅ File uploaded!")

    else:
        st.warning("Provide school name + file.")

##### FILE VIEW ##########


st.markdown("## 📚 View Strategy Documents")

school_lookup = st.text_input("Enter School Name")

if school_lookup:

    
    files = list(db["strategy_files"].find({
        "school_name": {"$regex": f"^{school_lookup}$", "$options": "i"}
    }))

    if files:

        for f in files:
            st.write(f"📄 {f['filename']} — {f['upload_date']}")

            try:
                file_data = fs.get(f["file_id"]).read()

                st.download_button(
                    label=f"Download {f['filename']}",
                    data=file_data,
                    file_name=f["filename"]
                )

                if st.button(f"Delete {f['filename']}"):
                    fs.delete(f["file_id"])
                    db["strategy_files"].delete_one({"file_id": f["file_id"]})
                    st.rerun()

            except:
                st.error("⚠️ File missing or corrupted")

    else:
        st.info("No strategy documents found.")
