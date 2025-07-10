import streamlit as st
from streamlit_supabase_auth import login_form, logout_button
import pandas as pd
from datetime import datetime
from streamlit_shadcn_ui import metric_card
from streamlit_lightweight_charts import renderLightweightCharts
import streamlit_lightweight_charts.dataSamples as data
from supabase import create_client, Client
import stripe
import os

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Stripe
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

st.set_page_config(page_title="User Dashboard", layout="centered")

# Price IDs for credit bundles from secrets
PRICE_10_CREDITS = os.environ.get("stripe_price_id_10_credit_bundle_test")
PRICE_5_CREDITS = os.environ.get("stripe_price_id_5_credit_bundle_test")

def fetch_profile(user_id: str):
    """Fetch user profile by user id."""
    response = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
    if response.error or response.data is None:
        st.error("Error fetching profile data.")
        return None
    return response.data

def fetch_stripe_subscription(stripe_customer_id: str):
    """Fetch active subscription info from Stripe for customer."""
    try:
        subs = stripe.Subscription.list(customer=stripe_customer_id, status='active', limit=1)
        if subs.data:
            sub = subs.data[0]
            price = sub['items']['data'][0]['price']
            product = stripe.Product.retrieve(price['product'])
            return {
                'tier_name': product['name'],
                'price': price['unit_amount'] / 100,
                'currency': price['currency'].upper(),
                'current_period_end': datetime.fromtimestamp(sub['current_period_end']),
                'subscription_id': sub['id']
            }
        else:
            return None
    except Exception as e:
        st.error(f"Stripe API error: {e}")
        return None

def create_checkout_session(price_id, customer_email):
    """Create a Stripe Checkout session and return the URL."""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            customer_email=customer_email,
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='payment',
            success_url=os.environ.get("success_url"),
            cancel_url=os.environ.get("cancel_url"),
        )
        return session.url
    except Exception as e:
        st.error(f"Stripe checkout creation error: {e}")
        return None

def main():
    session = login_form(url=SUPABASE_URL, apiKey=SUPABASE_KEY, providers=["github", "google"])
    if not session:
        st.stop()

    user_id = session['user']['id']
    user_email = session['user']['email']

    profile = fetch_profile(user_id)
    if not profile:
        st.stop()

    st.header("Dashboard")
    st.write(f"👋 Welcome, **{user_email}**!")

    credits = profile.get("credits", 0)
    is_subscribed = profile.get("is_subscribed", False)
    stripe_customer_id = profile.get("stripe_customer_id")

    if is_subscribed and stripe_customer_id:
        sub_info = fetch_stripe_subscription(stripe_customer_id)
        if sub_info:
            st.success(f"Subscription Active: **{sub_info['tier_name']}**")
            st.write(f"Price: {sub_info['price']} {sub_info['currency']} per billing cycle")
            st.write(f"Renewal Date: {sub_info['current_period_end'].strftime('%Y-%m-%d')}")
            if st.button("Unsubscribe"):
                st.warning("Unsubscribe functionality not implemented yet.")
        else:
            st.warning("No active subscription found on Stripe.")
    else:
        st.warning("You are not subscribed.")

    st.metric("Credits", credits)

    st.subheader("Buy Credits")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Buy 10 Credit Bundle ($9.99)"):
            url = create_checkout_session(PRICE_10_CREDITS, user_email)
            if url:
                st.experimental_set_query_params()
                st.markdown(f"[Click here to complete purchase]({url})")
    with col2:
        if st.button("Buy 5 Credit Bundle ($4.99)"):
            url = create_checkout_session(PRICE_5_CREDITS, user_email)
            if url:
                st.experimental_set_query_params()
                st.markdown(f"[Click here to complete purchase]({url})")

    projects = [{'name': 'Project A', 'created_at': datetime.now()}, {'name': 'Project B', 'created_at': datetime.now()}]

    st.subheader("Your Projects")
    for p in projects:
        st.write(f"- **{p['name']}** created {p['created_at'].strftime('%Y-%m-%d')}")

    st.subheader("Usage Chart")
    renderLightweightCharts([{
        "chart": {
            "layout": {"textColor": 'black', "background": {"type": 'solid', "color": 'white'}}
        },
        "series": [{"type": 'Area', "data": data.seriesMultipleChartArea01}],
    }], 'area')

    st.subheader("Usage Table")
    st.table(pd.DataFrame({'Credits': [credits]}))

    with st.sidebar:
        st.divider()
        st.caption(f"Logged in as {user_email}")
        if logout_button(url=SUPABASE_URL, apiKey=SUPABASE_KEY):
            st.session_state.clear()
            st.experimental_rerun()

if __name__ == "__main__":
    main()