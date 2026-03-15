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

# Custom CSS for Event Cards and styling
st.markdown("""
<style>
    .event-card {
        background-color: #1e2130;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 15px;
        border-left: 5px solid #EF553B;
    }
    .event-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 10px;
    }
    .sector-badge {
        padding: 4px 8px;
        border-radius: 5px;
        font-weight: bold;
        font-size: 0.8rem;
    }
    .source-tag {
        background-color: #3d425c;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.75rem;
        margin-right: 5px;
    }
    .priority-badge {
        background-color: #FF0000;
        color: white;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# Define consistent colors for clusters
SECTOR_COLORS = {
    "Security": "#EF553B",
    "Politics": "#17BECF",
    "Economy": "#FF6692",
    "Infrastructure": "#FFD700",
    "Other": "#9467BD"
}

def cluster_sector(val):
    """Maps granular event types into primary clusters."""
    if not val: return "Other"
    v = val.lower()
    if any(k in v for k in ["security", "military", "defense", "war", "weapon", "drone", "conflict", "explosion"]):
        return "Security"
    if any(k in v for k in ["politics", "election", "government", "diplomacy", "treaty", "protest", "summit"]):
        return "Politics"
    if any(k in v for k in ["economy", "finance", "economics", "trade", "sanction", "market", "crime"]):
        return "Economy"
    if any(k in v for k in ["infra", "transport", "energy", "utility", "telecom", "pipeline", "grid"]):
        return "Infrastructure"
    return "Other"

@st.cache_data(ttl=300)
def load_data():
    events = database.get_all_events()
    if not events: return None
    df = pd.DataFrame(events)

    # Clustered Sector
    df['event_type'] = df['event_type'].apply(cluster_sector)

    # Handle multiple countries stored as JSON strings
    def parse_countries(val):
        if not val: return ["International"]
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list): return parsed
            return [str(parsed)]
        except: return [val]

    df['countries_list'] = df['country'].apply(parse_countries)
    df['country_display'] = df['countries_list'].apply(lambda x: ", ".join(x))
    
    df['timestamp_dt'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df['ingested_at_dt'] = pd.to_datetime(df['ingested_at'], errors='coerce')
    df['final_dt'] = df['ingested_at_dt'].fillna(df['timestamp_dt'])
    df['final_date_only'] = df['final_dt'].dt.date

    def format_sources(row):
        try:
            if row.get('sources') and isinstance(row['sources'], str):
                return json.loads(row['sources'])
            return [row['source_channel'] or "Unknown"]
        except: return [row['source_channel']]

    df['Channels_List'] = df.apply(format_sources, axis=1)
    df['Channels'] = df['Channels_List'].apply(lambda x: ", ".join(x))

    def make_link(row):
        if pd.isna(row.get('source_channel')) or pd.isna(row.get('message_id')): return None
        return f"https://t.me/{row['source_channel']}/{int(row['message_id'])}"

    df['Source Link'] = df.apply(make_link, axis=1)
    return df

st.title("🛡️ OSINT Eurasia Monitor")

# Sidebars and stats
try:
    db_mtime = os.path.getmtime(database.config.DB_PATH)
    last_update_dt = datetime.datetime.fromtimestamp(db_mtime)
    last_update = last_update_dt.strftime("%d-%B-%Y %H:%M:%S")
    is_live = (datetime.datetime.now() - last_update_dt).total_seconds() < 3600
except: 
    last_update = "Unknown"
    is_live = False

df = load_data()

if "map_clicked_country" not in st.session_state:
    st.session_state.map_clicked_country = None

st.sidebar.header("Filters & Controls")
if is_live:
    st.sidebar.success(f"● LIVE Monitoring Active")
else:
    st.sidebar.warning(f"○ Listener Offline?")

usage = database.get_today_api_usage()
st.sidebar.progress(usage / 500, text=f"API Usage: {usage}/500 requests")

st.sidebar.info(f"✅ Last DB Update:\n{last_update}")

search_query = st.sidebar.text_input("🔍 Search Summaries", placeholder="e.g. drone, strike, gas...")

if st.sidebar.button("🔄 Manual Refresh"):
    st.cache_data.clear()
    st.rerun()

if df is not None and not df.empty:
    all_countries = sorted(list(set([c for sublist in df['countries_list'] for c in sublist])))
    all_sectors = sorted(df['event_type'].unique())
    min_date = df['final_date_only'].min()
    max_date = df['final_date_only'].max()

    default_countries = all_countries
    if st.session_state.map_clicked_country:
        if st.session_state.map_clicked_country in all_countries:
            default_countries = [st.session_state.map_clicked_country]
            if st.sidebar.button("❌ Clear Map Selection"):
                st.session_state.map_clicked_country = None
                st.rerun()

    selected_countries = st.sidebar.multiselect("Select Countries", all_countries, default=default_countries)        
    selected_sectors = st.sidebar.multiselect("Select Sectors", all_sectors, default=all_sectors)
    date_range = st.sidebar.date_input("Date Range", [min_date, max_date])
else:
    selected_countries = []
    selected_sectors = []
    date_range = []

def render_event_card(row, is_priority=False):
    color = SECTOR_COLORS.get(row['event_type'], "#FFFFFF")
    card_style = f"border-left-color: {color};"
    if is_priority:
        card_style = "border-left-color: #FF0000; background-color: #2b1b1b;"
    
    st.markdown(f"""
    <div class="event-card" style="{card_style}">
        <div class="event-header">
            <span style="font-weight: bold; font-size: 1.1rem;">{row['country_display']} — {row['final_dt'].strftime("%Y-%m-%d %H:%M")}</span>
            <span class="sector-badge" style="background-color: {color if not is_priority else '#FF0000'}; color: white;">{row['event_type'].upper()}</span>
        </div>
        <div style="margin-bottom: 10px; font-size: 1.05rem; line-height: 1.5;">{row['text_summary']}</div>
        <div style="display: flex; flex-wrap: wrap; align-items: center;">
            <span style="font-size: 0.8rem; margin-right: 10px; opacity: 0.7;">SOURCES:</span>
            {" ".join([f'<span class="source-tag">{s}</span>' for s in row['Channels_List']])}
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    col_link, col_del, _ = st.columns([1, 1, 4])
    with col_link:
        if row['Source Link']: st.link_button("Telegram", row['Source Link'], icon="🔗")
    with col_del:
        if st.button("🗑️ Delete", key=f"del_{row['id']}_{'p' if is_priority else 'f'}"):
            database.delete_event(row['id'])
            st.cache_data.clear()
            st.rerun()

def main_dashboard():
    if df is None or df.empty:
        st.info("📡 No events yet — start the listener to begin monitoring.")
        return

    # Filtering
    mask = df['countries_list'].apply(lambda x: any(c in x for c in selected_countries))
    mask &= df['event_type'].isin(selected_sectors)
    if search_query:
        mask &= (df['text_summary'].str.contains(search_query, case=False, na=False)) | \
                (df['raw_message'].str.contains(search_query, case=False, na=False))
    if len(date_range) == 2:
        mask &= (df['final_date_only'] >= date_range[0]) & (df['final_date_only'] <= date_range[1])

    filtered_df = df.loc[mask].copy()
    filtered_df['is_high_priority'] = pd.to_numeric(filtered_df.get('is_high_priority', 0), errors='coerce').fillna(0)

    # --- TOP ALERTS BANNER (Always Full Summary) ---
    high_prio_banner = filtered_df[filtered_df['is_high_priority'] == 1].head(3)
    if not high_prio_banner.empty:
        st.error("### 🔥 Recent Critical Alerts")
        for _, alert in high_prio_banner.iterrows():
            with st.container():
                st.markdown(f"**{alert['country_display']}**")
                st.write(alert['text_summary'])
        st.divider()

    # TABS
    tab_global, tab_high_priority, tab_analytics = st.tabs(["🌍 Global Overview", "🔥 High Priority Tab", "📈 Analytics"])

    with tab_global:
        # Metrics
        m1, m2, m3, m4 = st.columns(4)
        with m1: st.metric("Events", len(filtered_df))
        with m2: 
            mode_countries = [c for sublist in filtered_df['countries_list'] for c in sublist]
            top_country = pd.Series(mode_countries).mode()[0] if mode_countries else "N/A"
            st.metric("Top Country", top_country)
        with m3:
            top_type = filtered_df['event_type'].mode()[0] if not filtered_df.empty else "N/A"
            st.metric("Top Sector", top_type)
        with m4:
            st.metric("Total Mentions", int(filtered_df['Channels_List'].str.len().sum()))

        st.subheader("🌍 Map Distribution (Click to filter)")
        map_df = filtered_df.explode('countries_list').groupby('countries_list').size().reset_index(name='Events')
        fig_map = px.choropleth(map_df, locations="countries_list", locationmode="country names", color="Events", hover_name="countries_list", color_continuous_scale=px.colors.sequential.Reds, template="plotly_dark")
        fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=500, clickmode='event+select')
        
        # Interactive Plotly Chart
        map_selection = st.plotly_chart(fig_map, use_container_width=True, on_select="rerun")
        
        if map_selection and "selection" in map_selection and "points" in map_selection["selection"]:
            points = map_selection["selection"]["points"]
            if points:
                loc = points[0].get("location")
                if loc and loc != st.session_state.map_clicked_country:
                    st.session_state.map_clicked_country = loc
                    st.rerun()

        st.divider()
        st.subheader("📰 Event Feed")
        feed_df = filtered_df[filtered_df['parent_id'].isna()]
        for _, row in feed_df.iterrows():
            render_event_card(row)
            # Check for children
            children = filtered_df[filtered_df['parent_id'] == row['id']]
            if not children.empty:
                with st.expander(f"🔄 View {len(children)} Updates"):
                    for _, child in children.iterrows():
                        st.caption(f"**{child['source_channel']}** at {child['final_dt'].strftime('%H:%M')}:")
                        st.write(child['text_summary'])
            st.write("")

    with tab_high_priority:
        st.subheader("🔥 High Priority Alerts")
        prio_df = filtered_df[filtered_df['is_high_priority'] == 1]
        if prio_df.empty:
            st.info("No high priority alerts found.")
        else:
            for _, row in prio_df.iterrows():
                render_event_card(row, is_priority=True)
                st.divider()

    with tab_analytics:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📊 Events Over Time")
            daily_counts = filtered_df.groupby('final_date_only').size().reset_index(name='count')
            fig_time = px.bar(daily_counts, x='final_date_only', y='count', color_discrete_sequence=['#EF553B'], template="plotly_dark")
            st.plotly_chart(fig_time, use_container_width=True)
        with c2:
            st.subheader("📉 Sector Distribution")
            sector_counts = filtered_df.groupby('event_type').size().reset_index(name='count')
            fig_sector = px.bar(sector_counts, x='event_type', y='count', color='event_type', color_discrete_map=SECTOR_COLORS, template="plotly_dark")
            st.plotly_chart(fig_sector, use_container_width=True)

if __name__ == "__main__":
    main_dashboard()
