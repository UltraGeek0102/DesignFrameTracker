import streamlit as st
import sqlite3
import pandas as pd
import os
from datetime import datetime

DB_FILE = "saree.db"

st.set_page_config(
    page_title="Jubilee Frame Tracker",
    page_icon="favicon.ico",  # reference your .ico file
    layout="wide"
)


# ---------- CSS for Mobile Padding ----------
st.markdown("""
    <style>
        @media (max-width: 768px) {
            .block-container {
                padding: 1rem !important;
            }
        }
    </style>
""", unsafe_allow_html=True)

# ---------- COMMON UTILITIES ----------

def status_color(status):
    return {
        "InHouse": "green",
        "OutHouse": "red",
        "InRepair": "orange"
    }.get(status, "gray")

def render_table_page(table_name, label):
    if "show_sidebar" not in st.session_state:
        st.session_state.show_sidebar = True

    col1, col2, col3 = st.columns([1, 1.5, 6])
    with col1:
        if st.button("☰"):
            st.session_state.show_sidebar = not st.session_state.show_sidebar
    with col2:
        st.image("logo.png", width=180)  # Smaller logo size for better alignment
    with col3:
        st.markdown(f"<h1 style='margin-top: 0.6rem;'>{label}</h1>", unsafe_allow_html=True)


    # Add New Form in sidebar
    if st.session_state.show_sidebar:
        with st.sidebar:
            st.header(f"➕ Add New Frame ({label})")
            new_name = st.text_input("Frame Name", key=f"add_name_{table_name}")
            new_status = st.selectbox("Status", ["InHouse", "OutHouse", "InRepair"], key=f"add_status_{table_name}")
            if st.button("Add Frame", key=f"add_btn_{table_name}"):
                if new_name.strip():
                    success, msg = add_frame(table_name, new_name.strip(), new_status)
                    st.success(msg) if success else st.warning(msg)
                    st.experimental_rerun()
                else:
                    st.warning("Frame name is required.")

    # Search and display
    search_query = st.text_input("🔍 Search Frame Name", key=f"search_{table_name}")
    rows = get_frames(table_name, search_query)

    st.write(f"### 📋 {label} List ({len(rows)} items)")

    for row in rows:
        fid, name, status = row
        with st.expander(f"📌 {name}"):
            st.markdown(f"<span style='color: white; background-color: {status_color(status)}; padding: 4px 8px; border-radius: 4px;'>{status}</span>", unsafe_allow_html=True)

            with st.form(f"edit_form_{table_name}_{fid}", clear_on_submit=False):
                new_name = st.text_input("Edit Frame Name", name, key=f"edit_name_{table_name}_{fid}")
                new_status = st.selectbox("Edit Status", ["InHouse", "OutHouse", "InRepair"],
                                          index=["InHouse", "OutHouse", "InRepair"].index(status),
                                          key=f"edit_status_{table_name}_{fid}")
                col_edit, col_delete = st.columns(2)
                with col_edit:
                    if st.form_submit_button("💾 Save Changes"):
                        update_frame(table_name, fid, new_name, new_status)
                        st.success("Updated successfully.")
                        st.experimental_rerun()
                with col_delete:
                    if st.form_submit_button("🗑️ Delete Frame"):
                        delete_frame(table_name, fid)
                        st.warning(f"Deleted: {name}")
                        st.experimental_rerun()

    # Export to Excel
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

def get_frames(table_name, search_query=""):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if search_query:
        cursor.execute(f"SELECT id, frame_name, status FROM {table_name} WHERE LOWER(frame_name) LIKE ?", ('%' + search_query.lower() + '%',))
    else:
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

st.set_page_config(page_title="Jubilee Frame Tracker", layout="wide")

# Sidebar Navigation
st.sidebar.image("logo.png", width=80)
st.sidebar.title("Jubilee Inventory")
page = st.sidebar.radio("Navigation", ["Design Frame Tracker", "BP Frame Tracker"])

# Ensure tables exist
init_table("design_frames")
init_table("bp_frames")

# Routing
if page == "Design Frame Tracker":
    render_table_page("design_frames", "Design Frame Tracker")
elif page == "BP Frame Tracker":
    render_table_page("bp_frames", "BP Frame Tracker")
