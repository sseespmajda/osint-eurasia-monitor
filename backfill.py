import asyncio
import datetime
import json
import os
from telethon import TelegramClient, errors
import config
import database
import extractor

# Initialize the Telethon client
client = TelegramClient('session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

async def process_and_save(message, channel_name):
    """Processes a message and saves it if relevant."""
    message_text = message.message
    message_id = message.id

    if not message_text or len(message_text.strip()) < 10:
        return "irrelevant"

    # Get recent context for deduplication
    all_events = database.get_all_events()
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_context = [e for e in all_events if (now - datetime.datetime.fromisoformat(e['ingested_at']).replace(tzinfo=datetime.timezone.utc)).total_seconds() < (24 * 3600)]

    extracted_data = extractor.extract_event(message_text, channel_name, recent_context)

    if extracted_data.get('relevant'):
        is_dup = extracted_data.get('is_duplicate', False)
        duplicate_id = extracted_data.get('duplicate_of_id')

        if not is_dup or duplicate_id is None:
            # New Event
            event_dict = {
                "timestamp": extracted_data.get('timestamp') or message.date.isoformat(),
                "ingested_at": message.date.isoformat(),
                "source_channel": channel_name,
                "message_id": message_id,
                "raw_message": message_text,
                "text_summary": extracted_data.get('text_summary', 'No summary provided'),
                "event_type": extracted_data.get('event_type', 'unknown'),
                "country": extracted_data.get('country', 'International'),
                "sources": json.dumps([channel_name])
            }
            database.insert_event(event_dict)
            return "new"
    return "skip"

async def backfill():
    await client.start(phone=config.TELEGRAM_PHONE)
    database.setup_database()

    # Identify channels that have NO events yet (to avoid double processing)
    all_events = database.get_all_events()
    existing_channels = set([e['source_channel'] for e in all_events])
    
    new_channels = [c for c in config.CHANNELS if c not in existing_channels]
    
    if not new_channels:
        print("No new channels to backfill. (All channels in config already have at least one event in database)")
        return

    print(f"--- Starting backfill for {len(new_channels)} new channels ---")
    print(f"Target channels: {', '.join(new_channels)}")

    # For backfill, we look at the last 30 messages or last 3 days
    three_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)

    for channel in new_channels:
        print(f"\n[BACKFILL] Processing: {channel}")
        count = 0
        try:
            async for message in client.iter_messages(channel, limit=30):
                if message.date < three_days_ago:
                    break
                
                res = await process_and_save(message, channel)
                if res == "new":
                    print("+", end="", flush=True)
                else:
                    print(".", end="", flush=True)
                
                count += 1
                await asyncio.sleep(0.5) # Be gentle with API and LLM
                
        except errors.SecurityError:
            print(f"\n[SECURITY] Too many requests for {channel}, skipping.")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"\n[ERROR] {channel}: {e}")

    print("\n--- Backfill complete ---")

if __name__ == '__main__':
    asyncio.run(backfill())
