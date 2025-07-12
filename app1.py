import streamlit as st
import gspread
import pandas as pd
import os
import json
from datetime import datetime
from rapidfuzz import fuzz
from google.oauth2.service_account import Credentials
import hashlib
import time

# ---------- CONFIG ----------
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Load service account credentials
SERVICE_ACCOUNT_INFO = json.loads(st.secrets["gcp_service_account"])
credentials = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPE)
client = gspread.authorize(credentials)

# Sheet setup
SHEET_NAME = "design frame tracker"
WORKSHEET_MAP = {
    "design_frames": "Sheet1",
    "bp_frames": "Sheet2"
}

# ---------- Streamlit Setup ----------
st.set_page_config(page_title="Jubilee Frame Tracker", page_icon="favicon.ico", layout="wide")

# ---------- CSS ----------
st.markdown("""
    <style>
        @media (max-width: 768px) {
            .block-container { padding: 1rem !important; }
        }
        .status-tag {
            color: white;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
        }
        .status-inhouse { background-color: green; }
        .status-outhouse { background-color: red; }
        .status-inrepair { background-color: orange; }
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
        table.custom-table th { background-color: #222; }
    </style>
""", unsafe_allow_html=True)

# ---------- Utilities ----------
def status_tag(status):
    css_class = {
        "InHouse": "status-inhouse",
        "OutHouse": "status-outhouse",
        "InRepair": "status-inrepair"
    }.get(status, "")
    return f"<span class='status-tag {css_class}'>{status}</span>"

def get_worksheet(table_name):
    return client.open(SHEET_NAME).worksheet(WORKSHEET_MAP[table_name])

def get_sheet_data_and_hash(table_name):
    ws = get_worksheet(table_name)
    values = ws.get_all_values()

    if not values or len(values) < 2:
        return [], ""

    headers_raw = values[0]
    data_rows = values[1:]

    # Normalize column headers and create header map
    headers = [h.strip().lower() for h in headers_raw]
    header_map = {h: i for i, h in enumerate(headers)}

    data_hash = hashlib.md5(str(time.time()).encode()).hexdigest()

    processed_rows = []
    skipped = 0
    for i, row in enumerate(data_rows):
        try:
            frame_name = row[header_map.get("frame name", -1)].strip() if header_map.get("frame name") is not None else None
            status = row[header_map.get("status", -1)].strip() if header_map.get("status") is not None else None
            if frame_name and status:
                processed_rows.append((i + 2, frame_name, status))
            else:
                skipped += 1
        except Exception:
            skipped += 1

    if skipped > 0:
        st.warning(f"⚠️ Skipped {skipped} row(s) with missing 'Frame Name' or 'Status'.")

    return processed_rows, data_hash

def add_frame(table_name, frame_name, status):
    ws = get_worksheet(table_name)
    existing_names = [row[0] for row in ws.get_all_values()[1:] if row and len(row) > 0]
    if frame_name in existing_names:
        return False, f"Frame '{frame_name}' already exists."

    ws.append_row([frame_name, status], value_input_option="USER_ENTERED")

    records = ws.get_all_values()
    new_hash = hashlib.md5(json.dumps(records, sort_keys=True).encode()).hexdigest()

    return True, f"Frame '{frame_name}' added."

def update_frame(table_name, row_index, new_name, new_status):
    ws = get_worksheet(table_name)
    ws.update(f"A{row_index}:B{row_index}", [[new_name, new_status]])

def delete_frame(table_name, row_index):
    ws = get_worksheet(table_name)
    ws.delete_rows(row_index)

def export_to_excel(table_name):
    ws = get_worksheet(table_name)
    data = ws.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    os.makedirs("exports", exist_ok=True)
    path = f"exports/{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(path, index=False)
    return path

# ---------- Main Renderer ----------
def render_table_page(table_name, label):
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

    rows, current_hash = get_sheet_data_and_hash(table_name)
    hash_key = f"last_hash_{table_name}"
    refresh_key = f"last_refresh_{table_name}"

    if refresh_key not in st.session_state:
        st.session_state[refresh_key] = time.time()

    if hash_key not in st.session_state:
        st.session_state[hash_key] = current_hash
    elif st.session_state[hash_key] != current_hash:
        st.session_state[hash_key] = current_hash
        st.experimental_rerun()

    if st.session_state.show_sidebar:
        with st.sidebar:
            st.header(f"➕ Add New Frame ({label})")
            name_key = f"add_name_{table_name}"
            status_key = f"add_status_{table_name}"
            new_name = st.text_input("Frame Name", key=name_key)
            new_status = st.selectbox("Status", ["InHouse", "OutHouse", "InRepair"], key=status_key)
            if st.button("Add Frame", key=f"add_btn_{table_name}"):
                if new_name.strip():
                    success, msg = add_frame(table_name, new_name.strip(), new_status)
                    if success:
                        st.session_state.pop(name_key, None)
                        st.session_state.pop(status_key, None)
                        st.session_state.pop(f"search_{table_name}", None)
                        st.session_state.pop(f"filter_{table_name}", None)
                        st.rerun()
                    else:
                        st.warning(msg)
                else:
                    st.warning("Frame name is required.")

    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("🔍 Search Frame Name", key=f"search_{table_name}")
    with col2:
        status_filter = st.selectbox("Filter by Status", ["All", "InHouse", "OutHouse", "InRepair"], key=f"filter_{table_name}")

    if search_query:
        rows = [r for r in rows if fuzz.partial_ratio(search_query.lower(), r[1].lower()) > 70]
    if status_filter != "All":
        rows = [r for r in rows if r[2] == status_filter]

    st.write(f"### 📋 {label} Table View ({len(rows)} items)")

    items_per_page = 10
    total_pages = max((len(rows) - 1) // items_per_page + 1, 1)

    if f"page_{table_name}" not in st.session_state:
        st.session_state[f"page_{table_name}"] = 1

    current_page = st.number_input(
        "Page", min_value=1, max_value=total_pages,
        value=st.session_state[f"page_{table_name}"], step=1, key=f"page_{table_name}_input")

    st.session_state[f"page_{table_name}"] = current_page
    paginated_rows = rows[(current_page - 1) * items_per_page: current_page * items_per_page]

    if paginated_rows:
        st.markdown("<div class='scroll-table'><table class='custom-table'>", unsafe_allow_html=True)
        st.markdown("<thead><tr><th>Frame Name</th><th>Status</th><th>Actions</th></tr></thead><tbody>", unsafe_allow_html=True)
        for row_index, name, status in paginated_rows:
            with st.form(f"action_form_{table_name}_{row_index}"):
                st.markdown(f"<tr><td>{name}</td><td>{status_tag(status)}</td><td>", unsafe_allow_html=True)
                edit_col, delete_col = st.columns([1, 1])
                with edit_col:
                    new_name = st.text_input("", value=name, label_visibility="collapsed", key=f"edit_name_{row_index}_{table_name}")
                with delete_col:
                    new_status = st.selectbox("", ["InHouse", "OutHouse", "InRepair"], index=["InHouse", "OutHouse", "InRepair"].index(status), label_visibility="collapsed", key=f"edit_status_{row_index}_{table_name}")
                save, delete = st.columns([1, 1])
                with save:
                    if st.form_submit_button("💾 Save"):
                        update_frame(table_name, row_index, new_name, new_status)
                        st.session_state["success_message"] = "Updated successfully."
                        st.rerun()
                with delete:
                    if st.form_submit_button("🗑️ Delete"):
                        delete_frame(table_name, row_index)
                        st.session_state["success_message"] = f"Deleted: {name}"
                        st.rerun()
                st.markdown("</td></tr>", unsafe_allow_html=True)
        st.markdown("</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.info("No data available.")

    if st.button("📤 Export to Excel", key=f"export_{table_name}"):
        path = export_to_excel(table_name)
        with open(path, "rb") as f:
            st.download_button("Download Excel", data=f, file_name=os.path.basename(path),
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- MAIN ----------
st.sidebar.image("logo.png", width=80)
st.sidebar.title("Jubilee Inventory")
page = st.sidebar.radio("Navigation", ["Design Frame Tracker", "BP Frame Tracker"])

if page == "Design Frame Tracker":
    render_table_page("design_frames", "Design Frame Tracker")
elif page == "BP Frame Tracker":
    render_table_page("bp_frames", "BP Frame Tracker")
