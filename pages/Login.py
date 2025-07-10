import streamlit as st
from streamlit_supabase_auth import login_form, logout_button, signup_form
from supabase import create_client, Client
from menu import menu, unauthenticated_menu
from urllib.parse import parse_qs
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Login or Signup", layout="centered")
st.title("Welcome — Please Log In or Sign Up")

def redirect_to_app():
    st.experimental_set_query_params(page="app")
    st.experimental_rerun()

def get_user_profile(user_id: str):
    """Fetch user profile by user id."""
    response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    if response.error or response.data is None:
        return None
    return response.data

def create_profile_if_missing(user_id: str):
    """Create a profile if one doesn't exist yet."""
    profile = get_user_profile(user_id)
    if not profile:
        insert_response = supabase.table("profiles").insert({
            "id": user_id,
            "credits": 0,                # default credits
            "is_subscribed": False,      # default subscription status
            "stripe_customer_id": ""     # empty for now
        }).execute()
        if insert_response.error:
            st.error(f"Error creating profile: {insert_response.error.message}")

def main():
    query_params = st.experimental_get_query_params()
    access_token = query_params.get("access_token", [None])[0]
    refresh_token = query_params.get("refresh_token", [None])[0]

    if access_token and refresh_token:
        supabase.auth.set_session({
            "access_token": access_token,
            "refresh_token": refresh_token
        })

        user = supabase.auth.get_user()
        user_id = user.user.id if hasattr(user, "user") else user["id"]

        # Ensure profile exists
        create_profile_if_missing(user_id)

        st.session_state['user'] = {"id": user_id, "email": user.user.email}
        st.session_state['is_authenticated'] = True

        st.experimental_set_query_params()
        st.experimental_rerun()

    tab_login, tab_signup = st.tabs(["Login", "Sign Up"])

    with tab_login:
        st.subheader("Login")
        session = login_form(
            url=SUPABASE_URL,
            apiKey=SUPABASE_KEY,
            providers=["google"],
            email_password=True
        )
        if session:
            user = session['user']
            user_id = user['id']

            # Ensure profile exists
            create_profile_if_missing(user_id)

            st.success("Login successful!")
            profile = get_user_profile(user_id)
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
            show_terms=True,
            providers=["google"]
        )
        if new_user:
            user = new_user['user']
            user_id = user['id']

            # Ensure profile exists
            create_profile_if_missing(user_id)

            st.success("Signup successful! Please check your email to confirm.")
            profile = get_user_profile(user_id)
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