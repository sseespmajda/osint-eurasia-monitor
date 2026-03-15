import asyncio
import datetime
import json
import subprocess
import os
import time
import hashlib
from telethon import TelegramClient, events, errors
import config
import database
import extractor

# Initialize the Telethon client
client = TelegramClient('session', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH)

# Buffer for batch processing
message_buffer = []
BUFFER_LOCK = asyncio.Lock()
BATCH_WINDOW = 300 # 5 minutes

def get_msg_hash(text):
    """Generates a stable hash for message text."""
    return hashlib.sha256(text.strip().encode('utf-8')).hexdigest()

def sync_to_cloud():
    """Automatically pushes the local database to GitHub."""
    try:
        print("\n[SYNC] Pushing updates to Cloud...")
        branch_res = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True)
        branch = branch_res.stdout.strip() or "main"
        subprocess.run(["git", "pull", "--rebase", "origin", branch], capture_output=True)
        # Add and check specifically for database changes
        subprocess.run(["git", "add", "events.db"], check=True)
        status_res = subprocess.run(["git", "status", "--porcelain", "events.db"], capture_output=True, text=True)
        if not status_res.stdout.strip():
            print("[SYNC] No database changes.")
            return
        
        subprocess.run(["git", "commit", "-m", f"Auto-sync DB: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"], check=True, capture_output=True)
        subprocess.run(["git", "push", "origin", branch], check=True, capture_output=True)
        print(f"[SYNC] Cloud updated.")
    except Exception as e:
        print(f"[SYNC ERROR] {e}")

def is_urgent_locally(text):
    """Simple keyword check for immediate urgency flagging."""
    keywords = [
        'срочно', 'молния', 'важно', 'взрыв', 'прилет', 'пво', 'ракета', 'бпла', 'тревога', 
        'breaking', 'urgent', 'explosion', 'impact', 'missile', 'drone', 'attack'
    ]
    t = text.lower()
    return any(k in t for k in keywords)

async def process_batch():
    """Processes all messages currently in the buffer."""
    global message_buffer
    async with BUFFER_LOCK:
        if not message_buffer:
            return
        
        current_batch = list(message_buffer)
        message_buffer = []

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{now_str}] [BATCH] Processing {len(current_batch)} messages...")
    
    all_events = database.get_all_events()
    now = datetime.datetime.now(datetime.timezone.utc)
    recent_context = [e for e in all_events if (now - datetime.datetime.fromisoformat(e['ingested_at']).replace(tzinfo=datetime.timezone.utc)).total_seconds() < (24 * 3600)]

    # 1. First Pass: Check for EXACT hashes in DB (Instant save)
    to_extract = []
    for msg in current_batch:
        h = get_msg_hash(msg['text'])
        existing = database.get_event_by_hash(h)
        if existing:
            print(f" [{now_str}] [HASH MATCH] Skipping Gemini for duplicate content from {msg['channel']}")
            # Just update sources for the existing event
            try:
                sources = json.loads(existing['sources'])
                if msg['channel'] not in sources:
                    sources.append(msg['channel'])
                    database.update_event_sources(existing['id'], json.dumps(sources))
            except: pass
        else:
            to_extract.append(msg)

    if not to_extract:
        print(f"[{now_str}] [BATCH] All messages were exact duplicates. No API calls made.")
        return

    # 2. Second Pass: Call Gemini for unique content
    print(f"[{now_str}] [BATCH] Calling Gemini for {len(to_extract)} unique messages...")
    results = extractor.extract_batch_events(to_extract, recent_context)
    
    new_event_ids = {} # For batch-internal deduplication tracking

    for i, res in enumerate(results):
        if not res.get('relevant'): continue
        
        msg = to_extract[i]
        msg_hash = get_msg_hash(msg['text'])
        
        is_dup = res.get('is_duplicate', False)
        dup_id = res.get('duplicate_of_id')
        dup_idx = res.get('duplicate_of_msg_index')

        # Combine AI priority and Local priority
        is_high_priority = 1 if (res.get('is_high_priority') or is_urgent_locally(msg['text'])) else 0

        # Handle batch-internal duplicates
        if is_dup and dup_idx is not None and dup_idx in new_event_ids:
            dup_id = new_event_ids[dup_idx]

        if not is_dup or dup_id is None:
            # New Event
            countries = res.get('countries') or ["International"]
            event_dict = {
                "timestamp": res.get('timestamp') or msg['date'].isoformat(),
                "ingested_at": msg['date'].isoformat(),
                "source_channel": msg['channel'],
                "message_id": msg['id'],
                "raw_message": msg['text'],
                "text_summary": res.get('text_summary', 'No summary'),
                "event_type": res.get('event_type', 'Other'),
                "country": json.dumps(countries),
                "sources": json.dumps([msg['channel']]),
                "parent_id": None,
                "message_hash": msg_hash,
                "is_high_priority": is_high_priority
            }
            database.insert_event(event_dict)
            # Fetch back the ID for internal batch referencing
            latest = database.get_all_events()[0]
            new_event_ids[i] = latest['id']
        else:
            # Link as Child
            parent_id = dup_id
            countries = res.get('countries') or ["International"]
            event_dict = {
                "timestamp": res.get('timestamp') or msg['date'].isoformat(),
                "ingested_at": msg['date'].isoformat(),
                "source_channel": msg['channel'],
                "message_id": msg['id'],
                "raw_message": msg['text'],
                "text_summary": "Batch Update",
                "event_type": res.get('event_type', 'Other'),
                "country": json.dumps(countries),
                "sources": json.dumps([msg['channel']]),
                "parent_id": parent_id,
                "message_hash": msg_hash,
                "is_high_priority": is_high_priority
            }
            database.insert_event(event_dict)

    sync_to_cloud()

async def batch_timer():
    """Runs process_batch every X minutes, adjusting cadence based on API usage."""
    while True:
        # Check current usage to adjust cadence
        usage = database.get_today_api_usage()
        
        current_window = BATCH_WINDOW
        if usage >= 450:
            current_window = 1800 # 30 minutes (Emergency mode)
            print(f"\n[CADENCE] Usage high ({usage}/500). Slowing to 30m window.")
        elif usage >= 400:
            current_window = 900  # 15 minutes
            print(f"\n[CADENCE] Usage moderate ({usage}/500). Slowing to 15m window.")
            
        await asyncio.sleep(current_window)
        await process_batch()

async def sync_gaps():
    """Fetches messages missed while the listener was offline."""
    print("\n[GAP SYNC] Checking for missed messages...")
    last_ids = database.get_last_message_ids()
    
    total_missed = 0
    for channel in config.CHANNELS:
        last_id = last_ids.get(channel)
        if not last_id: continue
        
        try:
            # Fetch messages since the last known ID
            async for message in client.iter_messages(channel, min_id=last_id, limit=100):
                if not message.message or len(message.message.strip()) < 15:
                    continue
                
                async with BUFFER_LOCK:
                    message_buffer.append({
                        "id": message.id,
                        "text": message.message,
                        "channel": channel,
                        "date": message.date
                    })
                total_missed += 1
        except Exception as e:
            print(f" [GAP ERROR] {channel}: {e}")
    
    if total_missed > 0:
        print(f"[GAP SYNC] Queued {total_missed} missed messages for processing.")
        await process_batch()
    else:
        print("[GAP SYNC] No missed messages found.")

async def main():
    database.setup_database()
    
    await client.start(phone=config.TELEGRAM_PHONE)
    
    # Run gap sync once before starting live monitoring
    await sync_gaps()
    
    # Start the timer task
    asyncio.create_task(batch_timer())

    @client.on(events.NewMessage(chats=config.CHANNELS))
    async def handler(event):
        if not event.message.message or len(event.message.message.strip()) < 15:
            return

        chat = await event.get_chat()
        channel_name = getattr(chat, 'username', None) or str(chat.id)
        
        async with BUFFER_LOCK:
            message_buffer.append({
                "id": event.message.id,
                "text": event.message.message,
                "channel": channel_name,
                "date": event.message.date
            })
        print(".", end="", flush=True)

    await client.start(phone=config.TELEGRAM_PHONE)
    print(f"Listening (Batch window: {BATCH_WINDOW}s)...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
