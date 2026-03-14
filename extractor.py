# -*- coding: utf-8 -*-
import json
import datetime
from google import genai
import config
import difflib

# Configure Gemini API
client = genai.Client(api_key=config.GEMINI_API_KEY)
MODEL_ID = 'gemini-3-flash-preview'

def extract_event(message_text, channel_name, recent_events=None):
    """
    Extracts data and checks for semantic duplicates, promotional content, 
     and identifies multiple countries including flag emoji hints.
    """
    if not message_text or len(message_text.strip()) < 10:
        return {"relevant": False}

    # Format recent events for context
    context_str = "None"
    if recent_events:
        context_str = "\n".join([f"- ID {e['id']}: {e['text_summary']}" for e in recent_events])

    prompt = f"""
    You are an intelligence analyst. Extract structured data from the message.
    IMPORTANT: All fields in the resulting JSON MUST be in English.

    CONTEXT:
    Below are recent events already recorded in the last 3 hours:
    {context_str}

    NEW MESSAGE:
    Source Channel: {channel_name}
    Content: {message_text}

    TASK:
    1. Determine relevance (politics/security/econ/infra). 
    2. FILTER OUT PROMOTIONAL CONTENT: Mark "relevant": false for ads, VPNs, channel promos.
    3. SEMANTIC DEDUPLICATION: Check if this is the SAME real-world incident as any in CONTEXT.
    4. COUNTRY IDENTIFICATION: Identify ALL countries mentioned or relevant. 
       - CRITICAL: Pay attention to flag emojis (e.g., 🇷🇺, 🇺🇦, 🇰🇿, 🇮🇷) as they indicate the country context.
       - Return a LIST of country names in English.
    5. CATEGORIZATION: Security, Politics, Economy, Infrastructure, or Other.

    Respond ONLY with valid JSON:
    {{
      "relevant": true/false,
      "is_duplicate": true/false,
      "duplicate_of_id": null or number,
      "timestamp": "ISO date or null",
      "text_title": "English title",
      "text_summary": "Detailed English summary",
      "event_type": "Security, Politics, Economy, Infrastructure, or Other",
      "countries": ["List", "of", "Countries"],
      "notes": "English notes"
    }}
    """

    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text.replace("```json", "", 1).replace("```", "", 1).strip()

        data = json.loads(text)
        
        # Manual fallback for VPN/Ads
        summary_lower = data.get('text_summary', '').lower()
        if any(word in summary_lower for word in ['vpn', 'subscribe to', 'bot launch', 'unlimited speed']):
            data['relevant'] = False
            
        return data
    except Exception as e:
        print(f"Error in extract_event: {e}")
        return {"relevant": False}
