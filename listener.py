import asyncio
import datetime
import json
import subprocess
import os
import time
from telethon import TelegramClient, events, errors
import config
import database
import extractor

# Initialize the Telethon client
client = TelegramClient('session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

def sync_to_cloud():
    """Automatically pushes the local database to GitHub."""
    try:
        print("\n[SYNC] Pushing updates to Cloud...")
        # Get current branch name
        branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch = branch_res.stdout.strip() or "main"

        # Check if remote exists
        remote_check = subprocess.run(["git", "remote"], capture_output=True, text=True)
        if "origin" not in remote_check.stdout:
            print("[SYNC ERROR] Remote 'origin' not found.")
            return

        # Attempt to pull, but ignore errors if it's just a "no upstream" issue
        subprocess.run(["git", "pull", "--rebase", "origin", branch], capture_output=True)
        
        # Add and push the database
        subprocess.run(["git", "add", "events.db"], check=True)
        
        # Check if there are changes to commit
        status_res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status_res.stdout.strip():
            print("[SYNC] No changes to push.")
            return

        subprocess.run(["git", "commit", "-m", f"Auto-sync: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", branch], check=True, capture_output=True)
        print(f"[SYNC] Cloud Dashboard updated successfully via branch '{branch}'.")
    except Exception as e:
        print(f"[SYNC ERROR] Could not sync to GitHub: {e}")

async def process_and_save(message, channel_name, all_events_context):
    """Common logic for processing and saving a message."""
    try:
        message_text = message.message
        message_id = message.id

        if not message_text or len(message_text.strip()) < 10:
            return "irrelevant"

        # 1. Extract & Semantic Check
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_context = [e for e in all_events_context if (now - datetime.datetime.fromisoformat(e['ingested_at']).replace(tzinfo=datetime.timezone.utc)).total_seconds() < (6 * 3600)]

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
            else:
                # Aggregate Sources
                for old in all_events_context:
                    if old['id'] == duplicate_id:
                        try:
                            sources = json.loads(old['sources']) if old.get('sources') else [old['source_channel']]  
                        except:
                            sources = [old['source_channel']]

                        if channel_name not in sources:
                            sources.append(channel_name)
                            database.update_event_sources(duplicate_id, json.dumps(sources))
                            return "source"
                        return "dup"
        return "irrelevant"
    except Exception as e:
        print(f"[ERROR] processing message from {channel_name}: {e}")
        return "error"

async def catch_up():
    """Fetches missed messages since the last recorded event."""
    all_events = database.get_all_events()
    if not all_events:
        print("[CATCH-UP] No events in database, skipping catch-up.")
        return False

    latest_event = max(all_events, key=lambda x: x['ingested_at'])
    last_event_time = datetime.datetime.fromisoformat(latest_event['ingested_at'])
    if last_event_time.tzinfo is None:
        last_event_time = last_event_time.replace(tzinfo=datetime.timezone.utc)

    print(f"--- Catching up on missed messages since {last_event_time} ---")

    any_new = False
    for channel in config.CHANNELS:
        print(f"[CATCH-UP] Checking channel: {channel}...")
        try:
            count = 0
            # Reduced limit to avoid hitting Telethon Security errors for large batches
            async for message in client.iter_messages(channel, limit=150):
                msg_date = message.date
                if msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=datetime.timezone.utc)

                if msg_date <= last_event_time:
                    break
                
                res = await process_and_save(message, channel, all_events)
                if res in ["new", "source"]:
                    any_new = True
                    print("+" if res == "new" else "s", end="", flush=True)
                
                count += 1
                if count >= 150:
                    print(f"\n[CATCH-UP] Limit reached for {channel}, stopping.")
                    break
                
                # Tiny sleep to avoid consecutive ignored message errors
                await asyncio.sleep(0.1)

        except errors.SecurityError as e:
            print(f"\n[TELETHON SECURITY ERROR] {e}. Skipping {channel} for now.")
            await asyncio.sleep(2) # Pause for longer
        except Exception as e:
            print(f"\n[CATCH-UP ERROR] {channel}: {e}")

    print("\n--- Catch-up complete. ---")
    return any_new

async def main():
    database.setup_database()

    @client.on(events.NewMessage(chats=config.CHANNELS))
    async def handler(event):
        try:
            all_events = database.get_all_events()
            chat = await event.get_chat()
            channel_name = getattr(chat, 'username', None) or str(chat.id)
            
            res = await process_and_save(event.message, channel_name, all_events)       
            if res in ["new", "source"]:
                print(f"\n[EVENT] Updating Cloud...")
                sync_to_cloud()
        except Exception as e:
            print(f"[HANDLER ERROR] {e}")

    await client.start(phone=config.TELEGRAM_PHONE)

    if await catch_up():
        sync_to_cloud()

    print("Listening for new messages...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
