import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime
from rapidfuzz import fuzz

DB_FILE = "saree.db"

st.set_page_config(
    page_title="Jubilee Frame Tracker",
    page_icon="favicon.ico",
    layout="wide"
)

# ✅ EARLY RETURN check (right after config)
if st.session_state.get("rerun_needed", False):
    st.session_state["rerun_needed"] = False
    st.experimental_rerun()

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
        .action-button {
            color: blue;
            cursor: pointer;
            text-decoration: underline;
        }
    </style>
""", unsafe_allow_html=True)

# ---------- COMMON UTILITIES ----------

def status_tag(status):
    css_class = {
        "InHouse": "status-inhouse",
        "OutHouse": "status-outhouse",
        "InRepair": "status-inrepair"
    }.get(status, "")
    return f"<span class='status-tag {css_class}'>{status}</span>"

def render_table_page(table_name, label):
    if "show_sidebar" not in st.session_state:
        st.session_state.show_sidebar = True

    if "edit_row" not in st.session_state:
        st.session_state.edit_row = None

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
            new_name = st.text_input("Frame Name", key=f"add_name_{table_name}")
            new_status = st.selectbox("Status", ["InHouse", "OutHouse", "InRepair"], key=f"add_status_{table_name}")
            if st.button("Add Frame", key=f"add_btn_{table_name}"):
                if new_name.strip():
                    success, msg = add_frame(table_name, new_name.strip(), new_status)
                    if success:
                        st.session_state["success_message"] = msg
                        st.session_state["rerun_needed"] = True
                        st.stop()
                    else:
                        st.warning(msg)
                else:
                    st.warning("Frame name is required.")

    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("🔍 Search Frame Name", key=f"search_{table_name}")
    with col2:
        status_filter = st.selectbox("Filter by Status", ["All", "InHouse", "OutHouse", "InRepair"], key=f"filter_{table_name}")

    rows = get_frames(table_name)

    if search_query:
        rows = [r for r in rows if fuzz.partial_ratio(search_query.lower(), r[1].lower()) > 70]

    if status_filter != "All":
        rows = [r for r in rows if r[2] == status_filter]

    st.write(f"### 📋 {label} Table View ({len(rows)} items)")

    for fid, name, status in rows:
        if st.session_state.edit_row == fid:
            with st.form(f"edit_form_{table_name}_{fid}"):
                new_name = st.text_input("Edit Frame Name", name, key=f"edit_name_{table_name}_{fid}")
                new_status = st.selectbox("Edit Status", ["InHouse", "OutHouse", "InRepair"], index=["InHouse", "OutHouse", "InRepair"].index(status), key=f"edit_status_{table_name}_{fid}")
                col_edit, col_cancel = st.columns(2)
                with col_edit:
                    if st.form_submit_button("💾 Save"):
                        update_frame(table_name, fid, new_name, new_status)
                        st.session_state["success_message"] = "Updated successfully."
                        st.session_state["rerun_needed"] = True
                        st.stop()
                with col_cancel:
                    if st.form_submit_button("❌ Cancel"):
                        st.session_state.edit_row = None
                        st.experimental_rerun()
        else:
            col1, col2, col3 = st.columns([4, 2, 2])
            col1.markdown(f"**{name}**")
            col2.markdown(status_tag(status), unsafe_allow_html=True)
            col3.markdown(f"<span class='action-button' onclick='window.location.reload();'>Edit</span> | <span class='action-button' onclick='window.location.reload();'>Delete</span>", unsafe_allow_html=True)
            if col3.button("Edit", key=f"edit_btn_{fid}"):
                st.session_state.edit_row = fid
                st.experimental_rerun()
            if col3.button("Delete", key=f"delete_btn_{fid}"):
                delete_frame(table_name, fid)
                st.session_state["success_message"] = f"Deleted: {name}"
                st.session_state["rerun_needed"] = True
                st.stop()

    if st.button("📤 Export to Excel", key=f"export_{table_name}"):
        path = export_to_excel(table_name, label)
        with open(path, "rb") as f:
            st.download_button("Download Excel", data=f, file_name=os.path.basename(path), mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- DATABASE FUNCTIONS ----------

def init_table(table_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            frame_name TEXT UNIQUE,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_frames(table_name):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"SELECT id, frame_name, status FROM {table_name}")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_frame(table_name, frame_name, status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(f"INSERT INTO {table_name} (frame_name, status) VALUES (?, ?)", (frame_name, status))
        conn.commit()
        return True, f"Frame '{frame_name}' added."
    except sqlite3.IntegrityError:
        return False, f"Frame '{frame_name}' already exists."
    finally:
        conn.close()

def update_frame(table_name, frame_id, new_name, new_status):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE {table_name} SET frame_name = ?, status = ? WHERE id = ?", (new_name, new_status, frame_id))
    conn.commit()
    conn.close()

def delete_frame(table_name, frame_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (frame_id,))
    conn.commit()
    conn.close()

def export_to_excel(table_name, label):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query(f"SELECT frame_name, status FROM {table_name}", conn)
    conn.close()
    os.makedirs("exports", exist_ok=True)
    path = f"exports/{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(path, index=False)
    return path

# ---------- MAIN ----------

st.sidebar.image("logo.png", width=80)
st.sidebar.title("Jubilee Inventory")
page = st.sidebar.radio("Navigation", ["Design Frame Tracker", "BP Frame Tracker"])

init_table("design_frames")
init_table("bp_frames")

if page == "Design Frame Tracker":
    render_table_page("design_frames", "Design Frame Tracker")
elif page == "BP Frame Tracker":
    render_table_page("bp_frames", "BP Frame Tracker")
