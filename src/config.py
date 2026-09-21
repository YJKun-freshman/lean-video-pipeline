import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SOURCE_VIDEO_URL = os.getenv("SOURCE_VIDEO_URL")

MAX_AUDIO_MINUTES = int(os.getenv("MAX_AUDIO_MINUTES", 15))
MAX_SEGMENTS_TO_GENERATE = int(os.getenv("MAX_SEGMENTS_TO_GENERATE", 3))
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
