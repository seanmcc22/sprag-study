import streamlit as st
from streamlit_supabase_auth import login_form, logout_button, signup_form
from supabase import create_client, Client
from menu import menu, unauthenticated_menu

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Login or Signup", layout="centered")
st.title("Welcome — Please Log In or Sign Up")

def redirect_to_app():
    # Adjust this depending on your multipage routing or main page
    st.experimental_set_query_params(page="app")
    st.experimental_rerun()

def get_user_profile(user_id: str):
    """Fetch user profile by user id."""
    response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    if response.error or response.data is None:
        st.error("Error loading user profile.")
        return None
    return response.data

def main():
    # Show tabs for login and signup
    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        st.subheader("Login")
        session = login_form(
            url=SUPABASE_URL,
            apiKey=SUPABASE_KEY,
            providers=["google"],
            email_password=True  # Enables email/password login alongside OAuth
        )
        if session:
            user = session['user']
            st.success("Login successful!")
            # Fetch profile for role or extra info
            profile = get_user_profile(user['id'])
            st.session_state['user'] = user
            st.session_state['is_authenticated'] = True
            st.session_state['role'] = profile.get("role", "user") if profile else "user"
            redirect_to_app()

    with tab_signup:
        st.subheader("Create a new account")
        new_user = signup_form(
            url=SUPABASE_URL,
            apiKey=SUPABASE_KEY,
            email_password=True,
            show_terms=True,  # Optional: add checkbox for terms
            providers=["google"]
        )
        if new_user:
            user = new_user['user']
            st.success("Signup successful! Please check your email to confirm.")
            # You might want to wait for email verification before redirecting
            # For demo, we’ll assume immediate login after signup:
            profile = get_user_profile(user['id'])
            st.session_state['user'] = user
            st.session_state['is_authenticated'] = True
            st.session_state['role'] = profile.get("role", "user") if profile else "user"
            redirect_to_app()

    if st.session_state.get('is_authenticated'):
        menu()
        with st.sidebar:
            st.markdown(f"**Logged in as: *{st.session_state['user']['email']}***")
            if logout_button(url=SUPABASE_URL, apiKey=SUPABASE_KEY):
                st.session_state.clear()
                st.experimental_rerun()
    else:
        unauthenticated_menu()

if __name__ == "__main__":
    main()