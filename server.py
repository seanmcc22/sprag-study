import os
import streamlit as st
from supabase import create_client, Client
import stripe
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Stripe client
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Load your Stripe product or price IDs from environment
STRIPE_PRICE_ID_5_CREDITS = os.getenv("STRIPE_PRICE_ID_5_CREDITS")
STRIPE_PRICE_ID_10_CREDITS = os.getenv("STRIPE_PRICE_ID_10_CREDITS")
STRIPE_SUBSCRIPTION_PRICE_ID_MONTHLY = os.getenv("STRIPE_SUBSCRIPTION_PRICE_ID_MONTHLY")
# Add more if needed

def ensure_user_in_profiles(user_id: str):
    """Make sure the user exists in the profiles table, if not create with defaults."""
    response = supabase.table("profiles").select("*").eq("id", user_id).execute()
    if not response.data:
        # User doesn't exist, insert new profile
        insert_resp = supabase.table("profiles").insert({
            "id": user_id,
            "credits": 0,
            "is_subscribed": False
        }).execute()
        if insert_resp.error:
            st.error(f"Error creating user profile: {insert_resp.error.message}")
        else:
            st.success("User profile created.")
    return

def update_subscription_status(user_id: str, subscribed: bool):
    """Update is_subscribed flag for the user."""
    response = supabase.table("profiles").update({
        "is_subscribed": subscribed
    }).eq("id", user_id).execute()
    if response.error:
        st.error(f"Error updating subscription status: {response.error.message}")
    return

def add_credits(user_id: str, credits_to_add: float):
    """Add credits to the user profile."""
    profile_resp = supabase.table("profiles").select("credits").eq("id", user_id).single().execute()
    if profile_resp.error:
        st.error(f"Error fetching user credits: {profile_resp.error.message}")
        return
    current_credits = profile_resp.data.get("credits", 0) or 0
    new_credits = current_credits + credits_to_add
    update_resp = supabase.table("profiles").update({"credits": new_credits}).eq("id", user_id).execute()
    if update_resp.error:
        st.error(f"Error updating credits: {update_resp.error.message}")
    else:
        st.success(f"Added {credits_to_add} credits. New total: {new_credits}")

def is_user_subscribed(stripe_customer_id: str) -> bool:
    """Check via Stripe if user has an active subscription."""
    try:
        subscriptions = stripe.Subscription.list(customer=stripe_customer_id, status='all', limit=100)
        for sub in subscriptions.auto_paging_iter():
            if sub.status == 'active':
                return True
        return False
    except Exception as e:
        st.error(f"Stripe API error: {e}")
        return False

def get_user_profile(user_id: str):
    """Fetch user profile from Supabase."""
    resp = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    if resp.error:
        st.error(f"Error fetching user profile: {resp.error.message}")
        return None
    return resp.data

# Example usage inside Streamlit app
def main():
    st.title("User Dashboard")

    # Suppose you get user_id from your auth system
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.warning("User not logged in")
        return

    ensure_user_in_profiles(user_id)
    profile = get_user_profile(user_id)

    if profile:
        st.write(f"Credits: {profile.get('credits', 0)}")
        st.write(f"Subscribed: {profile.get('is_subscribed', False)}")

if __name__ == "__main__":
    main()