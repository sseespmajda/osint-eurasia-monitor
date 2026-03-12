import streamlit as st
import os

# --- Helper to handle both local and Streamlit Cloud ---
def get_secret(key, default=None):
    # Try Streamlit Secrets first (for Cloud deployment)
    try:
        if key in st.secrets:
            return st.secrets[key]
    except:
        pass
    
    # Try Environment Variables second
    env_val = os.getenv(key)
    if env_val:
        return env_val
        
    # Return default
    return default

# 1. API Keys (Set these locally or in Streamlit Secrets)
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "YOUR_LOCAL_KEY_HERE")

# 2. Telegram Credentials
TELEGRAM_API_ID = int(get_secret("TELEGRAM_API_ID", 123456)) 
TELEGRAM_API_HASH = get_secret("TELEGRAM_API_HASH", "YOUR_REAL_HASH_HERE")
TELEGRAM_PHONE = get_secret("TELEGRAM_PHONE", "+0000000000")

# 3. Database
DB_PATH = "events.db"

# 4. Monitored Channels
CHANNELS = [
    "lentachold",
    "agentstvonews",
    "milinfolive",
    "astrapress",
    "rbc_news",
    "uniannet",
    "AMK_Mapping",
    "UkrzalInfo",
    "energyofukraine",
    "V_Zelenskiy_official",
    "dtek_ua",
    "geran_gerbera"
]
