import streamlit as st
import pandas as pd
from datetime import datetime, date
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

st.title("📌 Recruitment Strategy")


st.markdown("## 🔔 Upcoming Meetings")

today = str(date.today())

try:
    meetings_all = list(db["strategy_meetings"].find({}, {"_id": 0}))
except:
    meetings_all = []

today_meetings = [m for m in meetings_all if m.get("date") == today]

if today_meetings:
    for m in today_meetings:
        st.warning(f"📅 Today: {m.get('purpose', 'Meeting')} with {m.get('contact', '')} at {m['time']}")
else:
    st.info("No meetings today.")


st.markdown("## 🗓️ Recruitment Calendar")

events = []
for m in meetings_all:
    if m.get("date") and m.get("time"):
        color = "#2ecc71" if m.get("status") == "confirmed" else "#f39c12"
        if m.get("status") == "completed":
            color = "#95a5a6"

        label = m.get("purpose", "Meeting")
        if m.get("contact"):
            label += f" — {m['contact']}"

        events.append({
            "title": label,
            "start": f"{m['date']}T{m['time']}",
            "color": color,
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



st.markdown("### ➕ Schedule Meeting")

default_date = st.session_state.get("selected_date")

purpose = st.text_input("Purpose", placeholder="e.g. Intro Call, Follow-up, Campus Visit")
contact = st.text_input("Contact / Organization", placeholder="e.g. John Smith, Acme Corp, MIT")
meeting_type = st.selectbox("Meeting Type", ["In-Person", "Virtual", "Phone Call", "Campus Visit", "Other"])

col1, col2 = st.columns(2)
with col1:
    meeting_date = st.date_input(
        "Date",
        value=pd.to_datetime(default_date) if default_date else None
    )
with col2:
    meeting_time = st.time_input("Time")

status = st.selectbox("Status", ["pending", "confirmed", "completed"])
assigned_to = st.text_input("Assigned To (optional)")
recipient_email = st.text_input("Recipient Email (optional)")

if st.button("Add Meeting"):
    if purpose and contact and meeting_date and meeting_time:

        existing = db["strategy_meetings"].find_one({
            "date": str(meeting_date),
            "time": str(meeting_time)
        })

        if existing:
            st.error("⚠️ Time slot already booked.")
        else:
            db["strategy_meetings"].insert_one({
                "purpose": purpose,
                "contact": contact,
                "meeting_type": meeting_type,
                "date": str(meeting_date),
                "time": str(meeting_time),
                "status": status,
                "assigned_to": assigned_to,
                "created_at": datetime.now()
            })

            st.success("✅ Meeting scheduled!")

            if recipient_email:
                try:
                    msg = MIMEText(f"""
Recruitment Meeting Scheduled

Purpose: {purpose}
Contact / Organization: {contact}
Type: {meeting_type}
Date: {meeting_date}
Time: {meeting_time}
Assigned To: {assigned_to}
""")
                    msg["Subject"] = f"Recruitment Meeting — {purpose} with {contact}"
                    msg["From"] = "ugrecruitmentBC@gmail.com"
                    msg["To"] = recipient_email

                    server = smtplib.SMTP("smtp.gmail.com", 587)
                    server.starttls()
                    server.login("ugrecruitmentBC@gmail.com", "wstpluqfccswzhxe")
                    server.send_message(msg)
                    server.quit()

                    st.success("📨 Email sent!")

                except Exception as e:
                    st.warning(f"Email failed: {e}")

            st.rerun()

    else:
        st.warning("Please fill in Purpose, Contact, Date, and Time.")



st.markdown("### 🔍 Event Details")

if calendar_data.get("eventClick"):
    event = calendar_data["eventClick"]["event"]
    title_parts = event.get("title", "").split(" — ")
    event_purpose = title_parts[0] if title_parts else ""
    event_contact = title_parts[1] if len(title_parts) > 1 else ""

    st.info(f"""
**Purpose:** {event_purpose}  
**Contact / Org:** {event_contact}  
**Start:** {event.get('start')}  
""")

    new_status = st.selectbox("Update Status", ["pending", "confirmed", "completed"])

    if st.button("Update Status"):
        db["strategy_meetings"].update_one(
            {
                "purpose": event_purpose,
                "date": event.get("start", "").split("T")[0]
            },
            {"$set": {"status": new_status}}
        )
        st.success("Status updated!")
        st.rerun()

    if st.button("🗑️ Delete This Event"):
        db["strategy_meetings"].delete_one({
            "purpose": event_purpose,
            "date": event.get("start", "").split("T")[0]
        })
        st.rerun()



st.markdown("## 🎯 Meeting Strategy")

st.caption("Look up any scheduled meeting to add priority, notes, and ownership.")

col1, col2 = st.columns(2)
with col1:
    lookup_purpose = st.text_input("Purpose", key="strat_purpose")
with col2:
    lookup_contact = st.text_input("Contact / Organization", key="strat_contact")

if lookup_purpose or lookup_contact:
    query = {}
    if lookup_purpose:
        query["purpose"] = {"$regex": lookup_purpose.strip(), "$options": "i"}
    if lookup_contact:
        query["contact"] = {"$regex": lookup_contact.strip(), "$options": "i"}

    strategy_doc = db["meeting_strategy"].find_one(query)

    priority = st.selectbox(
        "Priority",
        ["High", "Medium", "Low"],
        index=0 if not strategy_doc else ["High", "Medium", "Low"].index(strategy_doc.get("priority", "High"))
    )

    assigned = st.text_input(
        "Assigned To",
        value="" if not strategy_doc else strategy_doc.get("assigned_to", "")
    )

    notes = st.text_area(
        "Strategy Notes",
        value="" if not strategy_doc else strategy_doc.get("notes", ""),
        placeholder="Goals, talking points, follow-up actions..."
    )

    if st.button("Save Strategy"):
        db["meeting_strategy"].update_one(
            {"purpose": lookup_purpose.strip(), "contact": lookup_contact.strip()},
            {
                "$set": {
                    "purpose": lookup_purpose.strip(),
                    "contact": lookup_contact.strip(),
                    "priority": priority,
                    "assigned_to": assigned,
                    "notes": notes,
                    "updated_at": datetime.now()
                }
            },
            upsert=True
        )
        st.success("✅ Strategy saved!")



st.markdown("## 📂 Upload Meeting Document")

col1, col2 = st.columns(2)
with col1:
    upload_purpose = st.text_input("Purpose", key="upload_purpose")
with col2:
    upload_contact = st.text_input("Contact / Organization", key="upload_contact")

uploaded_file = st.file_uploader("Upload File", type=["pdf", "docx"])

if st.button("Upload File"):
    if uploaded_file and upload_purpose:
        file_id = fs.put(
            uploaded_file.read(),
            filename=uploaded_file.name,
            purpose=upload_purpose,
            contact=upload_contact
        )

        db["strategy_files"].insert_one({
            "purpose": upload_purpose,
            "contact": upload_contact,
            "filename": uploaded_file.name,
            "file_id": file_id,
            "upload_date": datetime.now()
        })

        st.success("✅ File uploaded!")
    else:
        st.warning("Provide at least a purpose and file.")



st.markdown("## 📚 View Meeting Documents")

col1, col2 = st.columns(2)
with col1:
    view_purpose = st.text_input("Purpose", key="view_purpose")
with col2:
    view_contact = st.text_input("Contact / Organization", key="view_contact")

if view_purpose or view_contact:
    file_query = {}
    if view_purpose:
        file_query["purpose"] = {"$regex": view_purpose.strip(), "$options": "i"}
    if view_contact:
        file_query["contact"] = {"$regex": view_contact.strip(), "$options": "i"}

    files = list(db["strategy_files"].find(file_query))

    if files:
        for f in files:
            st.write(f"📄 {f['filename']} — {f.get('contact', '')} — {f['upload_date']}")

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
                st.error("⚠️ File missing or corrupted.")
    else:
        st.info("No documents found.")
