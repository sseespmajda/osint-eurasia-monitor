import asyncio
import datetime
import json
from telethon import TelegramClient, events
import config
import database
import extractor

# Initialize the Telethon client
client = TelegramClient('session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

async def handle_new_message(event):
    """Callback for new messages with semantic deduplication."""
    try:
        channel = await event.get_chat()
        channel_name = getattr(channel, 'username', 'unknown') or str(channel.id)
        message_text = event.message.message
        message_id = event.message.id

        if not message_text:
            return

        # 1. Fetch recent events (last 3 hours) for context-aware extraction
        all_events = database.get_all_events()
        # Filter for last 3 hours locally to keep context small
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_events = []
        for e in all_events:
            e_time = datetime.datetime.fromisoformat(e['ingested_at'])
            if e_time.tzinfo is None:
                e_time = e_time.replace(tzinfo=datetime.timezone.utc)
            if (now - e_time).total_seconds() < (3 * 3600):
                recent_events.append(e)

        # 2. Extract event data via Gemini with semantic check
        extracted_data = extractor.extract_event(message_text, channel_name, recent_events)

        if extracted_data.get('relevant'):
            is_dup = extracted_data.get('is_duplicate', False)
            duplicate_id = extracted_data.get('duplicate_of_id')
            
            if not is_dup or duplicate_id is None:
                # 3. New Event
                event_dict = {
                    "timestamp": extracted_data.get('timestamp') or datetime.datetime.now().isoformat(),
                    "ingested_at": datetime.datetime.now().isoformat(),
                    "source_channel": channel_name,
                    "message_id": message_id,
                    "raw_message": message_text,
                    "text_summary": extracted_data.get('text_summary', 'No summary provided'),
                    "event_type": extracted_data.get('event_type', 'unknown'),
                    "country": extracted_data.get('country', 'International'),
                    "sources": json.dumps([channel_name])
                }
                database.insert_event(event_dict)
                print(f"\n[NEW EVENT] [{channel_name}] {extracted_data.get('text_title', 'Untitled')}")
            else:
                # 4. Aggregate sources if duplicate
                # Update existing record
                for old in all_events:
                    if old['id'] == duplicate_id:
                        try:
                            sources = json.loads(old['sources']) if old.get('sources') else [old['source_channel']]
                        except:
                            sources = [old['source_channel']]
                        
                        if channel_name not in sources:
                            sources.append(channel_name)
                            database.update_event_sources(duplicate_id, json.dumps(sources))
                            print(f"s", end="", flush=True) # additional source
                        else:
                            print("d", end="", flush=True) # exact duplicate
                        break
        else:
            print(".", end="", flush=True) # irrelevant

    except Exception as e:
        print(f"\n[ERROR] in handle_new_message: {e}")

async def main():
    database.setup_database()
    print("--- OSINT Monitor Starting (SEMANTIC) ---")
    
    @client.on(events.NewMessage(chats=config.CHANNELS))
    async def handler(event):
        await handle_new_message(event)

    await client.start(phone=config.TELEGRAM_PHONE)
    print("Client is online.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
