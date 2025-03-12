import requests
from .config import API_KEY, API_URL
from .utils import logger

def get_appeal_status(appeal_id):
    """Fetch appeal status from API."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    try:
        response = requests.get(f"{API_URL}/{appeal_id}", headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"API response for {appeal_id}: {data}")
        return data  # e.g., {"id": "APPEAL_123", "status": "pending", "timestamp": "..."}
    except requests.RequestException as e:
        logger.error(f"API call failed for {appeal_id}: {e}")
        return None