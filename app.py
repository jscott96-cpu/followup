import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import time
import altair as alt

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"
HISTORY_TAB_NAME = "History"

# --- AUTHENTICATION ---
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

# --- DATA LOADER ---
@st.cache_data(ttl=60)
def load_data_from_cloud():
    """Loads data from Google Sheets only when cache expires or forced."""
    client = get_google_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Load History
        try:
            h_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
            h_data = h_sheet.get_all_records()
            df_h = pd.DataFrame(h_data)
        except:
            df_h = pd.DataFrame()

        return df, df_h
    except Exception as e:
        # If API quota is hit, return empty to prevent crash
        return pd.DataFrame(), pd.DataFrame()

# --- CALLBACKS (The Fix for Cycling) ---
def toggle_status(idx, col_name, sheet_col_idx):
    """
    Updates Local State INSTANTLY, then sends to Google.
    This runs BEFORE the app reloads, preventing the cycle bug.
    """
    # 1. Update Local State
    current_val = str(st.session_state.df.at[idx, col_name]).upper()
    new_val = "FALSE" if current_val == "TRUE" else "TRUE"
    st.session_state.df.at[idx, col_name] = new_val
    
    # 2. Sync to Google (Fire and Forget)
    try:
        client = get_google_client()
        sheet = client.open(SHEET_NAME).sheet1
        # Row index is idx + 2 (0-based df index -> 1-based sheet + 1 header)
        sheet.update_cell(idx + 2, sheet_col_idx, new_val)
    except Exception as e:
        st.toast(f"⚠️ Saved locally, but cloud sync paused: {e}")

def update_missionary_details(idx, new_name, new_link, new_last, new_next, new_rep):
    # Update Local
    st.session_state.df.at[idx, 'Name'] = new_name
    st.session_state.df.at[idx, 'Chat_Link'] = new_link
    st.session_state.df.at[idx, 'Last_Session_Date'] = str(new_last)
    st.session_state.df.at[idx, 'Next_Session_Date'] = str(new_next)
    st.session_state.df.at[idx, 'Report_Day'] = new_rep
    
    # Update Cloud
    try:
        client = get_google_client()
        ws = client.open(SHEET_NAME).sheet1
        r = idx + 2
        ws.update_cell(r, 1, new_name)
        ws.update_cell(r, 2, new_link)
        ws.update_cell(r, 3, str(new_last))
        ws.update_cell(r, 4, str(new_next))
        ws.update_cell(r, 5, new_rep)
        st.toast("Details updated!")
    except:
        st.error("Failed to sync details to cloud.")

def log_and_reset(idx, name, p1, p2, p3, new_last, new_next):
    client = get_google_client()
    main_sheet = client.open(SHEET_NAME).sheet1
    hist_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
    
    # Log History
    log_date = datetime.now().strftime("%Y-%m-%d")
    hist_sheet.append_row([log_date, name, str(p1), str(p2), str(p3)])
    
    # Update Dates & Reset Checkboxes
    r = idx + 2
    main_sheet.update_cell(r, 3, str(new_last))
    main_sheet.update_cell(r, 4, str(new_next))
    main_sheet.update_cell(r, 6, "FALSE")
    main_sheet.update_cell(r, 7, "FALSE")
    main_sheet.update_cell(r, 8, "FALSE")
    
    # Clear Cache to force reload next time
    st.cache_data.clear()

# --- HELPER: DATE TOOLS ---
def get_day_number(day_name):
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    return days.index(clean) if clean in days else 0

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="Pg", layout="centered")
    st.title("🧭 Mentor Tracker")

    # 1. INITIALIZATION (Load once, then rely on session_state)
    if 'df' not in st.session_state:
        df, df_hist = load_data_from_cloud()
        st.session_state.df = df
        st.session_state.df_hist = df_hist

    # Force Refresh Button
    if st.button("🔄 Force Refresh (If Sync Stuck)"):
        st.cache_data.clear()
        df, df_hist = load_data_from_cloud()
        st.session_state.df = df
        st.session_state.df_hist = df_hist
        st.rerun()

    tab_tracker, tab_history = st.tabs(["📋 Tracker", "📈 Trends"])

    # ==========================
    # TAB 1: TRACKER
    # ==========================
    with tab_tracker:
        
        # ADD MISSIONARY
        with st.expander("➕ Add New Missionary"):
            with st.form("add"):
                c1, c2 = st.columns(2)
                n_name = c1.text_input("Name")
                n_rep = c1.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
                n_last = c2.date_input("Last Session", datetime.now())
                n_next = c2.date_input("Next Session", datetime.now() + timedelta(days=7))
                n_link = st.text_input("Chat Link")
                
                if st.form_submit_button("Add"):
                    client = get_google_client()
                    ws = client.open(SHEET_NAME).sheet1
                    # Schema: Name, Link, Last, Next, Report, P1, P2, P3, Webhook
                    row = [n_name, n_link, str(n_last), str(n_next), n_rep, "FALSE", "FALSE", "FALSE", ""]
                    ws.append_row(row)
                    st.cache_data.clear()
                    # Safe reload
                    if 'df' in st.session_state: del st.session_state['df']
                    st.rerun()

        # ALERTS ENGINE (Reads strictly from Local State)
        today = datetime.now().date()
        alerts = []
        
        if not st.session_state.df.empty:
            for i, row in st.session_state.df.iterrows():
                name = row['Name']
                try:
                    last_sess = datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date()
                    next_sess = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                except:
                    continue

                p1 = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                p2 = str(row['P2_Received_Report']).upper() == 'TRUE'
                p3 = str(row['P3_Sent_Prework']).upper() == 'TRUE'

                # Alert 1: Encouragement (Due: Last + 1)
                if not p1 and today >= (last_sess + timedelta(days=1)):
                    alerts.append(f"✉️ **{name}**: Encour
