import requests
import time
from datetime import datetime, timedelta
from .config import API_URL, API_LOGIN, API_PASSWORD
from .utils import logger

class APIManager:
    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.access_expiry = None
        self.refresh_expiry = None

    def authenticate(self):
        url = f"{API_URL}/api/auth/login"  # Still guessing, docs don’t confirm
        payload = {"login": API_LOGIN, "password": API_PASSWORD}
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self.access_expiry = datetime.now() + timedelta(minutes=5)
            self.refresh_expiry = datetime.now() + timedelta(minutes=30)
            logger.info("Successfully authenticated with API")
            return True
        except requests.RequestException as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def refresh_access_token(self):
        url = f"{API_URL}/api/auth/refresh"  # Still guessing
        payload = {"refresh_token": self.refresh_token}
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            self.access_token = data["access_token"]
            self.access_expiry = datetime.now() + timedelta(minutes=5)
            logger.info("Access token refreshed")
            return True
        except requests.RequestException as e:
            logger.error(f"Token refresh failed: {e}")
            return False

    def ensure_valid_token(self):
        now = datetime.now()
        if not self.access_token or now >= self.refresh_expiry:
            logger.info("Refresh token expired or no tokens, re-authenticating")
            return self.authenticate()
        elif now >= self.access_expiry:
            logger.info("Access token expired, refreshing")
            if not self.refresh_access_token():
                return self.authenticate()
        return True

    def get_appeal_status(self, appeal_id):
        if not self.ensure_valid_token():
            logger.error("Failed to get valid token, cannot fetch appeal status")
            return None
        
        url = f"{API_URL}/api/requests/?page=1&page_size=1&ordering=-id&search={appeal_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                logger.info(f"API response for {appeal_id}: {data}")
                # Flexible parsing based on docs’ POST response style
                if isinstance(data, list) and len(data) > 0:
                    # No explicit "status" in docs; guess it’s there or infer
                    return {"status": data[0].get("status", "pending" if "amount_to_pay" in data[0] else "unknown")}
                elif isinstance(data, dict):
                    return {"status": data.get("status", "unknown")}
                return None
            except requests.RequestException as e:
                logger.error(f"Attempt {attempt + 1}/3 failed for {appeal_id}: {e}")
                if attempt < 2:
                    time.sleep(5)
                else:
                    logger.error("All retries failed")
                    return None

api_manager = APIManager()