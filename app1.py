import streamlit as st
import pandas as pd
import os
from datetime import datetime
from rapidfuzz import fuzz
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------- CONFIG ----------
SERVICE_ACCOUNT_JSON = "service_account.json"
SPREADSHEET_NAME = "Jubilee Frames"

st.set_page_config(
    page_title="Jubilee Frame Tracker",
    page_icon="favicon.ico",
    layout="wide"
)

# ---------- CSS ----------
st.markdown("""
    <style>
        @media (max-width: 768px) {
            .block-container {
                padding: 1rem !important;
            }
        }
        .status-tag {
            color: white;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
        }
        .status-inhouse {
            background-color: green;
        }
        .status-outhouse {
            background-color: red;
        }
        .status-inrepair {
            background-color: orange;
        }
        .scroll-table {
            overflow-x: auto;
            max-height: 400px;
            border: 1px solid #444;
        }
        table.custom-table {
            border-collapse: collapse;
            width: 100%;
            color: white;
        }
        table.custom-table th, table.custom-table td {
            border: 1px solid #555;
            padding: 8px;
            text-align: center;
        }
        table.custom-table th {
            background-color: #222;
        }
    </style>
""", unsafe_allow_html=True)

# ---------- GOOGLE SHEETS ----------
class GoogleSheetDB:
    def __init__(self, json_key_path, spreadsheet_name):
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(json_key_path, scope)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open(spreadsheet_name)

    def get_sheet(self, sheet_name):
        return self.sheet.worksheet(sheet_name)

    def get_frames(self, sheet_name):
        df = pd.DataFrame(self.get_sheet(sheet_name).get_all_records())
        return df.reset_index().rename(columns={"index": "id"}).to_records(index=False)

    def add_frame(self, sheet_name, frame_name, status):
        ws = self.get_sheet(sheet_name)
        records = ws.get_all_records()
        if any(row["frame_name"] == frame_name for row in records):
            return False, f"Frame '{frame_name}' already exists."
        ws.append_row([frame_name, status])
        return True, f"Frame '{frame_name}' added."

    def update_frame(self, sheet_name, row_index, frame_name, status):
        ws = self.get_sheet(sheet_name)
        ws.update(f"A{row_index+2}", [[frame_name, status]])

    def delete_frame(self, sheet_name, row_index):
        ws = self.get_sheet(sheet_name)
        ws.delete_rows(row_index + 2)

    def export_to_excel(self, sheet_name):
        df = pd.DataFrame(self.get_sheet(sheet_name).get_all_records())
        os.makedirs("exports", exist_ok=True)
        path = f"exports/{sheet_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(path, index=False)
        return path

# ---------- UTILITIES ----------
def status_tag(status):
    css_class = {
        "InHouse": "status-inhouse",
        "OutHouse": "status-outhouse",
        "InRepair": "status-inrepair"
    }.get(status, "")
    return f"<span class='status-tag {css_class}'>{status}</span>"

gs_db = GoogleSheetDB(SERVICE_ACCOUNT_JSON, SPREADSHEET_NAME)

def render_table_page(sheet_name, label):
    if "show_sidebar" not in st.session_state:
        st.session_state.show_sidebar = True

    if "success_message" in st.session_state:
        st.success(st.session_state.pop("success_message"))

    col1, col2, col3 = st.columns([1, 1.5, 6])
    with col1:
        if st.button("☰"):
            st.session_state.show_sidebar = not st.session_state.show_sidebar
    with col2:
        st.image("logo.png", width=32)
    with col3:
        st.markdown(f"<h1 style='margin-top: 0.6rem;'>{label}</h1>", unsafe_allow_html=True)

    if st.session_state.show_sidebar:
        with st.sidebar:
            st.header(f"➕ Add New Frame ({label})")
            name_key = f"add_name_{sheet_name}"
            status_key = f"add_status_{sheet_name}"
            new_name = st.text_input("Frame Name", key=name_key)
            new_status = st.selectbox("Status", ["InHouse", "OutHouse", "InRepair"], key=status_key)
            if st.button("Add Frame", key=f"add_btn_{sheet_name}"):
                if new_name.strip():
                    success, msg = gs_db.add_frame(sheet_name, new_name.strip(), new_status)
                    if success:
                        st.session_state.pop(name_key, None)
                        st.session_state.pop(status_key, None)
                        st.rerun()
                    else:
                        st.warning(msg)
                else:
                    st.warning("Frame name is required.")

    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("🔍 Search Frame Name", key=f"search_{sheet_name}")
    with col2:
        status_filter = st.selectbox("Filter by Status", ["All", "InHouse", "OutHouse", "InRepair"], key=f"filter_{sheet_name}")

    rows = gs_db.get_frames(sheet_name)
    if search_query:
        rows = [r for r in rows if fuzz.partial_ratio(search_query.lower(), r.frame_name.lower()) > 70]
    if status_filter != "All":
        rows = [r for r in rows if r.status == status_filter]

    st.write(f"### 📋 {label} Table View ({len(rows)} items)")

    items_per_page = 10
    total_items = len(rows)
    total_pages = max((total_items - 1) // items_per_page + 1, 1)

    if f"page_{sheet_name}" not in st.session_state:
        st.session_state[f"page_{sheet_name}"] = 1

    current_page = st.number_input(
        "Page", min_value=1, max_value=total_pages,
        value=st.session_state[f"page_{sheet_name}"],
        step=1, key=f"page_{sheet_name}_input"
    )
    st.session_state[f"page_{sheet_name}"] = current_page

    start_idx = (current_page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    paginated_rows = rows[start_idx:end_idx]

    if paginated_rows:
        st.markdown("<div class='scroll-table'><table class='custom-table'>", unsafe_allow_html=True)
        st.markdown("<thead><tr><th>Frame Name</th><th>Status</th><th>Actions</th></tr></thead><tbody>", unsafe_allow_html=True)
        for row in paginated_rows:
            fid = row.id
            name = row.frame_name
            status = row.status
            with st.form(f"action_form_{sheet_name}_{fid}"):
                st.markdown(f"<tr><td>{name}</td><td>{status_tag(status)}</td><td>", unsafe_allow_html=True)
                edit_col, delete_col = st.columns([1, 1])
                with edit_col:
                    new_name = st.text_input("", value=name, label_visibility="collapsed", key=f"edit_name_{fid}_{sheet_name}")
                with delete_col:
                    new_status = st.selectbox("", ["InHouse", "OutHouse", "InRepair"], index=["InHouse", "OutHouse", "InRepair"].index(status), label_visibility="collapsed", key=f"edit_status_{fid}_{sheet_name}")
                save, delete = st.columns([1, 1])
                with save:
                    if st.form_submit_button("💾 Save"):
                        gs_db.update_frame(sheet_name, fid, new_name, new_status)
                        st.session_state["success_message"] = "Updated successfully."
                        st.rerun()
                with delete:
                    if st.form_submit_button("🗑️ Delete"):
                        gs_db.delete_frame(sheet_name, fid)
                        st.session_state["success_message"] = f"Deleted: {name}"
                        st.rerun()
                st.markdown("</td></tr>", unsafe_allow_html=True)
        st.markdown("</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.info("No data available.")

    if st.button("📤 Export to Excel", key=f"export_{sheet_name}"):
        path = gs_db.export_to_excel(sheet_name)
        with open(path, "rb") as f:
            st.download_button("Download Excel", data=f, file_name=os.path.basename(path), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- MAIN ----------
st.sidebar.image("logo.png", width=80)
st.sidebar.title("Jubilee Inventory")
page = st.sidebar.radio("Navigation", ["Design Frame Tracker", "BP Frame Tracker"])

if page == "Design Frame Tracker":
    render_table_page("design_frames", "Design Frame Tracker")
elif page == "BP Frame Tracker":
    render_table_page("bp_frames", "BP Frame Tracker")
