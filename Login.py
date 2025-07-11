import streamlit as st
from streamlit_supabase_auth import login_form, logout_button
from supabase import create_client, Client
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_user_profile(user_id: str, access_token: str):
    """Fetch user profile by user id."""
    response = supabase.table("profiles").select("*").eq("id", user_id).limit(1).execute(headers={"Authorization": f"Bearer {access_token}"})
    if not response.data:
        return None

    profile = response.data[0] if isinstance(response.data, list) else response.data
    return profile


def create_profile_if_missing(user_id: str, access_token: str):
    """Create a profile if one doesn't exist yet."""
    profile = get_user_profile(user_id, access_token)
    if not profile:
        try:
            insert_response = supabase.table("profiles").insert({
                "credits": 0,
                "is_subscribed": False,
                "stripe_customer_id": ""
            }).execute(headers={"Authorization": f"Bearer {access_token}"})
            if insert_response.data:
                st.info("Profile created.")
        except Exception as e:
            st.error(f"Error creating profile: {e}")


def run_login_page():
    st.title("Welcome — Please Log In or Sign Up")

    st.subheader("Login")

    logout_button()

    session = login_form(
        url=SUPABASE_URL,
        apiKey=SUPABASE_KEY,
        providers=["google"]
    )

    st.write("DEBUG — session:", session)

    if session is not None:
        user = session.get('user')
        access_token = session.get('access_token')

        if not user:
            st.warning("No user info found in session. Please try logging in again.")
            st.stop()

        if not access_token:
            st.warning("No access token found in session. Cannot authenticate requests.")
            st.stop()

        user_id = user.get('id')
        if not user_id:
            st.warning("No user ID found. Something is wrong with the session.")
            st.stop()

        create_profile_if_missing(user_id, access_token)

        profile = get_user_profile(user_id, access_token)
        if not profile:
            st.error("Could not load your profile. Please contact support.")
            st.stop()

        st.session_state['user'] = user
        st.session_state['is_authenticated'] = True
        st.session_state['role'] = profile.get("role", "user")

        st.success("Login successful!")
        st.rerun()

    else:
        st.info("Please log in to continue.")