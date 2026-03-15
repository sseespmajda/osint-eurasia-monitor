import sqlite3
import datetime
import config

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # Enables access by column name
    return conn

def setup_database():
    """Creates the events table or migrates it if columns are missing."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Create table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            ingested_at TEXT,
            source_channel TEXT,
            message_id INTEGER,
            raw_message TEXT,
            text_summary TEXT,
            event_type TEXT,
            sources TEXT,
            country TEXT,
            parent_id INTEGER DEFAULT NULL,
            message_hash TEXT DEFAULT NULL,
            is_high_priority INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Migration: Check for missing columns
    cursor.execute("PRAGMA table_info(events)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'message_id' not in columns:
        cursor.execute("ALTER TABLE events ADD COLUMN message_id INTEGER")
    if 'sources' not in columns:
        cursor.execute("ALTER TABLE events ADD COLUMN sources TEXT")
    if 'country' not in columns:
        print("Migrating: Adding 'country' column")
        cursor.execute("ALTER TABLE events ADD COLUMN country TEXT")
    if 'parent_id' not in columns:
        print("Migrating: Adding 'parent_id' column")
        cursor.execute("ALTER TABLE events ADD COLUMN parent_id INTEGER")
    if 'message_hash' not in columns:
        print("Migrating: Adding 'message_hash' column")
        cursor.execute("ALTER TABLE events ADD COLUMN message_hash TEXT")
    if 'is_high_priority' not in columns:
        print("Migrating: Adding 'is_high_priority' column")
        cursor.execute("ALTER TABLE events ADD COLUMN is_high_priority INTEGER")
    
    # 3. Create usage table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usage_logs (
            date TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def check_and_increment_api_usage(limit=500):
    """Checks the daily API usage and increments it if under the limit. Returns True if OK."""
    today = datetime.date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT count FROM usage_logs WHERE date = ?', (today,))
    row = cursor.fetchone()
    
    if row:
        current_count = row['count']
        if current_count >= limit:
            conn.close()
            return False, current_count
        
        cursor.execute('UPDATE usage_logs SET count = count + 1 WHERE date = ?', (today,))
        new_count = current_count + 1
    else:
        cursor.execute('INSERT INTO usage_logs (date, count) VALUES (?, 1)', (today,))
        new_count = 1
        
    conn.commit()
    conn.close()
    return True, new_count

def get_today_api_usage():
    """Returns the current API count for today."""
    today = datetime.date.today().isoformat()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT count FROM usage_logs WHERE date = ?', (today,))
    row = cursor.fetchone()
    conn.close()
    return row['count'] if row else 0

def insert_event(event_dict):
    """Inserts a new event into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO events (timestamp, ingested_at, source_channel, message_id, raw_message, text_summary, event_type, sources, country, parent_id, message_hash, is_high_priority)
        VALUES (:timestamp, :ingested_at, :source_channel, :message_id, :raw_message, :text_summary, :event_type, :sources, :country, :parent_id, :message_hash, :is_high_priority)
    ''', {**{"parent_id": None, "message_hash": None, "is_high_priority": 0}, **event_dict})
    conn.commit()
    conn.close()

def get_event_by_hash(msg_hash):
    """Returns an event if the hash exists."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM events WHERE message_hash = ? LIMIT 1', (msg_hash,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_event_sources(event_id, new_sources_json):
    """Updates the 'sources' column for an existing event."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE events SET sources = ? WHERE id = ?
    ''', (new_sources_json, event_id))
    conn.commit()
    conn.close()

def get_last_message_ids():
    """Returns a dictionary mapping channel names to their latest message_id in the DB."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT source_channel, MAX(message_id) as last_id FROM events GROUP BY source_channel')
    rows = cursor.fetchall()
    conn.close()
    return {row['source_channel']: row['last_id'] for row in rows}

def delete_event(event_id):
    """Deletes an event and its associated children/updates."""
    conn = get_connection()
    cursor = conn.cursor()
    # Delete the event itself
    cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
    # Delete any children pointing to this event
    cursor.execute('DELETE FROM events WHERE parent_id = ?', (event_id,))
    conn.commit()
    conn.close()

def get_all_events():
    """Returns all events as a list of dictionaries."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM events ORDER BY ingested_at DESC')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_database():
    """Deletes all events from the table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM events')
    conn.commit()
    conn.close()
    print("Database cleared.")

if __name__ == "__main__":
    setup_database()
    print(f"Database setup complete at {config.DB_PATH}")
