import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import time
import altair as alt # For charts

# --- CONFIGURATION ---
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "Missionary_Tracker"
HISTORY_TAB_NAME = "History"

# --- AUTHENTICATION & SETUP ---
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

# --- DATA LOADING (Cached) ---
@st.cache_data(ttl=60)
def load_data():
    client = get_google_client()
    try:
        # Load Main Tracker
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Load History
        try:
            history_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
            history_data = history_sheet.get_all_records()
            df_history = pd.DataFrame(history_data)
        except:
            df_history = pd.DataFrame() # Empty if tab doesn't exist yet

        return df, df_history
    except Exception as e:
        st.error(f"Connection Error (Try Refreshing): {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- HELPER: WRITE UPDATES ---
def update_cell(row_idx, col_idx, value):
    client = get_google_client()
    sheet = client.open(SHEET_NAME).sheet1
    try:
        sheet.update_cell(row_idx, col_idx, value)
    except:
        st.warning("API busy, retrying...")
        time.sleep(1)
        sheet.update_cell(row_idx, col_idx, value)

def log_history_and_reset(row_idx, name, p1, p2, p3, new_last, new_next):
    """
    1. Appends current status to History tab.
    2. Updates Dates in Main tab.
    3. Resets Checkboxes to FALSE in Main tab.
    """
    client = get_google_client()
    main_sheet = client.open(SHEET_NAME).sheet1
    hist_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
    
    # 1. Log to History
    log_date = datetime.now().strftime("%Y-%m-%d")
    hist_row = [log_date, name, str(p1), str(p2), str(p3)]
    hist_sheet.append_row(hist_row)
    
    # 2. Update Dates (Col 3=Last, Col 4=Next)
    main_sheet.update_cell(row_idx, 3, str(new_last))
    main_sheet.update_cell(row_idx, 4, str(new_next))
    
    # 3. Reset Checkboxes (Col 6, 7, 8) -> FALSE
    # We use batch_update for speed/quota if possible, but individual is safer for now
    main_sheet.update_cell(row_idx, 6, "FALSE") # P1
    main_sheet.update_cell(row_idx, 7, "FALSE") # P2
    main_sheet.update_cell(row_idx, 8, "FALSE") # P3

# --- HELPER: DATE TOOLS ---
def get_day_number(day_name):
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    return days.index(clean) if clean in days else 0

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="Pg", layout="centered")
    st.title("🧭 Mentor Tracker")

    # Initialize Session State
    if 'df' not in st.session_state:
        df, df_hist = load_data()
        st.session_state.df = df
        st.session_state.df_hist = df_hist

    # Refresh Button
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        df, df_hist = load_data()
        st.session_state.df = df
        st.session_state.df_hist = df_hist
        st.rerun()

    # --- TABS SYSTEM ---
    tab_tracker, tab_history = st.tabs(["📋 Tracker", "📈 Trends & History"])

    # ==========================
    # TAB 1: TRACKER & ALERTS
    # ==========================
    with tab_tracker:
        
        # --- ADD NEW MISSIONARY ---
        with st.expander("➕ Add New Missionary"):
            with st.form("add_form"):
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
                    st.rerun()

        # --- ALERTS ENGINE ---
        today = datetime.now().date()
        alerts = []
        
        if not st.session_state.df.empty:
            for i, row in st.session_state.df.iterrows():
                name = row['Name']
                try:
                    last_sess = datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date()
                    next_sess = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                except:
                    continue # Skip invalid dates

                # Checkbox States
                p1 = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                p2 = str(row['P2_Received_Report']).upper() == 'TRUE'
                p3 = str(row['P3_Sent_Prework']).upper() == 'TRUE'

                # ALERT 1: Encouragement (Due: Last Session + 1 Day)
                if not p1 and today >= (last_sess + timedelta(days=1)):
                    alerts.append(f"✉️ **{name}**: Encouragement needed (Session was {last_sess})")

                # ALERT 2: Report (Due: Specific Day of Week)
                # Calculate the date of the Report Day falling between Last and Next session
                sess_wd = last_sess.weekday()
                rep_wd = get_day_number(row['Report_Day'])
                days_until = (rep_wd - sess_wd) % 7
                if days_until == 0: days_until = 7
                report_due_date = last_sess + timedelta(days=days_until)
                
                if not p2 and today > report_due_date:
                    alerts.append(f"⚠️ **{name}**: Report overdue (Due {report_due_date})")

                # ALERT 3: Pre-Work (Due: Next Session - 1 Day)
                if not p3 and today >= (next_sess - timedelta(days=1)):
                    alerts.append(f"📚 **{name}**: Send Pre-Work (Next Session: {next_sess})")

        if alerts:
            st.error("### 🚨 Action Items")
            for a in alerts: st.write(a)
        else:
            st.success("✅ All caught up!")

        st.markdown("---")

        # --- MISSIONARY CARDS ---
        if st.session_state.df.empty:
            st.info("No missionaries found.")
        else:
            for i, row in st.session_state.df.iterrows():
                name = row['Name']
                sheet_row = i + 2
                
                with st.expander(f"**{name}**", expanded=False):
                    c1, c2 = st.columns([3, 1])
                    
                    # --- CHECKBOXES ---
                    with c1:
                        # P1
                        val_p1 = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                        if st.checkbox("1. Encouragement Sent", value=val_p1, key=f"p1_{i}"):
                            new_v = "FALSE" if val_p1 else "TRUE"
                            st.session_state.df.at[i, 'P1_Sent_Encouragement'] = new_v
                            update_cell(sheet_row, 6, new_v)
                            st.rerun()

                        # P2
                        val_p2 = str(row['P2_Received_Report']).upper() == 'TRUE'
                        if st.checkbox(f"2. Received Report ({row['Report_Day']})", value=val_p2, key=f"p2_{i}"):
                            new_v = "FALSE" if val_p2 else "TRUE"
                            st.session_state.df.at[i, 'P2_Received_Report'] = new_v
                            update_cell(sheet_row, 7, new_v)
                            st.rerun()

                        # P3
                        val_p3 = str(row['P3_Sent_Prework']).upper() == 'TRUE'
                        if st.checkbox("3. Pre-Work Sent", value=val_p3, key=f"p3_{i}"):
                            new_v = "FALSE" if val_p3 else "TRUE"
                            st.session_state.df.at[i, 'P3_Sent_Prework'] = new_v
                            update_cell(sheet_row, 8, new_v)
                            st.rerun()
                    
                    with c2:
                        if row['Chat_Link']:
                            st.link_button("Chat", row['Chat_Link'])

                    st.markdown("---")

                    # --- CYCLE MANAGEMENT (Start New Week) ---
                    st.caption(f"**Current Cycle:** {row['Last_Session_Date']} to {row['Next_Session_Date']}")
                    
                    with st.popover("🔄 Finish Cycle & Log"):
                        st.markdown("### Start New Week")
                        st.info("This will log current results to History and reset checkboxes.")
                        
                        # Date Pickers for NEW cycle
                        try:
                            def_date = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                        except:
                            def_date = datetime.now().date()
                            
                        new_last_input = st.date_input("New 'Last Session' (Today)", value=def_date, key=f"nl_{i}")
                        new_next_input = st.date_input("New 'Next Session'", value=def_date + timedelta(days=7), key=f"nn_{i}")
                        
                        if st.button("✅ Log & Reset", key=f"reset_{i}", type="primary"):
                            log_history_and_reset(
                                sheet_row, name, val_p1, val_p2, val_p3, 
                                new_last_input, new_next_input
                            )
                            st.success("Cycle Logged! Refreshing...")
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()

                    # --- EDIT DETAILS (Name/Dates/Delete) ---
                    with st.expander("✏️ Edit Details (No Reset)"):
                        with st.form(key=f"edit_{i}"):
                            e_name = st.text_input("Name", value=name)
                            e_link = st.text_input("Link", value=row['Chat_Link'])
                            # Helper for dates
                            try: d_last = datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date()
                            except: d_last = datetime.now().date()
                            try: d_next = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                            except: d_next = datetime.now().date()
                                
                            e_last = st.date_input("Last Session", value=d_last)
                            e_next = st.date_input("Next Session", value=d_next)
                            e_rep = st.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], index=get_day_number(row['Report_Day']))
                            
                            if st.form_submit_button("Save Edits"):
                                client = get_google_client()
                                ws = client.open(SHEET_NAME).sheet1
                                ws.update_cell(sheet_row, 1, e_name)
                                ws.update_cell(sheet_row, 2, e_link)
                                ws.update_cell(sheet_row, 3, str(e_last))
                                ws.update_cell(sheet_row, 4, str(e_next))
                                ws.update_cell(sheet_row, 5, e_rep)
                                st.cache_data.clear()
                                st.rerun()
                                
                        if st.button("🗑️ Delete User", key=f"del_{i}"):
                            client = get_google_client()
                            ws = client.open(SHEET_NAME).sheet1
                            ws.delete_rows(sheet_row)
                            st.cache_data.clear()
                            st.rerun()

    # ==========================
    # TAB 2: TRENDS & HISTORY
    # ==========================
    with tab_history:
        st.header("📈 Trends")
        
        hist_df = st.session_state.df_hist
        if hist_df.empty:
            st.info("No history logged yet. Complete a cycle to see trends.")
        else:
            # 1. METRICS
            total_logs = len(hist_df)
            # Convert 'TRUE'/'FALSE' strings to Booleans for math
            hist_df['P2_Bool'] = hist_df['P2_Report'].astype(str).str.upper() == 'TRUE'
            avg_report = hist_df['P2_Bool'].mean() * 100
            
            m1, m2 = st.columns(2)
            m1.metric("Total Sessions Logged", total_logs)
            m2.metric("Avg Report Submission", f"{avg_report:.0f}%")
            
            st.markdown("---")
            
            # 2. CHART: Report Completion by Missionary
            st.subheader("Report Consistency")
            
            # Group by Name and calculate percentage
            chart_data = hist_df.groupby("Name")['P2_Bool'].mean().reset_index()
            chart_data['Percentage'] = chart_data['P2_Bool'] * 100
            
            chart = alt.Chart(chart_data).mark_bar().encode(
                x=alt.X('Name', sort=None),
                y=alt.Y('Percentage', title='Reports Submitted (%)', scale=alt.Scale(domain=[0, 100])),
                tooltip=['Name', 'Percentage']
            ).properties(height=300)
            
            st.altair_chart(chart, use_container_width=True)
            
            # 3. RAW DATA
            with st.expander("View Raw History Log"):
                st.dataframe(hist_df)

if __name__ == "__main__":
    main()
