# -*- coding: utf-8 -*-
import json
import datetime
from google import genai
import config
import database
import difflib

# Configure Gemini API
client = genai.Client(api_key=config.GEMINI_API_KEY)
MODEL_ID = 'gemini-3-flash-preview'

def is_ad_or_promo(text):
    """Lite local check to weed out obvious Telegram ads/promos and sports noise without LLM."""
    if not text: return True
    t = text.lower()
    # Ad and Garbage keywords
    trash_keywords = [
        '#реклама', 'подписывайтесь', 'vpn', 'crypto', 'trading', 'бонусы',
        'зарабатывать', 'курсы', 'скидка', 'промокод', 'реферальная',
        'подписка', 'бесплатно', 'инвестиции', 'сигналы', 'обучение',
        'p2p', 'арбитраж', 'казино', 'casino', 'ставка', 'выплаты',
        'mma', 'ufc', 'fight night', 'чемпионат', 'победил', 'нокаут',
        'матч', 'лига', 'league', 'футбол', 'football', 'basketball', 'теннис'
    ]
    return any(k in t for k in trash_keywords)

def extract_event(text, channel, recent_events=None):
    """Wrapper to maintain compatibility with legacy single-event calls."""
    if is_ad_or_promo(text):
        return {"relevant": False, "note": "Local ad filter"}
        
    msg = {"text": text, "channel": channel, "id": 0, "date": datetime.datetime.now()}
    res = extract_batch_events([msg], recent_events)
    return res[0] if res else {"relevant": False}

def extract_batch_events(messages_batch, recent_events=None):
    """
    Analyzes a batch of messages in a single Gemini call to save credits.
    Returns a list of extraction results.
    """
    if not messages_batch:
        return []

    # Pre-filter ads locally before sending to Gemini
    processed_results = [None] * len(messages_batch)
    batch_to_send = []
    
    for i, m in enumerate(messages_batch):
        if is_ad_or_promo(m['text']):
            processed_results[i] = {"relevant": False, "note": "Local ad filter"}
        else:
            batch_to_send.append((i, m))

    if not batch_to_send:
        return processed_results

    context_str = "None"
    if recent_events:
        context_str = "\n".join([f"- ID {e['id']}: {e['text_summary']}" for e in recent_events])

    # Format the batch for the prompt
    batch_input = "\n\n".join([f"MESSAGE #{i}:\nChannel: {m['channel']}\nContent: {m['text']}" for i, m in batch_to_send])

    prompt = f"""
    You are an intelligence analyst. Analyze this BATCH of {len(messages_batch)} messages.
    IMPORTANT: All fields in the resulting JSON MUST be in English.

    CONTEXT (Recent incidents in the last 24 hours):
    {context_str}

    MESSAGES TO PROCESS:
    {batch_input}

    TASK:
    For EACH message in the batch:
    1. Determine relevance (Strictly Politics, Security, Economy, or Infrastructure). 
    2. FILTER OUT ALL OTHER CONTENT: Mark "relevant": false for sports, culture, celebrity news, ads, VPNs, promos.
    3. SEMANTIC MERGING (STRICT): Check if this is the EXACT SAME real-world incident as any in CONTEXT OR any other message in THIS BATCH.
       - ONLY merge if the details (location, subject, time) match exactly.
       - If the topics are different, "is_duplicate" MUST be false. 
       - If it is a DIFFERENT incident in the SAME country, it is NOT a duplicate.
       - If it's a duplicate of a CONTEXT event, set "is_duplicate": true and "duplicate_of_id" to that ID.
       - If it's a duplicate of another message in this batch, set "is_duplicate": true and "duplicate_of_msg_index" to that index.
    4. COUNTRY IDENTIFICATION: Identify ALL relevant countries.
    # 5. CATEGORIZATION: Use ONLY these EXACT strings:
       - Security
       - Politics
       - Economy
       - Infrastructure
       - Other
    DO NOT use any other words. If it is "Military", write "Security". If it is "Finance", write "Economy".
    
    6. IMPORTANCE: Determine if this is a HIGH PRIORITY event.
       - YES: Active kinetic strikes, explosions, missile launches, nuclear threats, death of a national leader, declaration of war.
       - NO: Political rumors, succession speculation, routine diplomatic meetings, economic forecasts.

    Respond ONLY with a JSON array containing objects for each message index:
    [
      {{
        "index": 0,
        "relevant": true/false,
        "is_duplicate": true/false,
        "duplicate_of_id": null or number,
        "duplicate_of_msg_index": null or number,
        "is_high_priority": true/false,
        "timestamp": "ISO date",
        "text_title": "English title",
        "text_summary": "Detailed English summary (Full and comprehensive)",
        "event_type": "One of: Security, Politics, Economy, Infrastructure, Other",
        "countries": ["List"],
        "notes": "Notes"
      }},
      ...
    ]
    """

    # Check API limit (500 per day)
    ok, count = database.check_and_increment_api_usage(limit=500)
    if not ok:
        print(f"[ERROR] API daily limit reached ({count}/500). Skipping batch.")
        return [{"relevant": False}] * len(messages_batch)

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.replace("```json", "", 1).replace("```", "", 1).strip()

        llm_results = json.loads(text)
        
        # Map LLM results back to original indices
        # llm_results is an array of objects. Each object has an 'index' matching the original index.
        # However, it's safer to map them explicitly.
        res_map = {r['index']: r for r in llm_results}
        
        final_results = []
        for i in range(len(messages_batch)):
            if processed_results[i] is not None:
                final_results.append(processed_results[i])
            else:
                final_results.append(res_map.get(i, {"relevant": False, "note": "LLM missing index"}))
                
        return final_results
    except Exception as e:
        print(f"Error in extract_batch_events: {e}")
        return [{"relevant": False}] * len(messages_batch)

