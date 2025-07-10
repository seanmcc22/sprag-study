import streamlit as st
from streamlit_supabase_auth import login_form, logout_button
from supabase import create_client, Client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_user_profile(user_id: str):
    """Fetch user profile by user id."""
    response = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if response.error or response.data is None:
        return None
    return response.data


def create_profile_if_missing(user_id: str):
    """Create a profile if one doesn't exist yet."""
    profile = get_user_profile(user_id)
    if not profile:
        insert_response = supabase.table("profiles").insert({
            "id": user_id,
            "credits": 0,
            "is_subscribed": False,
            "stripe_customer_id": ""
        }).execute()
        if insert_response.error:
            st.error(f"Error creating profile: {insert_response.error.message}")


def run_login_page():
    st.title("Welcome — Please Log In or Sign Up")

    st.subheader("Login")
    session = login_form(
        url=SUPABASE_URL,
        apiKey=SUPABASE_KEY,
        providers=["google"]
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
        st.rerun()
