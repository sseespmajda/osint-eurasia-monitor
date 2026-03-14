# -*- coding: utf-8 -*-
import json
import datetime
from google import genai
import config
import difflib

# Configure Gemini API
client = genai.Client(api_key=config.GEMINI_API_KEY)
MODEL_ID = 'gemini-3-flash-preview'

def extract_batch_events(messages_batch, recent_events=None):
    """
    Analyzes a batch of messages in a single Gemini call to save credits.
    Returns a list of extraction results.
    """
    if not messages_batch:
        return []

    context_str = "None"
    if recent_events:
        context_str = "\n".join([f"- ID {e['id']}: {e['text_summary']}" for e in recent_events])

    # Format the batch for the prompt
    batch_input = "\n\n".join([f"MESSAGE #{i}:\nChannel: {m['channel']}\nContent: {m['text']}" for i, m in enumerate(messages_batch)])

    prompt = f"""
    You are an intelligence analyst. Analyze this BATCH of {len(messages_batch)} messages.
    IMPORTANT: All fields in the resulting JSON MUST be in English.

    CONTEXT (Recent incidents in the last 24 hours):
    {context_str}

    MESSAGES TO PROCESS:
    {batch_input}

    TASK:
    For EACH message in the batch:
    1. Determine relevance (politics/security/econ/infra/culture/sports). 
    2. FILTER OUT PROMOTIONAL CONTENT: Mark "relevant": false for ads, VPNs, promos.
    3. SEMANTIC MERGING: Check if this is the EXACT SAME real-world incident as any in CONTEXT OR any other message in THIS BATCH.
       - If it's a duplicate of a CONTEXT event, set "is_duplicate": true and "duplicate_of_id" to that ID.
       - If it's a duplicate of another message in this batch, set "is_duplicate": true and "duplicate_of_msg_index" to that index.
    4. COUNTRY IDENTIFICATION: Identify ALL relevant countries.
    5. CATEGORIZATION: Security, Politics, Economy, Infrastructure, Sports and Culture, or Other.
    6. IMPORTANCE: Determine if this is a CRITICALLY IMPORTANT event (major explosion, death of official, huge military shift, nuclear event, etc).

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
        "text_summary": "Detailed English summary",
        "event_type": "Sector",
        "countries": ["List"],
        "notes": "Notes"
      }},
      ...
    ]
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.replace("```json", "", 1).replace("```", "", 1).strip()

        results = json.loads(text)
        return results
    except Exception as e:
        print(f"Error in extract_batch_events: {e}")
        return [{"relevant": False}] * len(messages_batch)
