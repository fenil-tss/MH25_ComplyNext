import os
import streamlit as st
import streamlit_authenticator as stauth
from auth import get_authenticator
from pathlib import Path
import yaml

# Load authentication config only once
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

# Get absolute path to CSS file (in frontend directory)
CSS_FILE = Path(__file__).parent.parent / "style.css"

# ------------------- LOAD CSS -------------------
if os.path.exists(CSS_FILE):
    with open(CSS_FILE, 'r', encoding='utf-8') as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# authenticator = stauth.Authenticate(
#     config["credentials"],
#     config["cookie"]["name"],
#     config["cookie"]["key"],
#     config["cookie"]["expiry_days"]
# )

def load_navbar(page_title: str):
    """Loads a constant top navbar on every page."""

    # ---------- LOGIN CHECK ----------
    # authenticator.login(location="unrendered")
    authenticator = get_authenticator()
    authenticator.login(location='unrendered')
    if not st.session_state.get("authentication_status"):
        st.error("🔒 Access denied. Please log in.")
        return

    # ---------- USER DETAILS ----------
    full_name = st.session_state["name"]
    username = st.session_state["username"]
    first_name = full_name.split()[0] if full_name else username
    initial = first_name[0].upper()

    # ---------- Navbar HTML ----------
    st.markdown(
        f"""
        <div class="top-navbar">
            <div>{page_title}</div>
            <div class="user-info">
                <div class="user-avatar">{initial}</div>
                <span>{first_name}</span>
                <a class="logout-link" href="?logout=true">Logout</a>
            </div>
        </div>
        <div class="main-content"></div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- LOGOUT ----------
    if st.query_params.get("logout") == "true":
        authenticator.logout(location="unrendered")
        st.query_params.clear()
        st.rerun()
