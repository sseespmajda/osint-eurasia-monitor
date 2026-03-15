# OSINT Eurasia Monitor

## Project Overview
A real-time Telegram monitoring dashboard for geopolitical, security, and economic events in the Eurasia and MENA regions.

## Tech Stack
- **Frontend:** [Streamlit](https://streamlit.io/) (Dashboard & Visualization)
- **Data Ingestion:** [Telethon](https://docs.telethon.dev/) (Telegram Client)
- **AI/LLM:** [Google Gemini GenAI SDK](https://ai.google.dev/gemini-api/docs) (using `gemini-3-flash-preview`)
- **Database:** SQLite (`events.db`)
- **Visuals:** Pandas & Plotly

## Architecture
- `dashboard.py`: The main Streamlit application. Provides "Global Overview", "Analytics", and "Event Feed" tabs.
- `listener.py`: Async Telegram listener. Batches incoming messages every 5 minutes (default `BATCH_WINDOW = 300`) to minimize LLM costs and improve semantic context for deduplication.
- `extractor.py`: Logic for extracting structured data from raw messages using Gemini. Performs relevance filtering, semantic merging (linking updates to parent events), and English summarization.
- `database.py`: Manages the SQLite schema and migrations. Stores events with fields for countries, event types (Security, Politics, etc.), and high-priority flags.
- `config.py`: Stores API keys, database path, and the list of 40+ monitored Telegram channels.
- `backfill.py`: Utility to ingest historical messages (last 30 messages or 3 days) for newly added channels.

## Key Features
- **Semantic Deduplication:** Uses Gemini to identify if multiple messages from different channels describe the same real-world event.
- **High-Priority Alerts:** Automatically flags critical incidents (explosions, major political shifts) via keyword matching and LLM analysis.
- **Auto-Sync:** `listener.py` includes a `sync_to_cloud()` function that automatically commits and pushes `events.db` to the GitHub repository.
- **English-Only Summaries:** Regardless of the source language (Russian, Ukrainian, etc.), summaries are generated in English.

## Current State (as of March 15, 2026)
- Monitoring 40+ channels across Eurasia, Central Asia, and the Middle East.
- Dashboard is functional with filtering by country, sector, and date.
- Analytics include events over time, sector distribution, and top source channels.
- **Data Policy:** Live monitoring only. Historical backfilling is disabled as of March 15, 2026.

## Roadmap / Future Improvements
- [ ] Improved entity extraction (specific cities, equipment types).
- [ ] Notification system (Telegram/Email) for high-priority alerts.
- [ ] Multi-user support or access control for the dashboard.
- [ ] Enhanced mapping (heatmaps or cluster maps).
- [ ] Sentiment analysis or trend detection for geopolitical shifts.
