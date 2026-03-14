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

# Define consistent colors for sectors
SECTOR_COLORS = {
    "security": "#EF553B",      # Red
    "war": "#B6E880",           # Green
    "terrorism": "#000000",      # Black
    "sanctions": "#AB63FA",     # Purple
    "public safety": "#FFA15A",  # Orange
    "healthcare": "#19D3F3",    # Cyan
    "economic": "#FF6692",      # Pink
    "political": "#17BECF",     # Teal
    "infrastructure": "#FFD700", # Gold
    "energy": "#9467BD"         # Muted Purple
}

@st.cache_data(ttl=300)
def load_data():
    events = database.get_all_events()
    if not events:
        return None
    df = pd.DataFrame(events)

    for col in ['message_id', 'sources', 'country']:
        if col not in df.columns:
            df[col] = None

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

    # Initial state for map selection
    if "map_selected_country" not in st.session_state:
        st.session_state.map_selected_country = None

    # Handle sidebar country multiselect
    # If a map selection happened, we can pre-set the selection
    default_countries = all_countries
    if st.session_state.map_selected_country:
        if st.session_state.map_selected_country in all_countries:
            default_countries = [st.session_state.map_selected_country]
            # Reset map selection after setting filter if needed, or keep it
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
    
    # Capture map selection (requires Streamlit 1.35+)
    selected_map_data = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun")
    
    # Process selection data
    if selected_map_data and "selection" in selected_map_data:
        points = selected_map_data["selection"].get("points", [])
        if points:
            # Get the country from the clicked point
            # Plotly choropleth points usually have 'location' which is the country name
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

    # --- Full Data Table ---
    st.subheader("📰 Detailed Event Feed")
    display_df = filtered_df[['final_dt', 'country', 'event_type', 'text_summary', 'Channels', 'Source Link']].copy()
    display_df['final_dt'] = display_df['final_dt'].dt.strftime("%Y-%m-%d %H:%M")
    
    st.dataframe(
        display_df,
        column_config={
            "final_dt": "Date/Time",
            "country": "Country",
            "event_type": "Sector",
            "text_summary": "Summary",
            "Channels": "Sources",
            "Source Link": st.column_config.LinkColumn("Link")
        },
        use_container_width=True,
        hide_index=True
    )

    with st.expander("🔍 View Recent Summary Details"):
        for _, row in filtered_df.head(5).iterrows():
            st.markdown(f"**{row['final_dt']} | {row['country']} | {row['event_type']}**")
            st.write(row['text_summary'])
            st.caption(f"Sources: {row['Channels']}")
            st.divider()

if __name__ == "__main__":
    main_dashboard()
