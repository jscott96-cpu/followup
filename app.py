import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"  # Ensure this matches your Google Sheet exactly

# --- AUTHENTICATION ---
def get_google_sheet_client():
    try:
        # Load credentials from Streamlit secrets
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Authentication Error: {e}")
        st.stop()

# --- HELPER FUNCTIONS ---
def get_day_index(day_name):
    """Converts 'Monday' to 0, 'Sunday' to 6."""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    try:
        return days.index(day_name.strip().title())
    except ValueError:
        return -1 # Invalid day name

def update_sheet(row_idx, col_idx, value, sheet):
    """Updates a specific cell in the Google Sheet."""
    try:
        sheet.update_cell(row_idx, col_idx, value)
        st.toast("Saved to Google Sheets! ☁️")
    except Exception as e:
        st.error(f"Failed to update sheet: {e}")

# --- MAIN APP LOGIC ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="🧭", layout="centered")
    
    # Custom CSS for mobile friendliness
    st.markdown("""
        <style>
        .stButton button { width: 100%; border-radius: 8px; }
        .stExpander { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 10px; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🧭 Mentor Tracker")

    # 1. Connect and Load Data
    client = get_google_sheet_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception as e:
        st.error(f"Could not load '{SHEET_NAME}'. Check your Google Sheet name and permissions.")
        st.stop()

    if df.empty:
        st.info("Your Google Sheet is empty.")
        st.stop()

    # 2. Global Date Calculations
    today = datetime.now().date()
    today_idx = today.weekday() # 0=Mon, 6=Sun

    # 3. DASHBOARD: "Action Required" (Top Section)
    st.subheader("🚨 Needs Attention")
    
    alerts = []
    
    for i, row in df.iterrows():
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day_str = str(row['Report_Day'])
        
        # Parse Dates
        try:
            last_session = datetime.strptime(last_session_str, "%Y-%m-%d").date()
            next_session = last_session + timedelta(days=7) # Assuming weekly cadence
        except ValueError:
            continue # Skip invalid dates
            
        # Status Flags
        p1_done = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_done = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_done = str(row['P3_Sent_Prework']).upper() == 'TRUE'

        # --- LOGIC: GENERATE ALERTS ---
        
        # Alert 1: Day After Session (Send Encouragement)
        if not p1_done and (today - last_session).days == 1:
            alerts.append(f"✨ **{name}**: Send encouragement (Day After Session)")
            
        # Alert 2: Late Report (Mid-Week)
        rep_idx = get_day_index(report_day_str)
        if not p2_done and rep_idx != -1:
            # If today is AFTER their report day, it is overdue
            if today_idx > rep_idx: 
                alerts.append(f"⚠️ **{name}**: Missed {report_day_str} Report!")
            # If today IS their report day
            elif today_idx == rep_idx:
                alerts.append(f"🕒 **{name}**: Report due today ({report_day_str})")

        # Alert 3: Day Before Next Session (Pre-Work)
        if not p3_done and (next_session - today).days == 1:
            alerts.append(f"📚 **{name}**: Check Pre-Work (Session Tomorrow)")

    # Render Alerts
    if alerts:
        for alert in alerts:
            st.warning(alert, icon="🔔")
    else:
        st.success("All caught up! No urgent tasks.", icon="✅")

    st.markdown("---")

    # 4. MISSIONARY CARDS
    st.subheader("Your Missionaries")

    # We use index+2 for GSheets (1-based index + header row)
    for i, row in df.iterrows():
        sheet_row_num = i + 2 
        name = row['Name']
        last_session_str = row['Last_Session_Date']
        report_day = row['Report_Day']
        chat_link = row['Chat_Link']
        
        # State Variables
        p1_val = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_val = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_val = str(row['P3_Sent_Prework']).upper() == 'TRUE'
        
        # Card UI
        with st.expander(f"**{name}**", expanded=False):
            c1, c2 = st.columns([2, 1])
            
            with c1:
                st.caption(f"Last Session: {last_session_str}")
                st.caption(f"Report Day: {report_day}")
                
            with c2:
                if chat_link:
                    st.link_button("💬 Chat", chat_link)
            
            st.divider()

            # --- CHECKBOXES WITH AUTO-SAVE ---
            
            # Point 1
            if st.checkbox("1. Sent Encouragement", value=p1_val, key=f"p1_{i}"):
                if not p1_val: # If it changed from False to True
                    update_sheet(sheet_row_num, 5, "TRUE", sheet)
                    st.rerun()
            elif p1_val: # If it changed from True to False
                update_sheet(sheet_row_num, 5, "FALSE", sheet)
                st.rerun()

            # Point 2
            if st.checkbox(f"2. Received Report ({report_day})", value=p2_val, key=f"p2_{i}"):
                 if not p2_val:
                    update_sheet(sheet_row_num, 6, "TRUE", sheet)
                    st.rerun()
            elif p2_val:
                update_sheet(sheet_row_num, 6, "FALSE", sheet)
                st.rerun()
                
            # Point 3
            if st.checkbox("3. Sent Pre-Work Check", value=p3_val, key=f"p3_{i}"):
                 if not p3_val:
                    update_sheet(sheet_row_num, 7, "TRUE", sheet)
                    st.rerun()
            elif p3_val:
                update_sheet(sheet_row_num, 7, "FALSE", sheet)
                st.rerun()

if __name__ == "__main__":
    main()
