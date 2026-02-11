import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import time

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"

# --- AUTHENTICATION ---
# We cache this to avoid re-authenticating constantly
@st.cache_resource
def get_google_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Authentication Error: {e}")
        st.stop()

# --- DATA LOADER (Prevents 429 Errors) ---
# We cache the data for 5 minutes (ttl=300) so we don't spam the API with reads
@st.cache_data(ttl=300)
def load_data_from_google():
    client = get_google_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Could not load sheet. API Limit likely hit. Wait 1 min. Error: {e}")
        return pd.DataFrame()

# --- HELPER: WRITE TO SHEET ---
# This is a 'Write' operation, we don't cache this.
def update_google_sheet(row_idx, col_idx, value):
    client = get_google_client()
    sheet = client.open(SHEET_NAME).sheet1
    try:
        sheet.update_cell(row_idx, col_idx, value)
    except Exception as e:
        st.warning(f"Note: Update sent, but API is busy. ({e})")

# --- HELPER: DAY CALCULATIONS ---
def get_day_number(day_name):
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    if clean in days:
        return days.index(clean)
    return 0 # Default to Monday if error

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="Pg", layout="centered")
    st.title("🧭 Mentor Tracker")

    # 1. INITIALIZE LOCAL STATE
    # This prevents the "Cycling" bug by keeping data in memory
    if 'df' not in st.session_state:
        st.session_state.df = load_data_from_google()

    # Refresh Button (To manually pull new data if needed)
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear() # Clear cache
        st.session_state.df = load_data_from_google()
        st.rerun()

    if st.session_state.df.empty:
        st.warning("No data found. Please add a missionary.")
    
    # 2. ADD MISSIONARY SECTION
    with st.expander("➕ Add New Missionary", expanded=False):
        with st.form("add_form"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("Name")
            new_report_day = c1.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            new_date = c2.date_input("Last Session", datetime.now())
            new_link = c2.text_input("Chat Link")
            
            if st.form_submit_button("Add"):
                client = get_google_client()
                sheet = client.open(SHEET_NAME).sheet1
                row = [new_name, new_link, str(new_date), new_report_day, "FALSE", "FALSE", "FALSE", ""]
                sheet.append_row(row)
                st.cache_data.clear() # Force reload
                st.rerun()

    # 3. 🚨 SMART ALERT ENGINE
    # Logic: Calculate specific DEADLINES. If Today > Deadline and Not Done -> ALERT.
    
    today = datetime.now().date()
    alerts = []
    
    # We iterate over the Local Dataframe
    for i, row in st.session_state.df.iterrows():
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day_str = str(row['Report_Day'])
        
        # Parse Dates
        try:
            last_session = datetime.strptime(last_session_str, "%Y-%m-%d").date()
        except:
            continue
            
        # --- DEADLINE CALCULATIONS ---
        
        # P1 Deadline: The day AFTER the session
        p1_deadline = last_session + timedelta(days=1)
        
        # P2 Deadline: The specific Report Day falling after the session
        session_weekday = last_session.weekday()
        report_weekday = get_day_number(report_day_str)
        # Calculate days until report is due (0-6 days later)
        days_until_report = (report_weekday - session_weekday) % 7
        if days_until_report == 0: days_until_report = 7 # If same day, assume next week
        p2_deadline = last_session + timedelta(days=days_until_report)
        
        # P3 Deadline: The day BEFORE the next session (Session + 6 days)
        # Next session is +7 days, so Pre-work check is +6 days
        p3_deadline = last_session + timedelta(days=6)

        # --- CHECK STATUS ---
        # Note: We check 'TRUE' explicitly to handle empty cells safely
        p1_done = str(row['P1_Sent_Encouragement']).strip().upper() == 'TRUE'
        p2_done = str(row['P2_Received_Report']).strip().upper() == 'TRUE'
        p3_done = str(row['P3_Sent_Prework']).strip().upper() == 'TRUE'

        # --- TRIGGER ALERTS ---
        
        # Alert 1: Encouragement (Late if today >= deadline)
        if not p1_done and today >= p1_deadline:
            days_late = (today - p1_deadline).days
            msg = "Yesterday" if days_late == 0 else f"{days_late} days ago"
            alerts.append(f"✉️ **{name}**: Encouragement needed (Session was {msg})")

        # Alert 2: Report (Late if today > deadline)
        # We give them until the end of the deadline day, so we alert if today > deadline
        if not p2_done and today > p2_deadline:
             alerts.append(f"⚠️ **{name}**: Report overdue (Was due {report_day_str})")

        # Alert 3: Pre-Work (Late if today >= deadline)
        # If it's the day before (deadline) OR the day of the next session
        next_session = last_session + timedelta(days=7)
        if not p3_done and today >= p3_deadline:
             alerts.append(f"📚 **{name}**: Send Pre-Work (Session is soon/today)")

    # Display Alerts
    if alerts:
        st.error("### 🚨 Action Items")
        for a in alerts: st.write(a)
    else:
        st.success("✅ All caught up!")
    
    st.markdown("---")

    # 4. MISSIONARY CARDS (With Instant State Updates)
    for i, row in st.session_state.df.iterrows():
        name = row['Name']
        # We use a unique index for the expander
        with st.expander(f"**{name}**", expanded=False):
            
            c1, c2 = st.columns([3, 1])
            sheet_row_num = i + 2 # Header is row 1
            
            with c1:
                # --- CHECKBOX 1: Encouragement ---
                # We use the 'on_change' callback strategy indirectly by checking state before drawing
                p1_val = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                if st.checkbox("1. Encouragement Sent", value=p1_val, key=f"p1_{i}"):
                    if not p1_val: # If user just checked it
                        st.session_state.df.at[i, 'P1_Sent_Encouragement'] = "TRUE" # Update Local
                        update_google_sheet(sheet_row_num, 5, "TRUE") # Update Cloud
                        st.rerun() # Refresh UI immediately
                elif p1_val: # If user unchecked it
                    st.session_state.df.at[i, 'P1_Sent_Encouragement'] = "FALSE"
                    update_google_sheet(sheet_row_num, 5, "FALSE")
                    st.rerun()

                # --- CHECKBOX 2: Report ---
                p2_val = str(row['P2_Received_Report']).upper() == 'TRUE'
                report_day = row['Report_Day']
                if st.checkbox(f"2. Received Report ({report_day})", value=p2_val, key=f"p2_{i}"):
                    if not p2_val:
                        st.session_state.df.at[i, 'P2_Received_Report'] = "TRUE"
                        update_google_sheet(sheet_row_num, 6, "TRUE")
                        st.rerun()
                elif p2_val:
                    st.session_state.df.at[i, 'P2_Received_Report'] = "FALSE"
                    update_google_sheet(sheet_row_num, 6, "FALSE")
                    st.rerun()

                # --- CHECKBOX 3: Pre-Work ---
                p3_val = str(row['P3_Sent_Prework']).upper() == 'TRUE'
                if st.checkbox("3. Pre-Work Sent", value=p3_val, key=f"p3_{i}"):
                    if not p3_val:
                        st.session_state.df.at[i, 'P3_Sent_Prework'] = "TRUE"
                        update_google_sheet(sheet_row_num, 7, "TRUE")
                        st.rerun()
                elif p3_val:
                    st.session_state.df.at[i, 'P3_Sent_Prework'] = "FALSE"
                    update_google_sheet(sheet_row_num, 7, "FALSE")
                    st.rerun()

            with c2:
                if row['Chat_Link']:
                    st.link_button("Chat", row['Chat_Link'])

            # --- EDIT/DELETE ---
            with st.popover("Edit Details"):
                new_n = st.text_input("Name", value=name, key=f"n_{i}")
                new_d = st.date_input("Last Session", value=datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date(), key=f"d_{i}")
                new_rd = st.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], index=get_day_number(row['Report_Day']), key=f"r_{i}")
                
                if st.button("Save Changes", key=f"save_{i}"):
                    # Update Local
                    st.session_state.df.at[i, 'Name'] = new_n
                    st.session_state.df.at[i, 'Last_Session_Date'] = str(new_d)
                    st.session_state.df.at[i, 'Report_Day'] = new_rd
                    # Update Cloud (Multiple cells)
                    client = get_google_client()
                    ws = client.open(SHEET_NAME).sheet1
                    # Update Name(1), Date(3), Day(4)
                    ws.update_cell(sheet_row_num, 1, new_n)
                    ws.update_cell(sheet_row_num, 3, str(new_d))
                    ws.update_cell(sheet_row_num, 4, new_rd)
                    st.success("Saved!")
                    time.sleep(1)
                    st.rerun()
                
                st.markdown("---")
                if st.button("Delete Missionary", key=f"del_{i}", type="primary"):
                    client = get_google_client()
                    ws = client.open(SHEET_NAME).sheet1
                    ws.delete_rows(sheet_row_num)
                    st.cache_data.clear() # Clear cache to remove deleted row
                    st.rerun()

if __name__ == "__main__":
    main()
