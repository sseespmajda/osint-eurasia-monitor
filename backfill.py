import asyncio
import datetime
import json
from telethon import TelegramClient
import config
import database
import extractor

# Initialize the Telethon client
client = TelegramClient('session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

async def process_message(message, channel_name):
    """Processes a single historical message with semantic deduplication."""
    message_text = message.message
    message_id = message.id
    
    # Get the actual channel username
    chat = await message.get_chat()
    actual_username = getattr(chat, 'username', channel_name)
    if not actual_username and hasattr(chat, 'id'):
        actual_username = str(chat.id)

    if not message_text or len(message_text.strip()) < 10:
        return

    # Fetch all events currently in DB to check for duplicates
    # For backfill, we look at the entire newly-built set
    recent_events = database.get_all_events()

    # 1. Extract event data AND check for duplicates via Gemini API
    extracted_data = extractor.extract_event(message_text, actual_username, recent_events)

    if extracted_data.get('relevant'):
        is_dup = extracted_data.get('is_duplicate', False)
        duplicate_id = extracted_data.get('duplicate_of_id')
        
        if not is_dup or duplicate_id is None:
            # 3. New Event
            event_dict = {
                "timestamp": extracted_data.get('timestamp') or message.date.isoformat(),
                "ingested_at": message.date.isoformat(),
                "source_channel": actual_username,
                "message_id": message_id,
                "raw_message": message_text,
                "text_summary": extracted_data.get('text_summary', 'No summary provided'),
                "event_type": extracted_data.get('event_type', 'unknown'),
                "country": extracted_data.get('country', 'International'),
                "sources": json.dumps([actual_username])
            }
            database.insert_event(event_dict)
            print(f"+", end="", flush=True) # New
        else:
            # 4. Aggregate sources if duplicate
            # Find the existing event in the DB to update it
            for old in recent_events:
                if old['id'] == duplicate_id:
                    try:
                        sources = json.loads(old['sources']) if old.get('sources') else [old['source_channel']]
                    except:
                        sources = [old['source_channel']]
                    
                    if actual_username not in sources:
                        sources.append(actual_username)
                        database.update_event_sources(duplicate_id, json.dumps(sources))
                        print(f"s", end="", flush=True) # source
                    else:
                        print("d", end="", flush=True) # exact duplicate
                    break

async def main():
    # 1. Setup and Clear DB
    database.setup_database()
    database.clear_database()
    
    # 2. Define Start Date (19:00 March 12, 2026)
    start_date = datetime.datetime(2026, 3, 12, 19, 0, 0, tzinfo=datetime.timezone.utc)
    
    print(f"--- Starting SEMANTIC Backfill from {start_date} ---")
    
    async with client:
        for channel_info in config.CHANNELS:
            print(f"\nProcessing {channel_info}...")
            async for message in client.iter_messages(channel_info, offset_date=start_date, reverse=True):
                await process_message(message, channel_info)
    
    print("\n--- Backfill Complete ---")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBackfill stopped.")
