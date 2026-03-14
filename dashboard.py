import streamlit as st
import pandas as pd
import database
import datetime
import plotly.express as px
import json
import os

# Ensure database is updated/migrated on startup
database.setup_database()

# Page configuration
st.set_page_config(page_title="OSINT Eurasia Monitor", layout="wide", page_icon="🛡️")

# Define consistent colors for new sectors
SECTOR_COLORS = {
    "Security": "#EF553B",       # Red
    "Politics": "#17BECF",       # Teal
    "Economy": "#FF6692",        # Pink
    "Infrastructure": "#FFD700", # Gold
    "Other": "#9467BD"           # Muted Purple
}

# --- Data Cleaning Logic for Broad Categories ---
def categorize_sector(val):
    if not val:
        return "Other"
    val = val.strip().lower()
    if any(k in val for k in ["war", "security", "terrorism", "safety", "military"]):
        return "Security"
    if any(k in val for k in ["politics", "political", "relation", "diplomat"]):
        return "Politics"
    if any(k in val for k in ["economy", "economic", "sanction", "trade", "finance"]):
        return "Economy"
    if any(k in val for k in ["infra", "energy", "transport", "communication", "rail", "electric"]):
        return "Infrastructure"
    return "Other"

@st.cache_data(ttl=300)
def load_data():
    events = database.get_all_events()
    if not events:
        return None
    df = pd.DataFrame(events)

    for col in ['message_id', 'sources', 'country', 'event_type']:
        if col not in df.columns:
            df[col] = None

    # Apply re-categorization to simplify labels
    df['event_type'] = df['event_type'].apply(categorize_sector)
    df['country'] = df['country'].fillna('International')
    
    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df['ingested_at_dt'] = pd.to_datetime(df['ingested_at'], errors='coerce')
    df['final_dt'] = df['ingested_at_dt'].fillna(df['timestamp_dt'])
    df['final_date_only'] = df['final_dt'].dt.date

    def format_sources(row):
        try:
            if row.get('sources') and isinstance(row['sources'], str):
                source_list = json.loads(row['sources'])
                return ", ".join(source_list)
            return row['source_channel'] if not pd.isna(row['source_channel']) else "Unknown"
        except:
            return row['source_channel']

    df['Channels'] = df.apply(format_sources, axis=1)

    def make_link(row):
        if pd.isna(row.get('source_channel')) or pd.isna(row.get('message_id')):
            return None
        return f"https://t.me/{row['source_channel']}/{int(row['message_id'])}"

    df['Source Link'] = df.apply(make_link, axis=1)
    return df

st.title("🛡️ OSINT Eurasia Monitor")

# Get database file modification time
try:
    db_mtime = os.path.getmtime(database.config.DB_PATH)
    last_update = datetime.datetime.fromtimestamp(db_mtime).strftime("%d-%B-%Y %H:%M:%S")
except:
    last_update = "Unknown"

# --- Sidebar Filters ---
df = load_data()

st.sidebar.header("Filters & Controls")
st.sidebar.info(f"✅ Database Last Updated:\n{last_update}")

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()
    st.rerun()

if df is not None and not df.empty:
    all_countries = sorted(df['country'].unique())
    all_sectors = sorted(df['event_type'].unique())
    min_date = df['final_date_only'].min()
    max_date = df['final_date_only'].max()

    if "map_selected_country" not in st.session_state:
        st.session_state.map_selected_country = None

    default_countries = all_countries
    if st.session_state.map_selected_country:
        if st.session_state.map_selected_country in all_countries:
            default_countries = [st.session_state.map_selected_country]
            if st.sidebar.button("Clear Map Filter"):
                st.session_state.map_selected_country = None
                st.rerun()

    selected_countries = st.sidebar.multiselect("Select Countries", all_countries, default=default_countries)        
    selected_sectors = st.sidebar.multiselect("Select Sectors", all_sectors, default=all_sectors)
    date_range = st.sidebar.date_input("Date Range", [min_date, max_date])
else:
    selected_countries = []
    selected_sectors = []
    date_range = []

def main_dashboard():
    if df is None or df.empty:
        st.info("📡 No events yet — start the listener to begin monitoring.")
        return

    # Filter the Dataframe
    mask = (df['country'].isin(selected_countries)) & (df['event_type'].isin(selected_sectors))
    if len(date_range) == 2:
        mask &= (df['final_date_only'] >= date_range[0]) & (df['final_date_only'] <= date_range[1])

    filtered_df = df.loc[mask].copy()

    # --- Top Metric Cards ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Events", len(filtered_df))
    with m2:
        top_country = filtered_df['country'].mode()[0] if not filtered_df.empty else "N/A"
        st.metric("Top Country", top_country)
    with m3:
        top_type = filtered_df['event_type'].mode()[0] if not filtered_df.empty else "N/A"
        st.metric("Primary Sector", top_type)
    with m4:
        total_mentions = filtered_df['Channels'].str.split(',').str.len().sum()
        st.metric("Total Mentions", int(total_mentions) if not pd.isna(total_mentions) else 0)

    st.divider()

    # --- Map Visualization (Interactive) ---
    st.subheader("🌍 Geographic Distribution (Click to filter)")
    country_counts = df.groupby('country').size().reset_index(name='Events')
    
    fig_map = px.choropleth(country_counts, 
                            locations="country", 
                            locationmode="country names",
                            color="Events",
                            hover_name="country",
                            color_continuous_scale=px.colors.sequential.Reds,
                            template="plotly_dark")
    fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=400, clickmode='event+select')
    
    selected_map_data = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun")
    
    if selected_map_data and "selection" in selected_map_data:
        points = selected_map_data["selection"].get("points", [])
        if points:
            clicked_country = points[0].get("location")
            if clicked_country and clicked_country != st.session_state.map_selected_country:
                st.session_state.map_selected_country = clicked_country
                st.rerun()

    if filtered_df.empty:
        st.warning("No events found matching the current filters.")
        return

    # --- Charts ---
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 Events Over Time")
        daily_counts = filtered_df.groupby('final_date_only').size().reset_index(name='count')
        fig_time = px.area(daily_counts, x='final_date_only', y='count',
                          labels={'final_date_only': 'Date', 'count': 'Number of Events'},
                          color_discrete_sequence=['#EF553B'])
        st.plotly_chart(fig_time, use_container_width=True)

    with c2:
        st.subheader("📊 Sector Distribution")
        sector_counts = filtered_df.groupby('event_type').size().reset_index(name='count')
        fig_sector = px.bar(sector_counts, x='event_type', y='count',
                            color='event_type',
                            color_discrete_map=SECTOR_COLORS,
                            labels={'event_type': 'Sector', 'count': 'Total'})
        st.plotly_chart(fig_sector, use_container_width=True)

    # --- Full News Feed (Replacing Table for Text Wrapping) ---
    st.subheader("📰 Detailed Event Feed")
    
    # Display headers for the custom feed
    h1, h2, h3, h4 = st.columns([1, 1, 1, 3])
    with h1: st.markdown("**Date/Time**")
    with h2: st.markdown("**Country**")
    with h3: st.markdown("**Sector**")
    with h4: st.markdown("**Summary**")
    st.divider()

    for _, row in filtered_df.iterrows():
        r1, r2, r3, r4 = st.columns([1, 1, 1, 3])
        with r1:
            st.write(row['final_dt'].strftime("%Y-%m-%d %H:%M"))
        with r2:
            st.write(row['country'])
        with r3:
            # Color badge simulation
            color = SECTOR_COLORS.get(row['event_type'], "#FFFFFF")
            st.markdown(f"<span style='color:{color}; font-weight:bold;'>{row['event_type']}</span>", unsafe_allow_html=True)
        with r4:
            st.write(row['text_summary'])
            st.caption(f"Sources: {row['Channels']}")
            if row['Source Link']:
                st.link_button("View Original Telegram Message", row['Source Link'], icon="🔗")
        st.divider()

if __name__ == "__main__":
    main_dashboard()
