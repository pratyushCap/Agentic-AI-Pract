# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # LLM Configuration
    LLM_API_KEY = os.getenv("LLM_API_KEY")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://openai.generative.engine.capgemini.com/v1")
    LLM_MODEL = os.getenv("LLM_MODEL", "amazon.nova-lite-v1:0")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))
    LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 2048))
    
    # Validation
    if not LLM_API_KEY:
        raise SystemExit(
            "Error: LLM_API_KEY is not set. Add it to your .env file."
        )

config = Config()
