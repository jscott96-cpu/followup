import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"

# --- AUTHENTICATION ---
def get_google_sheet_client():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Authentication Error: {e}")
        st.stop()

# --- HELPER: CONVERT DAY NAME TO NUMBER ---
def get_day_number(day_name):
    """Returns 0=Monday, 6=Sunday. Returns -1 if invalid."""
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    if clean in days:
        return days.index(clean)
    return -1

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="🧭", layout="centered")
    st.title("🧭 Mentor Tracker")

    # 1. Load Data
    client = get_google_sheet_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception as e:
        st.error(f"Could not load sheet: {SHEET_NAME}. Error: {e}")
        st.stop()

    if df.empty:
        st.info("Sheet is empty.")
        st.stop()

    # 2. Global Date Variables
    today = datetime.now().date()
    today_weekday = today.weekday() # 0=Mon, 6=Sun
    yesterday_weekday = (today_weekday - 1) % 7 # Logic for "Day After Report"

    # 3. 🚨 CALCULATE ALERTS
    alerts = []

    for i, row in df.iterrows():
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day_str = str(row['Report_Day'])
        
        # Checkbox States (True/False)
        p1_done = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_done = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_done = str(row['P3_Sent_Prework']).upper() == 'TRUE'

        # Parse Date
        try:
            last_session = datetime.strptime(last_session_str, "%Y-%m-%d").date()
            # Assume Weekly Cadence
            next_session = last_session + timedelta(days=7)
        except ValueError:
            continue # Skip invalid dates

        # --- CONDITION 1: P1 (Day After Session) ---
        # "I haven't sent out the p1 reminder the day after the completed session"
        days_since_session = (today - last_session).days
        if days_since_session == 1 and not p1_done:
            alerts.append(f"✉️ **{name}**: Session was yesterday. Send encouragement!")

        # --- CONDITION 2: P2 (Report Late) ---
        # "It is the day after they said they would share their report and they haven't"
        report_day_idx = get_day_number(report_day_str)
        if report_day_idx == yesterday_weekday and not p2_done:
             alerts.append(f"⚠️ **{name}**: Missed {report_day_str} report (Due Yesterday).")

        # --- CONDITION 3: P3 (Pre-Work) ---
        # "I haven't sent out the prework follow up the day before our next session"
        days_until_next = (next_session - today).days
        if days_until_next == 1 and not p3_done:
            alerts.append(f"📚 **{name}**: Session is tomorrow. Send Pre-Work check.")

    # 4. DISPLAY ALERTS
    if alerts:
        st.error("### 🚨 Action Items")
        for alert in alerts:
            st.write(alert)
        st.markdown("---")
    else:
        st.success("✅ No urgent alerts today!")
        st.markdown("---")

    # 5. MISSIONARY CARDS (Checkboxes)
    for i, row in df.iterrows():
        sheet_row = i + 2
        name = row['Name']
        chat_link = row['Chat_Link']
        
        # Current Values
        p1_val = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_val = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_val = str(row['P3_Sent_Prework']).upper() == 'TRUE'

        with st.expander(f"**{name}**", expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                # P1
                if st.checkbox("1. Encouragement Sent", value=p1_val, key=f"p1_{i}"):
                    if not p1_val: # Changed to True
                        sheet.update_cell(sheet_row, 5, "TRUE")
                        st.rerun()
                elif p1_val: # Changed to False
                     sheet.update_cell(sheet_row, 5, "FALSE")
                     st.rerun()

                # P2
                if st.checkbox("2. Report Received", value=p2_val, key=f"p2_{i}"):
                    if not p2_val:
                        sheet.update_cell(sheet_row, 6, "TRUE")
                        st.rerun()
                elif p2_val:
                     sheet.update_cell(sheet_row, 6, "FALSE")
                     st.rerun()

                # P3
                if st.checkbox("3. Pre-Work Sent", value=p3_val, key=f"p3_{i}"):
                    if not p3_val:
                        sheet.update_cell(sheet_row, 7, "TRUE")
                        st.rerun()
                elif p3_val:
                     sheet.update_cell(sheet_row, 7, "FALSE")
                     st.rerun()
            
            with c2:
                if chat_link:
                    st.link_button("💬 Chat", chat_link)

if __name__ == "__main__":
    main()
