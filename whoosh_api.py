try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False

import json
import uuid
import re
import logging

logger = logging.getLogger("WhooshAPI")

class WhooshAPI:
    BASE_URL = "https://www.tiket.com/ms-gateway"
    
    def __init__(self, auth_config=None):
        self.auth_config = auth_config or {}
        
        if USE_CURL_CFFI:
            self.session = requests.Session(impersonate="chrome120")
        else:
            self.session = requests.Session()
        
        user_agent = self.auth_config.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        account_id = self.auth_config.get("account_id", "36288055")
        device_id = self.auth_config.get("device_id", "170e297e-8dc4-4a4d-9bea-a77e9eae8104")
        cookie_str = self.auth_config.get("cookie", "")
        
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "*/*",
            "Accept-Language": "id,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Content-Type": "application/json",
            "Origin": "https://www.tiket.com",
            "Referer": "https://www.tiket.com/id-id/kereta-api",
            "countryCode": "id",
            "currency": "IDR",
            "deviceId": device_id,
            "lang": "id",
            "priority": "u=1, i",
            "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="120", "Chromium";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-audience": "tiket.com",
            "x-city-id": "Pasarkemis",
            "x-cookie-session-v2": "true",
            "x-country-code": "id",
            "x-country-id": "id",
            "x-currency": "IDR",
            "x-region-id": "JB",
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

    def search_whoosh(self, origin="IDHMA", destination="IDTLA", departure_date="2026-08-28", adult=1):
        """
        Search Kereta Cepat Whoosh journeys.
        departure_date format: YYYY-MM-DD or YYYYMMDD
        """
        date_param = departure_date.replace("-", "")
        url = f"{self.BASE_URL}/tix-train-search-v2/v8/whoosh/journeys"
        params = {
            "orig": origin,
            "otype": "STATION",
            "dest": destination,
            "dtype": "STATION",
            "ttype": "ONE_WAY",
            "ddate": date_param,
            "rdate": "",
            "acount": adult,
            "icount": 0
        }
        
        referer = f"https://www.tiket.com/id-id/kereta-api/search?d={origin}&dt=STATION&a={destination}&at=STATION&date={departure_date}&adult={adult}&infant=0&child=0&tripType=oneway&productType=whoosh"
        headers = self._get_request_headers(referer=referer)
        
        logger.info(f"Mengirim permintaan pencarian Whoosh {origin} -> {destination} ({departure_date})...")
        res = self.session.get(url, params=params, headers=headers, timeout=15)
        
        if res.status_code == 403:
            raise Exception("HTTP 403 Forbidden: Akses ditolak Cloudflare. Perbarui cookie di config.json.")
        if res.status_code == 401:
            raise Exception("HTTP 401 Unauthorized: Sesi expired. Silakan perbarui cookie di config.json.")
        if res.status_code != 200:
            raise Exception(f"Gagal mencari kereta Whoosh: HTTP {res.status_code}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon pencarian tidak valid: {data}")
            
        res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        depart_journeys = res_data.get("departJourneys") if isinstance(res_data.get("departJourneys"), dict) else {}
        journeys = depart_journeys.get("journeys") or []
        
        results = []
        for j in journeys:
            if not isinstance(j, dict):
                continue
            
            j_id = j.get("id")
            origin_code = (j.get("originStation") or {}).get("code", origin)
            dest_code = (j.get("destinationStation") or {}).get("code", destination)
            dep_date = j.get("departDate", departure_date)
            dep_time = (j.get("departTime") or "")[:5]
            arr_time = (j.get("arriveTime") or "")[:5]
            
            segs = j.get("segmentSchedules") or [{}]
            seg = segs[0] if isinstance(segs, list) and segs else {}
            
            train_number = seg.get("trainNumber", "Whoosh")
            train_name = seg.get("trainName", "Whoosh")
            sub_class = (seg.get("subClass") or {}).get("code", "PE")
            wagon_class = (seg.get("wagonClass") or {}).get("code", j_id)
            wagon_detail = (seg.get("wagonClass") or {}).get("detail", "Ekonomi Premium")
            available_seats = seg.get("availableSeats", 0)
            
            fares = seg.get("scheduleFares") or [{}]
            fare = fares[0] if isinstance(fares, list) and fares else {}
            price = fare.get("priceAmount", 0)
            
            if j_id:
                results.append({
                    "id": j_id,
                    "originCode": origin_code,
                    "destinationCode": dest_code,
                    "departDate": dep_date,
                    "subClass": sub_class,
                    "trainNumber": train_number,
                    "trainName": train_name,
                    "wagonClass": wagon_class,
                    "wagonDetail": wagon_detail,
                    "depart_time": dep_time,
                    "arrival_time": arr_time,
                    "price": price,
                    "available_seats": available_seats
                })
                
        return results

    def add_to_cart(self, schedule_item, adult_count=1):
        """
        Add Whoosh journey to cart. Returns (cart_id, secret).
        """
        url = f"{self.BASE_URL}/tix-train-trx/v6/whoosh/carts?result=summary"
        payload = {
            "passengerCount": {
                "adult": adult_count,
                "infant": 0
            },
            "selectedJourneys": {
                "depart": {
                    "schedules": [
                        {
                            "id": schedule_item["id"],
                            "originCode": schedule_item["originCode"],
                            "destinationCode": schedule_item["destinationCode"],
                            "departDate": schedule_item["departDate"],
                            "subClass": schedule_item["subClass"],
                            "trainNumber": schedule_item["trainNumber"],
                            "wagonClass": schedule_item["wagonClass"]
                        }
                    ]
                }
            },
            "productType": "WHOOSH"
        }
        
        headers = self._get_request_headers()
        res = self.session.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal add to cart Whoosh: HTTP {res.status_code} - {res.text}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon add to cart tidak valid: {data}")
            
        if data.get("code") != "SUCCESS":
            raise Exception(f"Gagal add to cart Whoosh: {data.get('message') or data}")
            
        res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        cart_id = res_data.get("cartId") or res_data.get("id")
        secret = res_data.get("secret")
        
        if not cart_id or not secret:
            raise Exception(f"Gagal add to cart (Cart ID / Secret tidak ditemukan): {data}")
            
        return cart_id, secret

    def get_cart(self, cart_id, secret):
        url = f"{self.BASE_URL}/tix-train-trx/v6/whoosh/carts/{cart_id}?secret={secret}&result=details&phoneVerified=true"
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/kereta-api/booking?cartId={cart_id}&secret={secret}")
        res = self.session.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.warning(f"Get cart HTTP status: {res.status_code}")
            return None
        return res.json()

    def update_passengers(self, cart_id, secret, contact_cfg, adults_cfg):
        """
        Update contact and passenger details in cart.
        """
        url = f"{self.BASE_URL}/tix-train-trx/v6/whoosh/carts/{cart_id}?secret={secret}"
        
        profile_id_contact = contact_cfg.get("profileId", 36143998)
        try:
            profile_id_contact = int(profile_id_contact)
        except Exception:
            pass
            
        contact_payload = {
            "title": contact_cfg.get("title", "Mr").capitalize(),
            "fullName": contact_cfg.get("fullName"),
            "areaCode": contact_cfg.get("areaCode", "+62"),
            "phone": contact_cfg.get("phone"),
            "emailAddress": contact_cfg.get("email"),
            "profileId": profile_id_contact
        }
        
        passengers_payload = []
        for adult in adults_cfg:
            pid = adult.get("profileId", 0)
            try:
                pid = int(pid)
            except Exception:
                pass
                
            passengers_payload.append({
                "paxType": "ADULT",
                "title": adult.get("title", "Mr").capitalize(),
                "fullName": adult.get("fullName"),
                "profileId": pid,
                "identityType": "identityNumber",
                "identityNumber": str(adult.get("identityNumber", "")),
                "passportNumber": "",
                "countryCode": ""
            })
            
        payload = {
            "cartId": cart_id,
            "secret": secret,
            "contact": contact_payload,
            "passengers": passengers_payload
        }
        
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/kereta-api/booking?cartId={cart_id}&secret={secret}")
        res = self.session.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal update data penumpang Whoosh: HTTP {res.status_code} - {res.text}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon update penumpang tidak valid: {data}")
            
        if data.get("code") != "SUCCESS":
            raise Exception(f"Update penumpang Whoosh gagal: {data.get('message') or data}")
            
        return data

    def create_order(self, cart_id, secret, insurances=None):
        """
        Create order for Whoosh Kereta Cepat.
        """
        url = f"{self.BASE_URL}/tix-train-trx/v7/whoosh/orders"
        
        if insurances is None:
            insurances = [
                {"type": "tiket-trainrefundkcic-aswata-public-epowt-1183", "applyInsurance": True},
                {"type": "tiket-trainfullkcic-bcai-public-epowt-1188", "applyInsurance": False}
            ]
            
        payload = {
            "cartId": cart_id,
            "secret": secret,
            "insurances": insurances,
            "voucherIds": []
        }
        
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/kereta-api/booking?cartId={cart_id}&secret={secret}")
        res = self.session.post(url, json=payload, headers=headers, timeout=20)
        if res.status_code != 200:
            raise Exception(f"Gagal membuat pesanan (order Whoosh): HTTP {res.status_code} - {res.text}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon order Whoosh tidak valid: {data}")
            
        if data.get("code") != "SUCCESS":
            err_msg = data.get("message") or data.get("errorMessage") or data
            raise Exception(f"Order Whoosh gagal: {err_msg}")
            
        res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        order_id = res_data.get("orderId") or res_data.get("id")
        order_hash = res_data.get("orderHash") or res_data.get("secret")
        payment_url = res_data.get("paymentUrl") or f"https://www.tiket.com/payment?order_id={order_id}&order_hash={order_hash}"
        
        return {
            "order_id": order_id,
            "order_hash": order_hash,
            "payment_url": payment_url,
            "raw": data
        }

    def initiate_payment_landing(self, order_id, order_hash):
        url = f"{self.BASE_URL}/tix-payment-core/payment/v4/landing"
        payload = {
            "cardNumber": "",
            "referenceId": int(order_id),
            "orderHash": order_hash,
            "paymentMethod": ""
        }
        res = self.session.post(url, json=payload, headers=self._get_request_headers(), timeout=15)
        return res.json()

    def select_payment_detail(self, order_id, order_hash, payment_key="VA_BCA"):
        url = f"{self.BASE_URL}/tix-payment-core/payment/detail/{payment_key}"
        payload = {
            "orderHash": order_hash,
            "referenceId": int(order_id),
            "paymentData": {
                "useDownPayment": False,
                "fullSettlement": False,
                "fdsToken": ""
            },
            "paymentKey": payment_key
        }
        res = self.session.put(url, json=payload, headers=self._get_request_headers(), timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal memilih metode pembayaran {payment_key}: HTTP {res.status_code}")
        return res.json()

    def confirm_payment(self, order_id, order_hash, payment_key="VA_BCA"):
        url = f"{self.BASE_URL}/tix-payment-core/payment/confirm/{payment_key}"
        payload = {
            "orderHash": order_hash,
            "referenceId": int(order_id)
        }
        res = self.session.post(url, json=payload, headers=self._get_request_headers(), timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal konfirmasi pembayaran {payment_key}: HTTP {res.status_code}")
        return res.json()
