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
    client = get_google_client()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        try:
            h_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
            h_data = h_sheet.get_all_records()
            df_h = pd.DataFrame(h_data)
        except:
            df_h = pd.DataFrame()

        return df, df_h
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame()

# --- CALLBACKS ---
def toggle_status(idx, col_name, sheet_col_idx):
    st.session_state['active_index'] = idx
    current_val = str(st.session_state.df.at[idx, col_name]).upper()
    new_val = "FALSE" if current_val == "TRUE" else "TRUE"
    st.session_state.df.at[idx, col_name] = new_val
    try:
        client = get_google_client()
        sheet = client.open(SHEET_NAME).sheet1
        sheet.update_cell(idx + 2, sheet_col_idx, new_val)
    except Exception as e:
        st.toast(f"⚠️ Cloud sync paused: {e}")

def update_missionary_details(idx, new_name, new_link, new_last, new_next, new_rep):
    st.session_state['active_index'] = idx
    st.session_state.df.at[idx, 'Name'] = new_name
    st.session_state.df.at[idx, 'Chat_Link'] = new_link
    st.session_state.df.at[idx, 'Last_Session_Date'] = str(new_last)
    st.session_state.df.at[idx, 'Next_Session_Date'] = str(new_next)
    st.session_state.df.at[idx, 'Report_Day'] = new_rep
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
        st.error("Failed to sync details.")

def log_and_reset(idx, name, p1, p2, p3, new_last, new_next):
    st.session_state['active_index'] = None
    client = get_google_client()
    main_sheet = client.open(SHEET_NAME).sheet1
    hist_sheet = client.open(SHEET_NAME).worksheet(HISTORY_TAB_NAME)
    
    log_date = datetime.now().strftime("%Y-%m-%d")
    hist_sheet.append_row([log_date, name, str(p1), str(p2), str(p3)])
    
    r = idx + 2
    main_sheet.update_cell(r, 3, str(new_last))
    main_sheet.update_cell(r, 4, str(new_next))
    main_sheet.update_cell(r, 6, "FALSE")
    main_sheet.update_cell(r, 7, "FALSE")
    main_sheet.update_cell(r, 8, "FALSE")
    st.cache_data.clear()

def get_day_number(day_name):
    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    clean = str(day_name).strip().lower()
    return days.index(clean) if clean in days else 0

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Mentor Tracker", page_icon="Pg", layout="centered")
    st.title("🧭 Mentor Tracker")

    if 'df' not in st.session_state:
        df, df_hist = load_data_from_cloud()
        st.session_state.df = df
        st.session_state.df_hist = df_hist
    
    if 'active_index' not in st.session_state:
        st.session_state['active_index'] = None

    if st.button("🔄 Force Refresh"):
        st.cache_data.clear()
        df, df_hist = load_data_from_cloud()
        st.session_state.df = df
        st.session_state.df_hist = df_hist
        st.rerun()

    tab_tracker, tab_history = st.tabs(["📋 Tracker", "📈 Trends"])

    # --- TAB 1: TRACKER ---
    with tab_tracker:
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
                    row = [n_name, n_link, str(n_last), str(n_next), n_rep, "FALSE", "FALSE", "FALSE", ""]
                    ws.append_row(row)
                    st.cache_data.clear()
                    if 'df' in st.session_state: del st.session_state['df']
                    st.rerun()

        today = datetime.now().date()
        alerts = []
        if not st.session_state.df.empty:
            for i, row in st.session_state.df.iterrows():
                name = row['Name']
                try:
                    last_sess = datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date()
                    next_sess = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                except: continue

                p1 = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                p2 = str(row['P2_Received_Report']).upper() == 'TRUE'
                p3 = str(row['P3_Sent_Prework']).upper() == 'TRUE'

                if not p1 and today >= (last_sess + timedelta(days=1)):
                    alerts.append(f"✉️ **{name}**: Encouragement needed")

                sess_wd = last_sess.weekday()
                rep_wd = get_day_number(row['Report_Day'])
                days_until = (rep_wd - sess_wd) % 7
                if days_until == 0: days_until = 7
                report_due = last_sess + timedelta(days=days_until)
                
                if not p2 and today > report_due:
                    alerts.append(f"⚠️ **{name}**: Report overdue (Due {report_due.strftime('%A')})")

                if not p3 and today >= (next_sess - timedelta(days=1)):
                    alerts.append(f"📚 **{name}**: Send Pre-Work (Session {next_sess})")

        if alerts:
            st.error("### 🚨 Action Items")
            for a in alerts: st.write(a)
        else:
            st.success("✅ All caught up!")
        st.markdown("---")

        if not st.session_state.df.empty:
            for i, row in st.session_state.df.iterrows():
                name = row['Name']
                is_expanded = (i == st.session_state['active_index'])
                
                with st.expander(f"**{name}**", expanded=is_expanded):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        val_p1 = str(row['P1_Sent_Encouragement']).upper() == 'TRUE'
                        st.checkbox("1. Encouragement Sent", value=val_p1, key=f"p1_{i}", 
                                    on_change=toggle_status, args=(i, 'P1_Sent_Encouragement', 6))

                        val_p2 = str(row['P2_Received_Report']).upper() == 'TRUE'
                        st.checkbox(f"2. Received Report ({row['Report_Day']})", value=val_p2, key=f"p2_{i}", 
                                    on_change=toggle_status, args=(i, 'P2_Received_Report', 7))

                        val_p3 = str(row['P3_Sent_Prework']).upper() == 'TRUE'
                        st.checkbox("3. Pre-Work Sent", value=val_p3, key=f"p3_{i}", 
                                    on_change=toggle_status, args=(i, 'P3_Sent_Prework', 8))
                    
                    with c2:
                        if row['Chat_Link']:
                            st.link_button("Chat", row['Chat_Link'])
                    
                    st.markdown("---")
                    
                    with st.popover("🔄 Finish Cycle"):
                        st.caption("Log history & reset checkboxes")
                        try: d_def = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                        except: d_def = datetime.now().date()
                        nl = st.date_input("New 'Last Session'", value=d_def, key=f"nl_{i}")
                        nn = st.date_input("New 'Next Session'", value=d_def + timedelta(days=7), key=f"nn_{i}")
                        if st.button("✅ Log & Reset", key=f"lr_{i}", type="primary"):
                            log_and_reset(i, name, val_p1, val_p2, val_p3, nl, nn)
                            st.rerun()

                    with st.expander("✏️ Edit Details"):
                        with st.form(f"edit_{i}"):
                            e_name = st.text_input("Name", value=name)
                            e_link = st.text_input("Link", value=row['Chat_Link'])
                            try: dl = datetime.strptime(str(row['Last_Session_Date']), "%Y-%m-%d").date()
                            except: dl = datetime.now().date()
                            try: dn = datetime.strptime(str(row['Next_Session_Date']), "%Y-%m-%d").date()
                            except: dn = datetime.now().date()
                            el = st.date_input("Last Session", value=dl)
                            en = st.date_input("Next Session", value=dn)
                            er = st.selectbox("Report Day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], 
                                              index=get_day_number(row['Report_Day']))
                            if st.form_submit_button("Save Edits"):
                                update_missionary_details(i, e_name, e_link, el, en, er)
                                st.rerun()
                        if st.button("🗑️ Delete User", key=f"del_{i}"):
                            client = get_google_client()
                            ws = client.open(SHEET_NAME).sheet1
                            ws.delete_rows(i + 2)
                            if 'df' in st.session_state: del st.session_state['df']
                            st.cache_data.clear()
                            st.rerun()

    # --- TAB 2: HISTORY ---
    with tab_history:
        st.header("📈 History & Trends")
        
        if not st.session_state.df_hist.empty:
            dfh = st.session_state.df_hist
            
            # 1. Clean Data (Convert to Booleans)
            dfh['Encouragement'] = dfh['P1_Encouragement'].astype(str).str.upper() == 'TRUE'
            dfh['Report'] = dfh['P2_Report'].astype(str).str.upper() == 'TRUE'
            dfh['Prework'] = dfh['P3_Prework'].astype(str).str.upper() == 'TRUE'
            
            # 2. Reshape Data
            chart_data = dfh.melt(
                id_vars=['Name', 'Date_Logged'], 
                value_vars=['Encouragement', 'Report', 'Prework'], 
                var_name='Task', 
                value_name='Completed'
            )
            
            # 3. Calculate %
            agg_data = chart_data.groupby(['Name', 'Task'])['Completed'].mean().reset_index()
            
            # 4. Create Grouped Bar Chart with CUSTOM COLORS
            c = alt.Chart(agg_data).mark_bar().encode(
                x=alt.X('Task', axis=None), 
                y=alt.Y('Completed', axis=alt.Axis(format='%', title='Completion Rate')),
                
                # --- COLOR CHANGE IS HERE ---
                color=alt.Color('Task', 
                    # Define manual color range: Blue, Green, Orange
                    scale=alt.Scale(range=['#3182bd', '#e6550d', '#31a354']), 
                    legend=alt.Legend(title="Task Type", orient="bottom")
                ),
                
                column=alt.Column('Name', header=alt.Header(titleOrient="bottom", labelOrient="bottom")),
                tooltip=['Name', 'Task', alt.Tooltip('Completed', format='.0%')]
            ).properties(
                height=300 
            ).configure_view(
                stroke='transparent' 
            )
            
            st.altair_chart(c)
            
        else:
            st.info("No history logs found. Complete a cycle in the Tracker tab to see data here.")

if __name__ == "__main__":
    main()
