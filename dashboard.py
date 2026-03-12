import streamlit as st
import pandas as pd
import database
import datetime
import plotly.express as px
import json

# Ensure database is updated/migrated on startup
database.setup_database()

# 10. Page configuration
st.set_page_config(page_title="OSINT Eurasia Monitor", layout="wide")

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

def format_custom_date(dt):
    """Formats datetime to DD-Month-YYYY HHMMhrs"""
    if pd.isna(dt):
        return "N/A"
    return dt.strftime("%d-%B-%Y %H%Mhrs")

def load_data():
    events = database.get_all_events()
    if not events:
        return None
    df = pd.DataFrame(events)
    
    # --- Resilience: Ensure columns exist ---
    for col in ['message_id', 'sources', 'country']:
        if col not in df.columns:
            df[col] = None
    
    # Fill empty countries
    df['country'] = df['country'].fillna('International')

    # Ensure timestamp is datetime
    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df['ingested_at_dt'] = pd.to_datetime(df['ingested_at'], errors='coerce')
    
    # Prioritize ingested_at (Telegram message time) for the dashboard feed 
    # to avoid historical dates mentioned in the text (like Feb 18) 
    # taking over the current news feed.
    df['final_dt'] = df['ingested_at_dt'].fillna(df['timestamp_dt'])
    df['final_date_only'] = df['final_dt'].dt.date
    
    # Apply custom date formatting for display
    df['Formatted Date'] = df['final_dt'].apply(format_custom_date)
    
    # Process sources column
    def format_sources(row):
        try:
            if row.get('sources') and isinstance(row['sources'], str):
                source_list = json.loads(row['sources'])
                return ", ".join(source_list)
            return row['source_channel'] if not pd.isna(row['source_channel']) else "Unknown"
        except:
            return row['source_channel']
            
    df['Channels'] = df.apply(format_sources, axis=1)
    
    # Create source link (Telegram link)
    def make_link(row):
        if pd.isna(row.get('source_channel')) or pd.isna(row.get('message_id')):
            return None
        return f"https://t.me/{row['source_channel']}/{int(row['message_id'])}"
    
    df['Source Link'] = df.apply(make_link, axis=1)
    
    return df

st.title("🛡️ OSINT Eurasia Monitor")

# Refresh Button
if st.button("🔄 Manual Refresh"):
    st.rerun()

# --- Sidebar Filters (OUTSIDE Fragment) ---
df_for_filters = load_data()

st.sidebar.header("Filters")
if df_for_filters is not None and not df_for_filters.empty:
    # Country Filter
    all_countries = sorted(df_for_filters['country'].unique())
    selected_countries = st.sidebar.multiselect("Select Countries", all_countries, default=all_countries)

    # Sector Filter
    all_sectors = sorted(df_for_filters['event_type'].unique())
    selected_sectors = st.sidebar.multiselect("Select Sectors", all_sectors, default=all_sectors)
    
    # Date Filter
    min_date = df_for_filters['final_date_only'].min()
    max_date = df_for_filters['final_date_only'].max()
    date_range = st.sidebar.date_input("Date Range", [min_date, max_date])
else:
    selected_countries = []
    selected_sectors = []
    date_range = []

@st.fragment(run_every="5m")
def dashboard_content(selected_countries, selected_sectors, date_range):
    df = load_data()

    if df is None or df.empty:
        st.info("📡 No events yet — start the listener to begin monitoring.")
    else:
        # Filter the Dataframe
        mask = (df['country'].isin(selected_countries)) & (df['event_type'].isin(selected_sectors))
        if len(date_range) == 2:
            mask &= (df['final_date_only'] >= date_range[0]) & (df['final_date_only'] <= date_range[1])
        
        filtered_df = df.loc[mask]

        # --- Top Metric Cards ---
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Events", len(filtered_df))
        with col2:
            top_country = filtered_df['country'].mode()[0] if not filtered_df.empty else "N/A"
            st.metric("Most Active Country", top_country)
        with col3:
            top_type = filtered_df['event_type'].mode()[0] if not filtered_df.empty else "N/A"
            st.metric("Most Active Sector", top_type)
        with col4:
            total_mentions = filtered_df['Channels'].str.split(',').str.len().sum()
            st.metric("Total Mentions", total_mentions)

        st.divider()

        # --- Charts ---
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("Events Over Time")
            daily_counts = filtered_df.groupby('final_date_only').size().reset_index(name='count')
            fig_time = px.bar(daily_counts, x='final_date_only', y='count', 
                              labels={'final_date_only': 'Date', 'count': 'Number of Events'},
                              color_discrete_sequence=['#636EFA'])
            st.plotly_chart(fig_time, width='stretch')

        with c2:
            st.subheader("Sector Distribution")
            sector_counts = filtered_df.groupby('event_type').size().reset_index(name='count')
            fig_sector = px.bar(sector_counts, x='event_type', y='count', 
                                color='event_type',
                                color_discrete_map=SECTOR_COLORS,
                                labels={'event_type': 'Sector', 'count': 'Total'})
            st.plotly_chart(fig_sector, width='stretch')

        # --- Full Data Table ---
        st.subheader("Detailed Event Feed")
        
        # Display columns configuration
        display_cols = ['Formatted Date', 'country', 'event_type', 'text_summary', 'Channels', 'Source Link']
        
        # We use st.table for full text expansion, or we can use st.dataframe with no truncation
        # however st.table is the most reliable for 'seeing everything' at once.
        st.table(
            filtered_df[display_cols].rename(columns={
                "Formatted Date": "Date/Time",
                "country": "Country",
                "event_type": "Sector",
                "text_summary": "Summary",
                "Channels": "Reporting Channels",
                "Source Link": "Link"
            })
        )

# Call the fragment with the current filter selections
dashboard_content(selected_countries, selected_sectors, date_range)
