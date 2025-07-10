import streamlit as st

def authenticated_menu():
    """Sidebar menu for logged-in users"""
    st.sidebar.page_link("app.py", label="Home")
    st.sidebar.page_link("pages/2_Dashboard.py", label="Dashboard")
    st.sidebar.page_link("Login.py", label="Logout")

    role = st.session_state.get('role')
    if role in ["admin", "super-admin"]:
        st.sidebar.page_link("pages/admin.py", label="Manage users")
    if role == "super-admin":
        st.sidebar.page_link("pages/super-admin.py", label="Manage admin access")

def unauthenticated_menu():
    """Sidebar menu for logged-out users"""
    st.sidebar.page_link("app.py", label="Home")

def menu():
    """Render correct menu based on auth"""
    if st.session_state.get('user') and st.session_state.get('role'):
        authenticated_menu()
    else:
        unauthenticated_menu()

def menu_with_redirect():
    """Force redirect if unauthenticated"""
    if not st.session_state.get('user') or not st.session_state.get('role'):
        from Login import run_login_page as run_login_page
        run_login_page()
        st.stop()
    menu()

def menu_home():
    """Alias for using menu on Home page"""
    menu()