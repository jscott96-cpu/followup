import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import requests

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"  # Make sure this matches your Google Sheet Name

# --- AUTHENTICATION ---
# Uses Streamlit Secrets for security (explained in Phase 3)
def get_google_sheet_client():
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    client = gspread.authorize(creds)
    return client

# --- HELPER FUNCTIONS ---
def send_webhook_notification(webhook_url, message):
    """Sends a message to Google Chat via Webhook."""
    if not webhook_url or str(webhook_url).strip() == "":
        st.warning("No Webhook URL found.")
        return False
        
    headers = {'Content-Type': 'application/json; charset=UTF-8'}
    data = {'text': message}
    try:
        response = requests.post(webhook_url, json=data, headers=headers)
        if response.status_code == 200:
            return True
        else:
            st.error(f"Webhook failed: {response.text}")
            return False
    except Exception as e:
        st.error(f"Error sending webhook: {e}")
        return False

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="🧭", layout="centered")
    st.title("🧭 Missionary Mentor Tracker")

    # 1. Load Data
    try:
        client = get_google_sheet_client()
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception as e:
        st.error(f"Could not connect to Google Sheet. Error: {e}")
        st.stop()

    if df.empty:
        st.info("No data found in the sheet.")
        st.stop()

    # 2. Iterate through Missionaries
    st.markdown("---")
    
    # We use index+2 because Sheets are 1-indexed and Row 1 is headers
    for i, row in df.iterrows():
        sheet_row_number = i + 2 
        name = row['Name']
        last_session_str = row['Last_Session_Date']
        report_day = row['Report_Day']
        chat_link = row['Chat_Link']
        
        # Date Logic
        try:
            last_session = datetime.strptime(str(last_session_str), "%Y-%m-%d").date()
            today = datetime.now().date()
            days_since = (today - last_session).days
            
            # Determine "Next Session" (Assuming weekly cadence)
            next_session = last_session + timedelta(days=7)
        except ValueError:
            st.error(f"Date format error for {name}. Use YYYY-MM-DD.")
            continue

        # --- CARD UI ---
        with st.expander(f"**{name}** (Session: {last_session_str})", expanded=True):
            
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.caption(f"Mid-Week Report Due: **{report_day}**")
                
                # POINT 1: Day After Encouragement
                p1_val = True if str(row['P1_Sent_Encouragement']).upper() == 'TRUE' else False
                if st.checkbox(f"Point 1: Sent Encouragement (Day +1)", value=p1_val, key=f"p1_{i}"):
                    if not p1_val: # Only update if changed to True
                        sheet.update_cell(sheet_row_number, 5, "TRUE")
                        st.rerun()
                elif p1_val: # Update if unchecked
                    sheet.update_cell(sheet_row_number, 5, "FALSE")
                    st.rerun()

                # POINT 2: Mid-Week Report
                p2_val = True if str(row['P2_Received_Report']).upper() == 'TRUE' else False
                if st.checkbox(f"Point 2: Received Report ({report_day})", value=p2_val, key=f"p2_{i}"):
                     if not p2_val:
                        sheet.update_cell(sheet_row_number, 6, "TRUE")
                        st.rerun()
                elif p2_val:
                    sheet.update_cell(sheet_row_number, 6, "FALSE")
                    st.rerun()

                # POINT 3: Pre-Work Follow Up
                p3_val = True if str(row['P3_Sent_Prework']).upper() == 'TRUE' else False
                is_day_before = (next_session - today).days <= 1
                label_p3 = "Point 3: Pre-Work Check (Due Soon)" if is_day_before else "Point 3: Pre-Work Check"
                
                if st.checkbox(label_p3, value=p3_val, key=f"p3_{i}"):
                     if not p3_val:
                        sheet.update_cell(sheet_row_number, 7, "TRUE")
                        st.rerun()
                elif p3_val:
                    sheet.update_cell(sheet_row_number, 7, "FALSE")
                    st.rerun()

            with col2:
                # Deep Link Button
                if chat_link:
                    st.link_button("💬 Chat", chat_link)
                
                # Automation / Nudge Button
                if not p2_val:
                    if st.button("🔔 Nudge", key=f"nudge_{i}", help="Send webhook reminder"):
                        webhook_url = row.get('Webhook_Url', '')
                        msg = f"Hi {name}, just a reminder to send in your report for this week!"
                        success = send_webhook_notification(webhook_url, msg)
                        if success:
                            st.toast(f"Notification sent to {name}!")

if __name__ == "__main__":
    main()
