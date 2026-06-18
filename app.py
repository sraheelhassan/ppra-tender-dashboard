"""
PPRA Tender Intelligence Dashboard
Interactive filtering demo for consulting clients.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = "data/tenders.csv"

st.set_page_config(
    page_title="PPRA Tender Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .ppra-header {
        background: linear-gradient(135deg, #0f1729 0%, #16213e 55%, #0f3460 100%);
        padding: 26px 34px;
        border-radius: 14px;
        margin-bottom: 22px;
        color: white;
    }
    .ppra-header h1 { margin: 0; font-size: 1.8rem; }
    .ppra-header p { margin: 4px 0 0 0; opacity: 0.75; font-size: 0.92rem; }
    .urgent-pill   { background:#fee2e2; color:#991b1b; padding:2px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    .warning-pill  { background:#fef3c7; color:#92400e; padding:2px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    .safe-pill     { background:#d1fae5; color:#065f46; padding:2px 10px; border-radius:20px; font-size:0.78rem; font-weight:600; }
    div[data-testid="stMetric"] {
        background: white; border-radius: 10px; padding: 14px 18px;
        box-shadow: 0 1px 6px rgba(0,0,0,0.07); border-left: 4px solid #0f3460;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner=False)
def load_data():
    df = pd.read_csv(DATA_PATH)
    df["closing_dt"] = pd.to_datetime(df["closing_date"], format="%b %d, %Y", errors="coerce")
    df["advertised_dt"] = pd.to_datetime(df["advertised_date"], format="%b %d, %Y", errors="coerce")
    df["days_to_close"] = (df["closing_dt"] - pd.Timestamp.now().normalize()).dt.days
    for col in ["title", "organization", "category", "location", "status"]:
        df[col] = df[col].fillna("Unknown")
    return df


def urgency_label(days):
    if pd.isna(days):
        return "Unknown"
    if days <= 3:
        return "🔴 Urgent"
    if days <= 7:
        return "🟠 This Week"
    return "🟢 Open"


def refresh_data():
    with st.spinner("Fetching latest tenders from PPRA — this takes ~30s..."):
        subprocess.run([sys.executable, "scraper.py"], check=True, cwd=os.path.dirname(__file__) or ".")
    st.cache_data.clear()
    st.rerun()


# ── Header ───────────────────────────────────────────────────────────────
last_modified = (
    datetime.fromtimestamp(os.path.getmtime(DATA_PATH)).strftime("%b %d, %Y — %I:%M %p")
    if os.path.exists(DATA_PATH) else "Never"
)
st.markdown(f"""
<div class="ppra-header">
    <h1>🏛️ PPRA Tender Intelligence Dashboard</h1>
    <p>Live monitoring of Pakistan government procurement tenders &nbsp;·&nbsp; Last updated: {last_modified}</p>
</div>
""", unsafe_allow_html=True)

if not os.path.exists(DATA_PATH):
    st.warning("No data found yet. Click below to fetch tenders from PPRA.")
    if st.button("🔄 Fetch Tenders Now", type="primary"):
        refresh_data()
    st.stop()

df = load_data()

# ── Sidebar filters ──────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔍 Filters")

    if st.button("🔄 Refresh Data", use_container_width=True):
        refresh_data()

    search = st.text_input("Keyword search", placeholder="e.g. medicine, construction, IT...")

    orgs = sorted(df["organization"].unique())
    selected_orgs = st.multiselect("Organization", orgs)

    cats = sorted(df["category"].unique())
    selected_cats = st.multiselect("Category", cats)

    urgency = st.radio(
        "Urgency",
        ["All", "🔴 Closing ≤ 3 days", "🟠 Closing ≤ 7 days", "🟢 Closing later"],
        index=0,
    )

    min_date = df["closing_dt"].min()
    max_date = df["closing_dt"].max()
    if pd.notna(min_date) and pd.notna(max_date):
        date_range = st.date_input(
            "Closing date range",
            value=(min_date.date(), max_date.date()),
            min_value=min_date.date(),
            max_value=max_date.date(),
        )
    else:
        date_range = None

    st.divider()
    if st.button("↺ Reset all filters", use_container_width=True):
        st.rerun()

# ── Apply filters ────────────────────────────────────────────────────────
filtered = df.copy()

if search:
    mask = (
        filtered["title"].str.contains(search, case=False, na=False)
        | filtered["organization"].str.contains(search, case=False, na=False)
        | filtered["description"].str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]

if selected_orgs:
    filtered = filtered[filtered["organization"].isin(selected_orgs)]

if selected_cats:
    filtered = filtered[filtered["category"].isin(selected_cats)]

if urgency == "🔴 Closing ≤ 3 days":
    filtered = filtered[filtered["days_to_close"] <= 3]
elif urgency == "🟠 Closing ≤ 7 days":
    filtered = filtered[filtered["days_to_close"] <= 7]
elif urgency == "🟢 Closing later":
    filtered = filtered[filtered["days_to_close"] > 7]

if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    filtered = filtered[
        (filtered["closing_dt"].dt.date >= start) & (filtered["closing_dt"].dt.date <= end)
    ]

# ── KPI row ──────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
k1.metric("Filtered Tenders", f"{len(filtered):,}", f"of {len(df):,} total")
k2.metric("Closing This Week", int((filtered["days_to_close"] <= 7).sum()))
k3.metric("Organizations", filtered["organization"].nunique())
avg_days = filtered["days_to_close"].mean()
k4.metric("Avg Days to Close", f"{avg_days:.0f}" if pd.notna(avg_days) else "—")

st.write("")

# ── Charts ───────────────────────────────────────────────────────────────
c1, c2 = st.columns(2)

with c1:
    top_orgs = filtered["organization"].value_counts().head(10).sort_values()
    if not top_orgs.empty:
        fig = px.bar(
            top_orgs, orientation="h",
            labels={"value": "Tenders", "index": ""},
            title="Top Organizations",
            color_discrete_sequence=["#0f3460"],
        )
        fig.update_layout(showlegend=False, height=360, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)

with c2:
    cat_counts = filtered["category"].value_counts()
    if not cat_counts.empty:
        fig2 = px.pie(
            values=cat_counts.values, names=cat_counts.index,
            title="By Category", hole=0.45,
        )
        fig2.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)

# ── Table ────────────────────────────────────────────────────────────────
st.subheader(f"📋 Tenders ({len(filtered):,})")

display = filtered.copy()
display["Urgency"] = display["days_to_close"].apply(urgency_label)
display = display[[
    "tender_number", "title", "organization", "category",
    "closing_date", "closing_time", "Urgency", "status", "detail_url",
]].rename(columns={
    "tender_number": "Tender No",
    "title": "Title",
    "organization": "Organization",
    "category": "Category",
    "closing_date": "Closing Date",
    "closing_time": "Closing Time",
    "status": "Status",
    "detail_url": "Link",
})
display = display.sort_values("Closing Date")

st.dataframe(
    display,
    use_container_width=True,
    height=460,
    hide_index=True,
    column_config={
        "Link": st.column_config.LinkColumn("Details", display_text="View →"),
    },
)

st.download_button(
    "⬇️ Download filtered results as CSV",
    data=display.to_csv(index=False).encode("utf-8"),
    file_name=f"ppra_tenders_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv",
)
