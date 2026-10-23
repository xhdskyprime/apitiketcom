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

logger = logging.getLogger("TiketAPI")

class TiketAPI:
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
            "Content-Type": "text/plain;charset=UTF-8",
            "Origin": "https://www.tiket.com",
            "Referer": "https://www.tiket.com/id-id/flights",
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

    def validate_session(self):
        url = f"{self.BASE_URL}/tix-member-session/v1/session/validate"
        res = self.session.get(url, headers=self._get_request_headers(), timeout=15)
        if res.status_code == 200:
            return res.json()
        return None

    def search_flights(self, origin, destination, departure_date, adult=1, child=0, infant=0, cabin_class="ECONOMY"):
        search_url = f"{self.BASE_URL}/tix-flight-search/v4/search"
        params = {
            "origin": origin,
            "originType": "CITY",
            "destination": destination,
            "destinationType": "CITY",
            "adult": adult,
            "child": child,
            "infant": infant,
            "cabinClass": cabin_class,
            "departureDate": departure_date,
            "resultType": "DEPARTURE",
            "searchType": "ONE_WAY",
            "enableVI": "true",
            "dcVar": "true",
            "ffVar": "control"
        }
        
        referer = f"https://www.tiket.com/id-id/flights/search?d={origin}&a={destination}&date={departure_date}&adult={adult}&child={child}&infant={infant}&class={cabin_class.lower()}&dType=CITY&aType=CITY&dLabel=Jakarta&aLabel=Surabaya&type=depart&flexiFare=true"
        headers = self._get_request_headers(referer=referer)
        headers["searchtrackerid"] = str(uuid.uuid4())
        headers["x-user-search-id"] = str(uuid.uuid4())
        
        logger.info(f"Mengirim permintaan pencarian penerbangan {origin} -> {destination} ({departure_date})...")
        res = self.session.get(search_url, params=params, headers=headers, timeout=15)
        
        # Retry on HTTP 429 Too Many Requests
        if res.status_code == 429:
            import time
            time.sleep(1.2)
            res = self.session.get(search_url, params=params, headers=headers, timeout=15)
            
        if res.status_code == 403:
            raise Exception("HTTP 403 Forbidden: Akses ditolak oleh sistem keamanan Cloudflare. Masukkan 'cookie' sesi aktif di config.json.")
        if res.status_code == 401:
            raise Exception("HTTP 401 Unauthorized: Sesi atau cookie pengguna belum terisi / expired. Silakan perbarui 'cookie' di config.json.")
        if res.status_code != 200:
            raise Exception(f"Gagal mencari penerbangan: HTTP {res.status_code}")
            
        initial_data = res.json()
        if isinstance(initial_data, str):
            initial_data = json.loads(initial_data)
            
        res_data = initial_data.get("data") if isinstance(initial_data, dict) and isinstance(initial_data.get("data"), dict) else {}
        request_items = res_data.get("requestItems") or []
        
        if not request_items:
            search_list = res_data.get("searchList") or {}
            if search_list:
                return self._parse_search_list(search_list)

        streaming_url = f"{self.BASE_URL}/tix-flight-search/v4/search/streaming"
        payload = {
            "requestItems": request_items,
            "streamType": "OW",
            "searchTrackerId": headers["searchtrackerid"],
            "userSearchId": headers["x-user-search-id"],
            "ffVar": "control",
            "enableVI": "true",
            "dcVar": True
        }
        
        res_stream = self.session.post(streaming_url, json=payload, headers=headers, timeout=20)
        if res_stream.status_code != 200:
            raise Exception(f"Gagal streaming pencarian penerbangan: HTTP {res_stream.status_code}")
            
        stream_data = res_stream.json()
        if isinstance(stream_data, str):
            stream_data = json.loads(stream_data)
            
        stream_res_data = stream_data.get("data") if isinstance(stream_data, dict) and isinstance(stream_data.get("data"), dict) else {}
        search_list = stream_res_data.get("searchList") or {}
        return self._parse_search_list(search_list)

    def _parse_search_list(self, search_list):
        flights = []
        
        items_to_process = []
        if isinstance(search_list, dict):
            items_to_process = search_list.get("departureFlights") or []
        elif isinstance(search_list, list):
            for sec in search_list:
                if isinstance(sec, dict):
                    items_to_process.extend(sec.get("items") or [])
                    
        for item in items_to_process:
            if not isinstance(item, dict):
                continue
                
            flight_id = item.get("flightId")
            supplier_id = item.get("supplierId")
            card = item.get("card") or {}
            
            # Ekstrak maskapai, waktu, dan harga dari card
            departure = card.get("departure") or {}
            arrival = card.get("arrival") or {}
            depart_time = departure.get("time", "")
            arrival_time = arrival.get("time", "")
            duration = card.get("duration", "")
            
            flight_infos = card.get("flightInfos") or []
            airline_name = flight_infos[0].get("info", "Unknown Airline") if flight_infos and isinstance(flight_infos[0], dict) else "Unknown Airline"
            airline_code = airline_name.split()[0] if airline_name else "XX"
            flight_number = airline_name
            
            price_num = 0
            price_components = card.get("priceComponents") or []
            if price_components and isinstance(price_components[0], dict):
                text_obj = price_components[0].get("text") or {}
                val_str = text_obj.get("value", "") if isinstance(text_obj, dict) else ""
                nums = re.findall(r"\d+", val_str.replace(".", "").replace(",", ""))
                if nums:
                    price_num = int("".join(nums))
                    
            if flight_id and supplier_id:
                flights.append({
                    "flight_id": flight_id,
                    "supplier_id": supplier_id,
                    "airline_name": airline_name,
                    "airline_code": airline_code,
                    "flight_number": flight_number,
                    "depart_time": depart_time,
                    "arrival_time": arrival_time,
                    "duration": duration,
                    "price": price_num,
                    "full_refund": item.get("fullRefund", False)
                })
                
        return flights

    def get_flight_detail(self, flight_id, supplier_id):
        url = f"{self.BASE_URL}/tix-flight-search/v3/prp/flightDetail"
        payload = {
            "details": [
                {
                    "flightId": flight_id,
                    "supplierId": supplier_id,
                    "fullRefund": False,
                    "fullRefundReschedule": True
                }
            ],
            "promoApplied": False,
            "prpVar": "control",
            "enablePRPPercentage": True,
            "dcVar": "true",
            "departRT": False
        }
        res = self.session.post(url, json=payload, headers=self._get_request_headers(), timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal mengambil detail penerbangan: HTTP {res.status_code}")
        return res.json()

    def add_to_cart(self, flight_id, supplier_id, price):
        url = f"{self.BASE_URL}/tix-flight-cart/v5/cart"
        payload = {
            "cartDetails": [
                {
                    "flightId": flight_id,
                    "supplierRequest": {
                        "supplierId": supplier_id
                    },
                    "isFullRefund": False,
                    "fullRefundCredentialCode": "tiket-basic-internal",
                    "fareBasisCode": ""
                }
            ],
            "currency": "IDR",
            "scale": 0,
            "departurePrice": price,
            "dcVar": True
        }
        res = self.session.post(url, json=payload, headers=self._get_request_headers(), timeout=15)
        if res.status_code != 200:
            raise Exception(f"Gagal menambah penerbangan ke keranjang: HTTP {res.status_code} - {res.text}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon add to cart tidak valid: {data}")
            
        if data.get("code") != "SUCCESS":
            raise Exception(f"Gagal add to cart: {data.get('message') or data}")
            
        res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        cart_id = res_data.get("cartId")
        if not cart_id:
            raise Exception(f"Gagal add to cart (Cart ID tidak ditemukan): {data}")
        return cart_id

    def format_passengers_for_cart(self, adults_config, cart_detail=None):
        """
        Dynamically formats passenger payload based on passengerFormSection requirements returned by get_cart,
        ensuring compatibility across all airlines (AirAsia, Citilink, Lion Air, Super Air Jet, Pelita Air, etc.).
        """
        expected_fields = set()
        if cart_detail and isinstance(cart_detail, dict):
            pax_section = (cart_detail.get("data") or {}).get("passengerFormSection") or {}
            for sec in pax_section.get("adultFormSections") or []:
                for form in sec.get("forms") or []:
                    name = form.get("name")
                    if name:
                        expected_fields.add(name)

        formatted = []
        for adult in adults_config:
            p = dict(adult)
            # Ensure alias mappings (e.g. dob <-> birthDate)
            if "birthDate" in p and "dob" not in p:
                p["dob"] = p["birthDate"]
            if "dob" in p and "birthDate" not in p:
                p["birthDate"] = p["dob"]
                
            # Ensure title is properly formatted (e.g. "Mr", "Mrs", "Ms")
            if p.get("title"):
                p["title"] = p["title"].capitalize()
                
            formatted.append(p)
        return formatted

    def get_cart(self, cart_id):
        url = f"{self.BASE_URL}/tix-flight-cart/v5/cart/{cart_id}"
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/cart/flight/{cart_id}")
        res = self.session.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.warning(f"Get cart HTTP status: {res.status_code}")
            return None
        return res.json()

    def validate_itinerary(self, cart_id):
        url = f"{self.BASE_URL}/tix-flight-cart/v5/cart/validate-itinerary"
        payload = {
            "cartId": cart_id,
            "prpInsurances": [],
            "dcVar": True
        }
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/cart/flight/{cart_id}")
        res = self.session.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code != 200:
            logger.warning(f"Validate itinerary HTTP status: {res.status_code}")
        return res.json()

    def create_booking(self, cart_id, contact, adults, childs=None, infants=None):
        url = f"{self.BASE_URL}/tix-flight-core/v7/booking"
        payload = {
            "cartId": cart_id,
            "contact": contact,
            "adults": adults,
            "childs": childs or [],
            "infants": infants or [],
            "multiInsurances": [],
            "claimVouchers": [],
            "scale": 0,
            "promoData": None
        }
        headers = self._get_request_headers(referer=f"https://www.tiket.com/id-id/cart/flight/{cart_id}")
        res = None
        for attempt_num in range(2):
            try:
                res = self.session.post(url, json=payload, headers=headers, timeout=45)
                break
            except Exception as e:
                if attempt_num == 0 and "timed out" in str(e).lower():
                    logger.warning(f"Booking attempt 1 timed out, retrying... ({e})")
                    continue
                raise e
        if res.status_code != 200:
            raise Exception(f"Gagal membuat pesanan (booking): HTTP {res.status_code} - {res.text}")
            
        data = res.json()
        if isinstance(data, str):
            data = json.loads(data)
            
        if not isinstance(data, dict):
            raise Exception(f"Respon booking tidak valid: {data}")
            
        if data.get("code") != "SUCCESS":
            err_msg = data.get("message") or data.get("errorMessage") or data
            raise Exception(f"Booking gagal: {err_msg}")
            
        res_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        success_data = res_data.get("successData") if isinstance(res_data.get("successData"), dict) else {}
        order_id = success_data.get("orderId")
        order_hash = success_data.get("orderHash")
        payment_url = success_data.get("paymentUrl")
        
        if not order_id:
            logger.error(f"Raw booking response: {json.dumps(data)}")
            err_msg = res_data.get("errorMessage") or res_data.get("errorCode") or data.get("errors") or data.get("errorMessage") or json.dumps(data)
            raise Exception(f"Booking gagal (Order ID tidak ditemukan): {err_msg}")
        
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
