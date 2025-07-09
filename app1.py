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
            cursor: pointer;
        }
        .action-button {
            background-color: #444;
            color: white;
            padding: 4px 8px;
            border: none;
            border-radius: 4px;
            margin: 0 4px;
            cursor: pointer;
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
                        st.session_state["clear_input"] = True
                        st.session_state["success_message"] = msg
                        st.session_state["rerun_needed"] = True
                        return
                    else:
                        st.warning(msg)
                else:
                    st.warning("Frame name is required.")

    if st.session_state.get("clear_input"):
        st.session_state[f"add_name_{table_name}"] = ""
        st.session_state["clear_input"] = False

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

    # Pagination and sorting
    sort_column = st.selectbox("Sort By", ["Frame Name", "Status"], key=f"sort_col_{table_name}")
    sort_order = st.radio("Sort Order", ["Ascending", "Descending"], key=f"sort_order_{table_name}", horizontal=True)

    reverse = sort_order == "Descending"
    if sort_column == "Frame Name":
        rows.sort(key=lambda x: x[1].lower(), reverse=reverse)
    else:
        rows.sort(key=lambda x: x[2], reverse=reverse)

    page_size = 10
    total_pages = (len(rows) - 1) // page_size + 1
    current_page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key=f"page_{table_name}")
    page_rows = rows[(current_page - 1) * page_size: current_page * page_size]

    st.write(f"### 📋 {label} Table View ({len(rows)} items, Page {current_page}/{total_pages})")

    if page_rows:
        st.markdown("<div class='scroll-table'><table class='custom-table'>", unsafe_allow_html=True)
        st.markdown("<thead><tr><th>Frame Name</th><th>Status</th><th>Actions</th></tr></thead><tbody>", unsafe_allow_html=True)
        for fid, name, status in page_rows:
            with st.form(f"action_form_{table_name}_{fid}"):
                st.markdown(f"<tr><td>{name}</td><td>{status_tag(status)}</td><td>", unsafe_allow_html=True)
                edit_col, delete_col = st.columns([1, 1])
                with edit_col:
                    new_name = st.text_input("", value=name, label_visibility="collapsed", key=f"edit_name_{fid}_{table_name}")
                with delete_col:
                    new_status = st.selectbox("", ["InHouse", "OutHouse", "InRepair"], index=["InHouse", "OutHouse", "InRepair"].index(status), label_visibility="collapsed", key=f"edit_status_{fid}_{table_name}")
                save, delete = st.columns([1, 1])
                with save:
                    if st.form_submit_button("💾 Save"):
                        update_frame(table_name, fid, new_name, new_status)
                        st.session_state["success_message"] = "Updated successfully."
                        st.session_state["rerun_needed"] = True
                        return
                with delete:
                    if st.form_submit_button("🗑️ Delete"):
                        delete_frame(table_name, fid)
                        st.session_state["success_message"] = f"Deleted: {name}"
                        st.session_state["rerun_needed"] = True
                        return
                st.markdown("</td></tr>", unsafe_allow_html=True)
        st.markdown("</tbody></table></div>", unsafe_allow_html=True)
    else:
        st.info("No data available.")

    if st.button("📤 Export to Excel", key=f"export_{table_name}"):
        path = export_to_excel(table_name, label)
        with open(path, "rb") as f:
            st.download_button("Download Excel", data=f, file_name=os.path.basename(path),
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
