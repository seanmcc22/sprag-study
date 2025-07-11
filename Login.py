import streamlit as st
from streamlit_supabase_auth import login_form, logout_button
from supabase import create_client, Client
import os
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_EDGE_FUNCTION_GET_PROFILE_URL = os.environ.get("SUPABASE_EDGE_FUNCTION_GET_PROFILE_URL")
SUPABASE_EDGE_FUNCTION_CREATE_PROFILE_URL = os.environ.get("SUPABASE_EDGE_FUNCTION_CREATE_PROFILE_URL")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ✅ Helper to make a client WITH user JWT
def get_user_supabase_client(access_token: str) -> Client:
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options={
            "headers": {
                "Authorization": f"Bearer {access_token}"
            }
        }
    )

# ✅ NEW: Call Edge Function to create profile if missing
def create_profile_if_missing(user_id: str, access_token: str):
    """Calls the create-profile-if-missing Edge Function."""
    headers = {
        "Authorization": f"Bearer {access_token}"
        }
    try:
        response = requests.post(
            SUPABASE_EDGE_FUNCTION_CREATE_PROFILE_URL,
            headers=headers,
            json={"user_id": user_id}
        )
        if response.status_code != 200:
            st.error(f"Failed to create profile: {response.status_code} — {response.text}")
            return False
        return True
    except Exception as e:
        st.error(f"Error calling create-profile-if-missing Edge Function: {e}")
        return False

# ✅ Fetch the profile via Edge Function (uses JWT, respects RLS)
def get_user_profile_via_edge_function(access_token: str):
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    try:
        response = requests.get(SUPABASE_EDGE_FUNCTION_GET_PROFILE_URL, headers=headers)
        if response.status_code != 200:
            st.error(f"Failed to fetch profile: {response.status_code} — {response.text}")
            return None
        return response.json()
    except Exception as e:
        st.error(f"Error calling get-profile Edge Function: {e}")
        return None

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

        # ✅ Call Edge Function to create the profile if missing
        if not create_profile_if_missing(user_id, access_token):
            st.stop()

        # ✅ Then fetch the profile using the other Edge Function
        profile = get_user_profile_via_edge_function(access_token)
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