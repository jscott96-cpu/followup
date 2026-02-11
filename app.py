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
    st.set_page_config(page_title="Mentor Tracker", page_icon="🧭", layout="centered")
    
    # Custom CSS to make the "Add" section pop and buttons look better
    st.markdown("""
        <style>
        .stButton button { width: 100%; border-radius: 8px; }
        /* Style the expander header to be more visible */
        .streamlit-expanderHeader { font-weight: bold; font-size: 1.1rem; }
        </style>
    """, unsafe_allow_html=True)

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

    # --- SECTION: ADD MISSIONARY (High Visibility) ---
    # Moved from sidebar to main page for better visibility
    with st.expander("➕ Add New Missionary (Tap to Open)", expanded=False):
        st.info("Enter details below to start tracking a new missionary.")
        with st.form("add_missionary_form"):
            col_a, col_b = st.columns(2)
            with col_a:
                new_name = st.text_input("Name")
                new_report_day = st.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            with col_b:
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
                time.sleep(1) # Brief pause so user sees the success message
                st.rerun()

    # --- SECTION: ALERTS ---
    if df.empty:
        st.warning("No missionaries found. Add one above!")
        st.stop()

    # Date Calculations
    today = datetime.now().date()
    yesterday_weekday = (today.weekday() - 1) % 7
    
    alerts = []

    # Calculate Alerts Loop
    for i, row in df.iterrows():
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day_str = str(row['Report_Day'])
        
        p1_done = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
        p2_done = str(row['P2_Received_Report']).upper() == 'TRUE'
        p3_done = str(row['P3_Sent_Prework']).upper() == 'TRUE'

        try:
            last_session = datetime.strptime(last_session_str, "%Y-%m-%d").date()
            next_session = last_session + timedelta(days=7)
        except ValueError:
            continue 

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

    # Display Alerts
    if alerts:
        st.error("### 🚨 Action Items")
        for alert in alerts:
            st.write(alert)
        st.markdown("---")
    else:
        st.success("✅ All caught up!")
        st.markdown("---")

    # --- SECTION: MISSIONARY LIST ---
    st.subheader("Missionaries")

    for i, row in df.iterrows():
        sheet_row = i + 2
        
        name = row['Name']
        last_session_str = str(row['Last_Session_Date'])
        report_day = row['Report_Day']
        chat_link = row['Chat_Link']
        
        # UI Card
        with st.expander(f"**{name}**", expanded=False):
            
            # --- ACTIONS TAB ---
            c1, c2 = st.columns([3, 1])
            with c1:
                # P1
                p1_val = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                if st.checkbox("1. Encouragement Sent", value=p1_val, key=f"p1_{i}"):
                    # Toggle logic
                    new_val = "FALSE" if p1_val else "TRUE"
                    update_cell(sheet, sheet_row, 5, new_val)
                    st.rerun()

                # P2
                p2_val = str(row['P2_Received_Report']).upper() == 'TRUE'
                if st.checkbox(f"2. Received Report ({report_day})", value=p2_val, key=f"p2_{i}"):
                    new_val = "FALSE" if p2_val else "TRUE"
                    update_cell(sheet, sheet_row, 6, new_val)
                    st.rerun()

                # P3
                p3_val = str(row['P3_Sent_Prework']).upper() == 'TRUE'
                if st.checkbox("3. Pre-Work Sent", value=p3_val, key=f"p3_{i}"):
                    new_val = "FALSE" if p3_val else "TRUE"
                    update_cell(sheet, sheet_row, 7, new_val)
                    st.rerun()

            with c2:
                if chat_link:
                    st.link_button("💬 Chat", chat_link)

            st.markdown("---")
            
            # --- EDIT & DELETE SECTION ---
            with st.expander("✏️ Edit or Delete"):
                # Edit Form
                with st.form(key=f"edit_form_{i}"):
                    st.caption("Edit Details")
                    edit_name = st.text_input("Name", value=name)
                    
                    try:
                        date_obj = datetime.strptime(last_session_str, "%Y-%m-%d").date()
                    except:
                        date_obj = datetime.now().date()
                    edit_date = st.date_input("Last Session Date", value=date_obj)
                    
                    edit_day = st.selectbox("Report Day", 
                                          ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                                          index=get_day_number(report_day) if get_day_number(report_day) != -1 else 0)
                    edit_link = st.text_input("Chat Link", value=chat_link)
                    
                    if st.form_submit_button("💾 Save Changes"):
                        sheet.update_cell(sheet_row, 1, edit_name)
                        sheet.update_cell(sheet_row, 2, edit_link)
                        sheet.update_cell(sheet_row, 3, str(edit_date))
                        sheet.update_cell(sheet_row, 4, edit_day)
                        st.success("Updated!")
                        st.rerun()
                
                # DELETE BUTTON
                st.markdown("---")
                st.caption("Danger Zone")
                # We use a unique key for every button so Streamlit doesn't get confused
                if st.button(f"🗑️ Delete {name}", key=f"del_{i}", type="primary"):
                    sheet.delete_rows(sheet_row)
                    st.warning(f"Deleted {name}.")
                    time.sleep(1)
                    st.rerun()

if __name__ == "__main__":
    main()
