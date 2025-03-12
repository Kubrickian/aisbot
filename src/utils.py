import json
import logging
from .config import GROUP_FILE, APPEALS_FILE, LOG_FILE

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def escape_markdown_v2(text):
    reserved_chars = r"_*[]()~`>#+-=|{}.!"
    for char in reserved_chars:
        text = text.replace(char, f"\\{char}")
    return text

def load_groups():
    try:
        with open(GROUP_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded groups from {GROUP_FILE}: {data}")
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        default_data = {"merchant": [], "trader": [], "trader_accounts": {}}
        logger.info(f"No groups file found, initializing with: {default_data}")
        return default_data

def save_groups(groups):
    try:
        with open(GROUP_FILE, "w") as f:
            json.dump(groups, f, indent=4)
        logger.info(f"Groups saved to {GROUP_FILE}: {groups}")
    except Exception as e:
        logger.error(f"Failed to save groups: {e}")
        raise

def load_appeals_cache():
    try:
        with open(APPEALS_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded appeals cache: {len(data)} appeals")
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info("No appeals cache found, initializing empty")
        return {}

def save_appeals_cache(appeals):
    try:
        with open(APPEALS_FILE, "w") as f:
            json.dump(appeals, f, indent=4)
        logger.info(f"Saved appeals cache: {len(appeals)} appeals")
    except Exception as e:
        logger.error(f"Failed to save appeals cache: {e}")
        raise