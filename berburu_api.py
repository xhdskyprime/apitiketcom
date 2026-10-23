try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

import json
import uuid
import logging

logger = logging.getLogger("BerburuAPI")

class BerburuAPI:
    BASE_URL = "https://www.tiket.com/ms-gateway/ggwp-server/harta-karun"
    
    def __init__(self, auth_config=None):
        self.auth_config = auth_config or {}
        
        if USE_CURL_CFFI:
            self.session = requests.Session(impersonate="chrome120")
        else:
            self.session = requests.Session()
            
        user_agent = self.auth_config.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")
        account_id = self.auth_config.get("account_id", "36288055")
        device_id = self.auth_config.get("device_id", "170e297e-8dc4-4a4d-9bea-a77e9eae8104")
        cookie_str = self.auth_config.get("cookie", "")
        
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.tiket.com",
            "Referer": "https://www.tiket.com/id-id/game/berburu-tiket-murah",
            "countryCode": "id",
            "currency": "IDR",
            "deviceId": device_id,
            "lang": "id",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-audience": "tiket.com",
            "x-cookie-session-v2": "true",
            "x-country-code": "id",
            "x-country-id": "id",
            "x-currency": "IDR"
        })
        
        if account_id:
            self.session.headers["x-account-id"] = str(account_id)
            self.session.headers["accountid"] = str(account_id)
            
        if cookie_str:
            self.session.headers["Cookie"] = cookie_str

    def _get_request_headers(self, referer=None):
        headers = dict(self.session.headers)
        headers["x-request-id"] = str(uuid.uuid4())
        headers["x-correlation-id"] = str(uuid.uuid4())[:6]
        if referer:
            headers["Referer"] = referer
        return headers

    def get_player_state(self):
        """Fetches current player status, token balance, and playerId."""
        url = f"{self.BASE_URL}/player/state"
        headers = self._get_request_headers()
        try:
            res = self.session.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("code") == "SUCCESS" or data.get("status") == "SUCCESS":
                    return data.get("data", {})
            logger.error(f"Failed to fetch player state: {res.status_code} - {res.text}")
        except Exception as e:
            logger.exception(f"Error fetching player state: {e}")
        return None

    def get_campaign_product(self, campaign_id):
        """Fetches product details, session ID, countdown, and current leading player."""
        url = f"{self.BASE_URL}/campaigns/products/{campaign_id}"
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/game/berburu-tiket-murah/campaign/{campaign_id}")
        try:
            res = self.session.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("code") == "SUCCESS" or data.get("status") == "SUCCESS":
                    return data.get("data", {})
            logger.error(f"Failed to fetch campaign product: {res.status_code} - {res.text}")
        except Exception as e:
            logger.exception(f"Error fetching campaign product: {e}")
        return None

    def get_session_views(self, session_id):
        """Checks if campaign session is active."""
        url = f"{self.BASE_URL}/session/{session_id}/views"
        headers = self._get_request_headers()
        try:
            res = self.session.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            logger.exception(f"Error fetching session views: {e}")
        return None

    def hit_chest(self, session_id, custom_key=None):
        """Sends hit request to steal/claim the treasure chest."""
        url = f"{self.BASE_URL}/session/{session_id}/hit"
        headers = self._get_request_headers()
        key_val = custom_key or str(uuid.uuid4())
        payload = json.dumps({"key": key_val})
        
        try:
            res = self.session.post(url, data=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("code") == "SUCCESS" or data.get("status") == "SUCCESS":
                    return True, data.get("data", {}), data.get("serverTime")
                return False, data, None
            return False, f"HTTP {res.status_code}: {res.text}", None
        except Exception as e:
            logger.exception(f"Error hitting chest: {e}")
            return False, str(e), None
