import os

import pandas as pd
import requests
import streamlit as st


API_BASE_URL = os.getenv("RIDEUS_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="RideUS Author Dashboard", page_icon="R", layout="wide")

st.markdown(
    """
    <style>
      .stApp { background: #f5f7fb; }
      div[data-testid="stMetric"] {
        background: white;
        border: 1px solid rgba(20, 28, 42, .08);
        border-radius: 14px;
        padding: 16px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str):
    response = requests.get(f"{API_BASE_URL}{path}", timeout=8)
    response.raise_for_status()
    return response.json()


st.title("RideUS Author Dashboard")
st.caption("Separate author/admin website for the FastAPI + SQL + ML ride booking backend.")

with st.sidebar:
    st.header("Backend")
    st.code(API_BASE_URL)
    refresh = st.button("Refresh data", use_container_width=True)

try:
    health = api_get("/health")
    summary = api_get("/admin/summary")
    users = api_get("/admin/users")
    bookings = api_get("/admin/bookings")
    contacts = api_get("/admin/contacts")
    ai_insights = api_get("/admin/ai-insights")
except Exception as exc:
    st.error(f"Backend is not reachable: {exc}")
    st.info("Run this first: `python -m uvicorn backend_api:app --host 0.0.0.0 --port 8000 --reload`")
    st.stop()

st.success(f"Backend status: {health['status']} | Database: {health['database']}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Riders", summary["total_users"])
c2.metric("Total bookings", summary["total_bookings"])
c3.metric("Active rides", summary["active_rides"])
c4.metric("Revenue", f"Rs {summary['estimated_revenue']:.0f}")

c5, c6 = st.columns(2)
c5.metric("Support requests", summary["support_requests"])
c6.metric("Avg distance", f"{summary['average_distance_km']} km")

st.subheader("AI Insights")
i1, i2, i3 = st.columns(3)
i1.metric("Top ride type", ai_insights["top_ride_type"])
i2.metric("Urgent support", ai_insights["urgent_support_count"])
i3.metric("Average fare", f"Rs {ai_insights['average_fare']:.0f}")

for recommendation in ai_insights["recommendations"]:
    st.info(recommendation)

if ai_insights["support_categories"]:
    st.write("Support categories")
    st.bar_chart(pd.DataFrame(
        [{"category": key, "count": value} for key, value in ai_insights["support_categories"].items()]
    ), x="category", y="count")

st.subheader("Riders")
if users:
    st.dataframe(pd.DataFrame(users), use_container_width=True, hide_index=True)
else:
    st.info("No riders yet. Save a profile from the Android app first.")

st.subheader("Bookings")
if bookings:
    bookings_df = pd.DataFrame(bookings)
    st.dataframe(bookings_df, use_container_width=True, hide_index=True)

    chart_df = bookings_df.groupby("ride_type", as_index=False)["estimated_fare"].sum()
    st.bar_chart(chart_df, x="ride_type", y="estimated_fare")
else:
    st.info("No bookings yet. Book from Android app or call `/book-ride` API.")

st.subheader("Contact Requests")
if contacts:
    st.dataframe(pd.DataFrame(contacts), use_container_width=True, hide_index=True)
else:
    st.info("No contact requests yet.")
