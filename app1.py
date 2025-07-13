# Optimized and modular version of your Streamlit Frame Tracker
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

SERVICE_ACCOUNT_INFO = st.secrets["gcp_service_account"]
credentials = Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPE)
client = gspread.authorize(credentials)

SHEET_NAME = "design frame tracker"
WORKSHEET_MAP = {
    "design_frames": "Sheet1",
    "bp_frames": "Sheet2"
}

# ---------- SETUP ----------
st.set_page_config(page_title="Jubilee Frame Tracker", page_icon="favicon.ico", layout="wide")

# ---------- CSS ----------
st.markdown("""
    <style>
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

# ---------- UTILS ----------
def status_tag(status):
    classes = {"InHouse": "status-inhouse", "OutHouse": "status-outhouse", "InRepair": "status-inrepair"}
    return f"<span class='status-tag {classes.get(status, '')}'>{status}</span>"

def get_worksheet(table):
    return client.open(SHEET_NAME).worksheet(WORKSHEET_MAP[table])

@st.cache_data(show_spinner=False)
def read_frames(table):
    ws = get_worksheet(table)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return []

    headers = [h.strip().lower() for h in values[0]]
    data_rows = values[1:]
    hmap = {h: i for i, h in enumerate(headers)}
    if "frame name" not in hmap or "status" not in hmap:
        st.error("Missing required headers: 'Frame Name' or 'Status'")
        return []

    return [(i+2, row[hmap["frame name"]], row[hmap["status"]])
            for i, row in enumerate(data_rows)
            if len(row) > max(hmap["frame name"], hmap["status"]) and row[hmap["frame name"]] and row[hmap["status"]]]

def get_sheet_data_and_hash(table):
    rows = read_frames(table)
    data_hash = hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return rows, data_hash

def add_frame(table, name, status):
    ws = get_worksheet(table)
    existing = [r[0] for r in ws.get_all_values()[1:] if r]
    if name in existing:
        return False, f"Frame '{name}' already exists."
    ws.append_row([name, status], value_input_option="USER_ENTERED")
    return True, f"Frame '{name}' added."

def update_frame(table, row, name, status):
    ws = get_worksheet(table)
    ws.update(f"A{row}:B{row}", [[name, status]])

def delete_frame(table, row):
    get_worksheet(table).delete_rows(row)

def export_to_excel(table):
    ws = get_worksheet(table)
    df = pd.DataFrame(ws.get_all_values()[1:], columns=ws.get_all_values()[0])
    os.makedirs("exports", exist_ok=True)
    path = f"exports/{table}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(path, index=False)
    return path

# ---------- MAIN PAGE RENDER ----------
def render_table_page(table, label):
    if "show_sidebar" not in st.session_state:
        st.session_state.show_sidebar = True

    if "success_message" in st.session_state:
        st.success(st.session_state.pop("success_message"))

    st.columns([1, 1.5, 6])[0].button("☰", on_click=lambda: st.session_state.update(show_sidebar=not st.session_state.show_sidebar))
    st.columns([1, 1.5, 6])[1].image("logo.png", width=32)
    st.columns([1, 1.5, 6])[2].markdown(f"<h1 style='margin-top: 0.6rem;'>{label}</h1>", unsafe_allow_html=True)

    rows, hash_val = get_sheet_data_and_hash(table)
    if st.session_state.get(f"last_hash_{table}") != hash_val:
        st.session_state[f"last_hash_{table}"] = hash_val
        st.rerun()

    # Sidebar for adding frame
    if st.session_state.show_sidebar:
        with st.sidebar:
            st.header(f"➕ Add New Frame ({label})")
            name = st.text_input("Frame Name", key=f"add_name_{table}")
            status = st.selectbox("Status", ["InHouse", "OutHouse", "InRepair"], key=f"add_status_{table}")
            if st.button("Add Frame", key=f"add_btn_{table}"):
                if name.strip():
                    success, msg = add_frame(table, name.strip(), status)
                    if success:
                        st.session_state.pop(f"add_name_{table}", None)
                        st.session_state.pop(f"add_status_{table}", None)
                        st.rerun()
                    else:
                        st.warning(msg)
                else:
                    st.warning("Frame name is required.")

    # Search and filter
    search = st.text_input("🔍 Search Frame Name", key=f"search_{table}")
    status_filter = st.selectbox("Filter by Status", ["All", "InHouse", "OutHouse", "InRepair"], key=f"filter_{table}")

    if search:
        rows = [r for r in rows if fuzz.partial_ratio(search.lower(), r[1].lower()) > 70]
    if status_filter != "All":
        rows = [r for r in rows if r[2] == status_filter]

    st.write(f"### 📋 {label} Table View ({len(rows)} items)")
    items_pg = 10
    total_pages = max((len(rows) - 1) // items_pg + 1, 1)
    current_pg = st.number_input("Page", 1, total_pages, value=st.session_state.get(f"page_{table}", 1), key=f"page_{table}_input")
    st.session_state[f"page_{table}"] = current_pg
    paged = rows[(current_pg - 1) * items_pg: current_pg * items_pg]

    if paged:
        st.markdown("<div class='scroll-table'><table class='custom-table'>", unsafe_allow_html=True)
        st.markdown("<thead><tr><th>Frame Name</th><th>Status</th><th>Actions</th></tr></thead><tbody>", unsafe_allow_html=True)
        for row, name, status in paged:
            with st.form(f"form_{table}_{row}"):
                st.markdown(f"<tr><td>{name}</td><td>{status_tag(status)}</td><td>", unsafe_allow_html=True)
                new_name = st.text_input("", value=name, label_visibility="collapsed", key=f"edit_name_{row}_{table}")
                new_status = st.selectbox("", ["InHouse", "OutHouse", "InRepair"], index=["InHouse", "OutHouse", "InRepair"].index(status), label_visibility="collapsed", key=f"edit_status_{row}_{table}")
                if st.form_submit_button("💾 Save"):
                    update_frame(table, row, new_name, new_status)
                    st.session_state["success_message"] = "Updated successfully."
                    st.rerun()
                if st.form_submit_button("🗑️ Delete"):
                    delete_frame(table, row)
                    st.session_state["success_message"] = f"Deleted: {name}"
                    st.rerun()
                st.markdown("</td></tr>", unsafe_allow_html=True)
        st.markdown("</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.info("No data available.")

    if st.button("📤 Export to Excel", key=f"export_{table}"):
        path = export_to_excel(table)
        with open(path, "rb") as f:
            st.download_button("Download Excel", data=f, file_name=os.path.basename(path),
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- MAIN ----------
st.sidebar.image("logo.png", width=80)
st.sidebar.title("Jubilee Inventory")
choice = st.sidebar.radio("Navigation", ["Design Frame Tracker", "BP Frame Tracker"])

if choice == "Design Frame Tracker":
    render_table_page("design_frames", "Design Frame Tracker")
elif choice == "BP Frame Tracker":
    render_table_page("bp_frames", "BP Frame Tracker")
