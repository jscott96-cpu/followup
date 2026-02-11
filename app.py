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

# --- HELPER FUNCTIONS ---
def get_day_number(day_name):
    """Returns 0=Monday, 6=Sunday."""
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    if clean in days:
        return days.index(clean)
    return -1

def update_cell(sheet, row, col, value):
    """Updates a single cell."""
    try:
        sheet.update_cell(row, col, value)
        st.toast("Saved!")
    except Exception as e:
        st.error(f"Save failed: {e}")

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="Pg", layout="centered")
    st.title("🧭 Mentor Tracker")

    # 1. CONNECT TO GOOGLE SHEETS
    client = get_google_sheet_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception as e:
        st.error(f"Could not connect to sheet: {e}")
        st.stop()

    # --- SIDEBAR: ADD NEW MISSIONARY ---
    with st.sidebar:
        st.header("➕ Add Missionary")
        with st.form("add_missionary_form"):
            new_name = st.text_input("Name")
            new_report_day = st.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            new_last_session = st.date_input("Last Session Date", datetime.now())
            new_chat_link = st.text_input("Chat Link (URL)")
            
            submitted = st.form_submit_button("Add to Tracker")
            if submitted and new_name:
                # Append row to Google Sheet
                # Order: Name, Chat_Link, Last_Session_Date, Report_Day, P1, P2, P3, Webhook
                new_row = [
                    new_name, 
                    new_chat_link, 
                    str(new_last_session), 
                    new_report_day, 
                    "FALSE", "FALSE", "FALSE", ""
                ]
                sheet.append_row(new_row)
                st.success(f"Added {new_name}!")
                st.rerun()

    if df.empty:
        st.info("No missionaries found. Use the sidebar to add one.")
        st.stop()

    # 2. CALCULATE ALERTS (The "Brain" of the app)
    today = datetime.now().date()
    yesterday_weekday = (today.weekday() - 1) % 7
    
    alerts = []

    for i, row in df.iterrows():
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day_str = str(row['Report_Day'])
        
        # Checkbox States
        p1_done = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_done = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_done = str(row['P3_Sent_Prework']).upper() == 'TRUE'

        try:
            last_session = datetime.strptime(last_session_str, "%Y-%m-%d").date()
            next_session = last_session + timedelta(days=7)
        except ValueError:
            continue # Skip invalid dates

        # ALERT 1: Day After Session (Encouragement)
        if (today - last_session).days == 1 and not p1_done:
            alerts.append(f"✉️ **{name}**: Session was yesterday. Send encouragement!")

        # ALERT 2: Day After Report Day (Late Report)
        report_idx = get_day_number(report_day_str)
        if report_idx == yesterday_weekday and not p2_done:
            alerts.append(f"⚠️ **{name}**: Missed {report_day_str} report.")

        # ALERT 3: Day Before Next Session (Pre-Work)
        if (next_session - today).days == 1 and not p3_done:
            alerts.append(f"📚 **{name}**: Session is tomorrow. Send Pre-Work.")

    # 3. DISPLAY ALERTS
    if alerts:
        st.error("### 🚨 Action Items")
        for alert in alerts:
            st.write(alert)
        st.markdown("---")
    else:
        st.success("✅ All caught up!")
        st.markdown("---")

    # 4. MISSIONARY CARDS (View & Edit)
    st.subheader("Missionaries")

    for i, row in df.iterrows():
        # Google Sheets is 1-indexed, row 1 is header, so data starts at row 2
        sheet_row = i + 2
        
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day = row['Report_Day']
        chat_link = row['Chat_Link']
        
        # Card UI
        with st.expander(f"**{name}**", expanded=False):
            
            # --- TAB 1: ACTIONS (Checkboxes) ---
            c1, c2 = st.columns([3, 1])
            with c1:
                # P1
                p1_val = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                if st.checkbox("1. Encouragement Sent", value=p1_val, key=f"p1_{i}"):
                    if not p1_val: 
                        update_cell(sheet, sheet_row, 5, "TRUE")
                        st.rerun()
                elif p1_val:
                    update_cell(sheet, sheet_row, 5, "FALSE")
                    st.rerun()

                # P2
                p2_val = str(row['P2_Received_Report']).upper() == 'TRUE'
                if st.checkbox(f"2. Received Report ({report_day})", value=p2_val, key=f"p2_{i}"):
                    if not p2_val:
                        update_cell(sheet, sheet_row, 6, "TRUE")
                        st.rerun()
                elif p2_val:
                    update_cell(sheet, sheet_row, 6, "FALSE")
                    st.rerun()

                # P3
                p3_val = str(row['P3_Sent_Prework']).upper() == 'TRUE'
                if st.checkbox("3. Pre-Work Sent", value=p3_val, key=f"p3_{i}"):
                    if not p3_val:
                        update_cell(sheet, sheet_row, 7, "TRUE")
                        st.rerun()
                elif p3_val:
                    update_cell(sheet, sheet_row, 7, "FALSE")
                    st.rerun()

            with c2:
                if chat_link:
                    st.link_button("💬 Chat", chat_link)

            st.markdown("---")
            
            # --- TAB 2: EDIT DETAILS (Collapsible Form) ---
            with st.expander("✏️ Edit Details"):
                with st.form(key=f"edit_form_{i}"):
                    # Pre-fill form with current data
                    edit_name = st.text_input("Name", value=name)
                    
                    # Handle Date Conversion for Input
                    try:
                        date_obj = datetime.strptime(last_session_str, "%Y-%m-%d").date()
                    except:
                        date_obj = datetime.now().date()
                    edit_date = st.date_input("Last Session Date", value=date_obj)
                    
                    edit_day = st.selectbox("Report Day", 
                                          ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                                          index=get_day_number(report_day) if get_day_number(report_day) != -1 else 0)
                    
                    edit_link = st.text_input("Chat Link", value=chat_link)
                    
                    # Save Button
                    if st.form_submit_button("💾 Save Changes"):
                        # Update specific cells in Google Sheet
                        # Name=Col1, Chat=Col2, Date=Col3, ReportDay=Col4
                        sheet.update_cell(sheet_row, 1, edit_name)
                        sheet.update_cell(sheet_row, 2, edit_link)
                        sheet.update_cell(sheet_row, 3, str(edit_date))
                        sheet.update_cell(sheet_row, 4, edit_day)
                        
                        # Optional: Reset checkboxes if date changed? 
                        # For now, we leave them as is to prevent accidental data loss.
                        
                        st.success("Updated!")
                        st.rerun()

if __name__ == "__main__":
    main()
