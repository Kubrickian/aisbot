import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
API_URL = os.getenv("API_URL")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
GROUP_FILE = os.path.join(DATA_DIR, "groups.json")
APPEALS_FILE = os.path.join(DATA_DIR, "appeals.json")
LOG_FILE = os.path.join(LOG_DIR, "bot.log")

if not all([BOT_TOKEN, API_KEY, API_URL]):
    raise ValueError("Missing BOT_TOKEN, API_KEY, or API_URL in .env")