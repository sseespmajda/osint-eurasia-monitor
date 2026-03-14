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
    Extracts data and checks for semantic duplicates and promotional content.
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
    1. Determine if the 'NEW MESSAGE' is relevant to political/security/economic/infrastructure events.
    2. FILTER OUT PROMOTIONAL CONTENT: Mark "relevant": false if the message is an advertisement, a promotion for a VPN service, a call to join another Telegram channel, or a marketing post.
    3. Check if it describes the SAME real-world incident as any event in the CONTEXT.
       - If it's the same event, mark as duplicate.
    4. Identify the primary country. Use full English names.
    5. Categorize into: Security, Politics, Economy, Infrastructure, or Other.

    Respond ONLY with valid JSON:
    {{
      "relevant": true/false,
      "is_duplicate": true/false,
      "duplicate_of_id": null or number,
      "timestamp": "ISO date or null",
      "text_title": "English title",
      "text_summary": "Detailed English summary",
      "event_type": "Security, Politics, Economy, Infrastructure, or Other",
      "country": "Primary country name in English",
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
        
        # Additional safety check for VPN/Ads in the summary just in case
        summary_lower = data.get('text_summary', '').lower()
        if any(word in summary_lower for word in ['vpn', 'subscribe to', 'bot launch', 'unlimited speed']):
            data['relevant'] = False
            
        return data
    except Exception as e:
        print(f"Error in extract_event: {e}")
        return {"relevant": False}
