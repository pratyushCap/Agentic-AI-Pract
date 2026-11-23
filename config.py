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
    LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", 30))
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", 2))
    
config = Config()
