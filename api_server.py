import json
import os
import uuid
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from tiket_api import TiketAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TiketPublicAPI")

CONFIG_PATH = "config.json"

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    elif os.path.exists("config.example.json"):
        with open("config.example.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

app = FastAPI(
    title="Tiket.com Flight & Promo Public API",
    description="REST API Publik & Tool Calling Interface untuk Pencarian, Pemantauan (War), dan Pemesanan Tiket Pesawat Otomatis di tiket.com. Dirancang agar mudah diintegrasikan dengan AI Muse / LLM.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global API client instance
cfg_cache = load_config()
api_client = TiketAPI(cfg_cache.get("auth", {}))

# State for Background War Worker
class WarState:
    def __init__(self):
        self.is_running = False
        self.stop_requested = False
        self.thread: Optional[threading.Thread] = None
        self.start_time: Optional[float] = None
        self.current_round = 0
        self.params: Dict[str, Any] = {}
        self.logs: List[str] = []
        self.matched_tickets: List[Dict[str, Any]] = []
        self.completed_orders: List[Dict[str, Any]] = []

    def log(self, msg: str):
        entry = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        self.logs.append(entry)
        if len(self.logs) > 100:
            self.logs.pop(0)
        logger.info(msg)

    def reset(self):
        self.is_running = False
        self.stop_requested = False
        self.thread = None
        self.start_time = None
        self.current_round = 0
        self.params = {}
        self.logs = []
        self.matched_tickets = []
        self.completed_orders = []

war_worker = WarState()

# Pydantic Request Models
class CookieUpdateRequest(BaseModel):
    cookie: str = Field(..., description="String Cookie lengkap dari browser tiket.com")
    user_agent: Optional[str] = Field(None, description="User Agent browser")

class FlightSearchRequest(BaseModel):
    origin: str = Field("JKTC", description="Kode kota / bandara asal (contoh: JKTC)")
    destination: str = Field("DPSC", description="Kode kota / bandara tujuan (contoh: DPSC)")
    departure_date: str = Field(..., description="Tanggal terbang format YYYY-MM-DD")
    adult: int = Field(2, ge=1, le=7, description="Jumlah penumpang dewasa")
    cabin_class: str = Field("ECONOMY", description="Kelas kabin (ECONOMY, BUSINESS, FIRST)")

class MultiDateSearchRequest(BaseModel):
    origin: str = Field("JKTC", description="Kode asal")
    destination: str = Field("DPSC", description="Kode tujuan")
    dates: List[str] = Field(..., description="Daftar tanggal format YYYY-MM-DD")
    adult: int = Field(2, ge=1, le=7, description="Jumlah penumpang")
    max_price: Optional[int] = Field(500000, description="Filter harga maksimal (0 = tanpa batas)")

class BookingRequest(BaseModel):
    flight_id: str = Field(..., description="Flight ID dari hasil pencarian penerbangan")
    supplier_id: str = Field(..., description="Supplier ID dari penerbangan yang dipilih")
    price: int = Field(..., description="Harga per tiket yang tertera di hasil pencarian")
    payment_method: str = Field("VA_BCA", description="Metode pembayaran (default: VA_BCA)")
    pax_count: Optional[int] = Field(None, description="Override jumlah penumpang (1 atau 2)")

class AutoBookRequest(BaseModel):
    origin: str = Field("JKTC", description="Kode kota asal")
    destination: str = Field("DPSC", description="Kode kota tujuan")
    departure_date: str = Field(..., description="Tanggal penerbangan (YYYY-MM-DD)")
    max_price: int = Field(500000, description="Batas harga maksimal tiket")
    adult: int = Field(2, description="Jumlah penumpang")
    payment_method: str = Field("VA_BCA", description="Metode pembayaran (VA_BCA)")

class WarStartRequest(BaseModel):
    dates: Optional[List[str]] = Field(None, description="Daftar tanggal war (kosong = gunakan target_dates di config)")
    max_price: int = Field(500000, description="Harga maksimal tiket target")
    interval_seconds: float = Field(2.0, ge=1.0, description="Jeda waktu refresh antar putaran")
    pax: int = Field(2, description="Jumlah penumpang")
    schedule_time: Optional[str] = Field(None, description="Jadwal waktu mulai otomatis (format HH:MM, misal '11:59')")

# --- ENDPOINTS ---

@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def get_dashboard():
    cfg = load_config()
    search_cfg = cfg.get("search", {})
    cookie_sample = cfg.get("auth", {}).get("cookie", "")[:35] + "..." if cfg.get("auth", {}).get("cookie") else "Belum diisi"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Tiket.com Flight & Promo Public API</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0b0f19;
                --card-bg: #131b2e;
                --primary: #006fee;
                --accent: #00d26a;
                --text: #e2e8f0;
                --text-muted: #94a3b8;
                --border: #1e293b;
            }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background: var(--bg);
                color: var(--text);
                padding: 40px 20px;
                display: flex;
                flex-direction: column;
                align-items: center;
            }}
            .container {{ max-width: 900px; width: 100%; }}
            .header {{
                text-align: center;
                margin-bottom: 40px;
            }}
            .header h1 {{
                font-size: 2.4rem;
                background: linear-gradient(135deg, #38bdf8, #818cf8, #c084fc);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 12px;
            }}
            .header p {{ color: var(--text-muted); font-size: 1.1rem; }}
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; margin-bottom: 30px; }}
            .card {{
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 24px;
                box-shadow: 0 10px 25px rgba(0,0,0,0.3);
            }}
            .card h3 {{ color: #38bdf8; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }}
            .badge {{
                display: inline-block;
                background: rgba(0, 210, 106, 0.15);
                color: var(--accent);
                padding: 4px 12px;
                border-radius: 999px;
                font-size: 0.85rem;
                font-weight: 600;
            }}
            .links {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 15px; }}
            .btn {{
                background: var(--primary);
                color: white;
                text-decoration: none;
                padding: 10px 18px;
                border-radius: 10px;
                font-weight: 600;
                transition: transform 0.2s, background 0.2s;
                display: inline-block;
            }}
            .btn:hover {{ background: #0056b3; transform: translateY(-2px); }}
            .btn-outline {{
                background: transparent;
                border: 1px solid var(--primary);
                color: #38bdf8;
            }}
            .btn-outline:hover {{ background: rgba(56, 189, 248, 0.1); }}
            .code-box {{
                background: #060911;
                border: 1px solid var(--border);
                padding: 16px;
                border-radius: 12px;
                font-family: monospace;
                font-size: 0.9rem;
                color: #a5b4fc;
                overflow-x: auto;
                margin-top: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✈️ Tiket.com Public REST API</h1>
                <p>Gateway Otomatisasi & Tool Calling Interface untuk AI Muse / LLM</p>
            </div>

            <div class="grid">
                <div class="card">
                    <h3>⚡ Status Layanan <span class="badge">ONLINE</span></h3>
                    <p style="margin-top: 8px;"><strong>Rute Default:</strong> {search_cfg.get('origin', 'JKTC')} ➔ {search_cfg.get('destination', 'DPSC')}</p>
                    <p style="margin-top: 4px;"><strong>Target Max Price:</strong> Rp {search_cfg.get('max_price', 500000):,}</p>
                    <p style="margin-top: 4px;"><strong>Penumpang:</strong> {search_cfg.get('adult', 2)} Pax</p>
                    <p style="margin-top: 4px;"><strong>Metode Bayar:</strong> BCA Virtual Account (VA_BCA)</p>
                    <div class="links">
                        <a href="/api/status" class="btn btn-outline">Check Status API</a>
                        <a href="/api/promo/bali" class="btn btn-outline">Cek Jadwal Bali</a>
                    </div>
                </div>

                <div class="card">
                    <h3>🤖 Integrasi AI Muse</h3>
                    <p>API ini menyediakan Tool Definitions (Function Calling) standar OpenAI / Anthropic yang bisa langsung dibaca oleh AI Muse Anda.</p>
                    <div class="links">
                        <a href="/ai/tools" class="btn">Tool Schema (/ai/tools)</a>
                        <a href="/ai/prompt" class="btn btn-outline">System Prompt Guide</a>
                    </div>
                </div>
            </div>

            <div class="card" style="margin-bottom: 30px;">
                <h3>📚 Dokumentasi Interaktif OpenAPI / Swagger</h3>
                <p>Uji coba seluruh endpoint (Search, Detail, Add-To-Cart, Booking, hingga Background War) secara langsung melalui browser:</p>
                <div class="links" style="margin-top: 12px;">
                    <a href="/docs" class="btn">Buka Swagger UI (/docs)</a>
                    <a href="/redoc" class="btn btn-outline">Buka ReDoc (/redoc)</a>
                    <a href="/openapi.json" class="btn btn-outline">OpenAPI Spec (JSON)</a>
                </div>
            </div>

            <div class="card">
                <h3>💡 Contoh Call untuk AI Muse (cURL)</h3>
                <div class="code-box">
# Cek harga tiket Jakarta ke Bali 2 pax tanggal 6 Nov 2026:<br>
curl "http://localhost:8000/api/flights/search?origin=JKTC&destination=DPSC&date=2026-11-06&adult=2"<br><br>
# Auto-booking tiket termurah di bawah Rp 500.000:<br>
curl -X POST "http://localhost:8000/api/flights/auto-book-cheapest" \\<br>
&nbsp;&nbsp;-H "Content-Type: application/json" \\<br>
&nbsp;&nbsp;-d '{{"origin":"JKTC","destination":"DPSC","departure_date":"2026-11-06","max_price":500000,"adult":2}}'
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.get("/api/status", tags=["System"])
def check_status():
    """Memeriksa status koneksi, validitas sesi tiket.com, dan konfigurasi saat ini."""
    cfg = load_config()
    auth = cfg.get("auth", {})
    search = cfg.get("search", {})
    passengers = cfg.get("passengers", {})
    
    session_res = None
    is_active = False
    try:
        session_res = api_client.validate_session()
        is_active = session_res is not None and session_res.get("code") == "SUCCESS"
    except Exception as e:
        is_active = False

    return {
        "status": "online",
        "session_active": is_active,
        "account_id": auth.get("account_id"),
        "session_data": session_res.get("data") if session_res else None,
        "config": {
            "origin": search.get("origin"),
            "destination": search.get("destination"),
            "max_price": search.get("max_price"),
            "adult": search.get("adult"),
            "passengers": [p.get("fullName") for p in passengers.get("adults", [])],
            "payment_method": cfg.get("payment", {}).get("method", "VA_BCA"),
            "target_dates": search.get("target_dates", [])
        },
        "war_worker": {
            "is_running": war_worker.is_running,
            "current_round": war_worker.current_round,
            "completed_orders": len(war_worker.completed_orders)
        }
    }

@app.post("/api/auth/update-cookie", tags=["System"])
def update_cookie(req: CookieUpdateRequest):
    """Memperbarui cookie sesi tiket.com secara dinamis tanpa perlu restart server."""
    cfg = load_config()
    cfg["auth"]["cookie"] = req.cookie.strip()
    if req.user_agent:
        cfg["auth"]["user_agent"] = req.user_agent.strip()
    save_config(cfg)

    # Re-initialize client
    global api_client
    api_client = TiketAPI(cfg.get("auth", {}))
    
    validation = api_client.validate_session()
    is_valid = validation is not None and validation.get("code") == "SUCCESS"

    return {
        "success": True,
        "message": "Cookie berhasil diperbarui",
        "session_valid": is_valid,
        "session_data": validation.get("data") if validation else None
    }

@app.get("/api/flights/search", tags=["Flights"])
def search_flights(
    origin: str = Query("JKTC", description="Kode kota/bandara asal"),
    destination: str = Query("DPSC", description="Kode kota/bandara tujuan"),
    date: str = Query(..., description="Tanggal keberangkatan YYYY-MM-DD"),
    adult: int = Query(2, ge=1, le=7, description="Jumlah penumpang dewasa"),
    cabin_class: str = Query("ECONOMY", description="Kelas kabin")
):
    """Mencari jadwal dan harga penerbangan pada satu tanggal tertentu."""
    try:
        flights = api_client.search_flights(
            origin=origin,
            destination=destination,
            departure_date=date,
            adult=adult,
            cabin_class=cabin_class
        )
        flights.sort(key=lambda x: x["price"])
        return {
            "origin": origin,
            "destination": destination,
            "departure_date": date,
            "adult": adult,
            "total_flights": len(flights),
            "cheapest_price": flights[0]["price"] if flights else None,
            "flights": flights
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/flights/search-multi", tags=["Flights"])
def search_multi_dates(req: MultiDateSearchRequest):
    """Mencari dan membandingkan harga termurah di banyak tanggal sekaligus."""
    results = []
    for d_str in req.dates:
        time.sleep(0.4)
        try:
            flights = api_client.search_flights(
                origin=req.origin,
                destination=req.destination,
                departure_date=d_str,
                adult=req.adult
            )
            if flights:
                flights.sort(key=lambda x: x["price"])
                cheapest = flights[0]
                is_qualifying = req.max_price == 0 or cheapest["price"] <= req.max_price
                results.append({
                    "date": d_str,
                    "cheapest_airline": cheapest["airline_name"],
                    "depart_time": cheapest["depart_time"],
                    "arrival_time": cheapest["arrival_time"],
                    "price": cheapest["price"],
                    "is_under_max_price": is_qualifying,
                    "flight_id": cheapest["flight_id"],
                    "supplier_id": cheapest["supplier_id"],
                    "total_available": len(flights)
                })
            else:
                results.append({
                    "date": d_str,
                    "error": "Tidak ada penerbangan",
                    "price": None
                })
        except Exception as e:
            results.append({
                "date": d_str,
                "error": str(e),
                "price": None
            })

    qualifying = [r for r in results if r.get("is_under_max_price")]
    return {
        "origin": req.origin,
        "destination": req.destination,
        "adult": req.adult,
        "max_price": req.max_price,
        "dates_checked": len(req.dates),
        "qualifying_count": len(qualifying),
        "summary": results
    }

@app.get("/api/promo/bali", tags=["Flights"])
def quick_check_bali():
    """Shortcut: Cek cepat ketersediaan tiket promo Jakarta -> Bali di semua weekend target yang terdaftar."""
    cfg = load_config()
    search = cfg.get("search", {})
    dates = search.get("target_dates", [])
    max_price = search.get("max_price", 500000)
    adult = search.get("adult", 2)
    
    return search_multi_dates(MultiDateSearchRequest(
        origin="JKTC",
        destination="DPSC",
        dates=dates,
        adult=adult,
        max_price=max_price
    ))

@app.post("/api/flights/book", tags=["Booking"])
def book_flight(req: BookingRequest):
    """
    Membuat pemesanan instan tiket penerbangan dan memilih metode pembayaran (default: VA_BCA).
    Menghasilkan Order ID resmi, Payment URL, dan Nomor Virtual Account BCA.
    """
    cfg = load_config()
    contact = cfg.get("contact", {})
    passengers = cfg.get("passengers", {})
    
    adults = passengers.get("adults", [])
    if req.pax_count is not None:
        adults = adults[:req.pax_count]

    start_t = time.time()
    try:
        # Step 1: Detail
        api_client.get_flight_detail(req.flight_id, req.supplier_id)
        
        # Step 2: Add to Cart
        cart_id = api_client.add_to_cart(req.flight_id, req.supplier_id, req.price)
        
        # Step 3: Validate Itinerary
        cart_detail = api_client.get_cart(cart_id)
        api_client.validate_itinerary(cart_id)
        
        # Step 4: Booking
        formatted_adults = api_client.format_passengers_for_cart(adults, cart_detail)
        booking_res = api_client.create_booking(cart_id, contact, formatted_adults)
        
        order_id = booking_res["order_id"]
        order_hash = booking_res["order_hash"]
        payment_url = booking_res["payment_url"]
        
        # Step 5: Payment Confirm (VA_BCA)
        va_number = None
        try:
            api_client.initiate_payment_landing(order_id, order_hash)
            api_client.select_payment_detail(order_id, order_hash, req.payment_method)
            confirm_res = api_client.confirm_payment(order_id, order_hash, req.payment_method)
            conf_data = confirm_res.get("data") if isinstance(confirm_res, dict) else {}
            va_number = conf_data.get("customAccount")
        except Exception as pe:
            logger.warning(f"Payment selection warning: {pe}")

        elapsed = time.time() - start_t
        return {
            "success": True,
            "order_id": order_id,
            "order_hash": order_hash,
            "payment_url": payment_url,
            "payment_method": req.payment_method,
            "va_number": va_number,
            "passengers": [p.get("fullName") for p in adults],
            "price_per_pax": req.price,
            "execution_time_seconds": round(elapsed, 2)
        }
    except Exception as e:
        logger.error(f"Booking error: {e}")
        raise HTTPException(status_code=500, detail=f"Gagal melakukan booking: {str(e)}")

@app.post("/api/flights/auto-book-cheapest", tags=["Booking"])
def auto_book_cheapest(req: AutoBookRequest):
    """
    Satu Panggilan: Cari penerbangan termurah di tanggal tertentu, jika <= max_price langsung booking otomatis sampai pembayaran!
    """
    flights = api_client.search_flights(
        origin=req.origin,
        destination=req.destination,
        departure_date=req.departure_date,
        adult=req.adult
    )
    if not flights:
        raise HTTPException(status_code=404, detail="Tidak ada penerbangan ditemukan pada tanggal tersebut.")

    flights.sort(key=lambda x: x["price"])
    cheapest = flights[0]

    if req.max_price > 0 and cheapest["price"] > req.max_price:
        return {
            "success": False,
            "message": f"Tiket termurah ({cheapest['airline_name']} - Rp {cheapest['price']:,}) masih di atas batas harga maksimum (Rp {req.max_price:,})",
            "cheapest_flight": cheapest
        }

    # Execute booking
    book_req = BookingRequest(
        flight_id=cheapest["flight_id"],
        supplier_id=cheapest["supplier_id"],
        price=cheapest["price"],
        payment_method=req.payment_method,
        pax_count=req.adult
    )
    return book_flight(book_req)

# --- BACKGROUND WAR WORKER ---

def _run_war_loop(dates: List[str], max_price: int, interval: float, pax: int, schedule_time: Optional[str]):
    war_worker.log(f"War Bot dimulai. Memantau {len(dates)} tanggal. Target <= Rp {max_price:,}")
    
    # Wait for schedule if specified
    if schedule_time:
        try:
            now = datetime.now()
            parts = list(map(int, schedule_time.split(":")))
            target_dt = now.replace(hour=parts[0], minute=parts[1], second=0, microsecond=0)
            if target_dt > now:
                war_worker.log(f"Menunggu hingga jadwal war: {schedule_time} WIB...")
                while datetime.now() < target_dt:
                    if war_worker.stop_requested:
                        war_worker.log("War dibatalkan oleh pengguna saat menunggu jadwal.")
                        war_worker.is_running = False
                        return
                    time.sleep(0.5)
                war_worker.log(f"Waktu {schedule_time} tiba! Memulai pemantauan intensif!")
        except Exception as e:
            war_worker.log(f"Format schedule error ({e}), langsung memulai war.")

    war_worker.current_round = 0
    booked_ids = set()

    cfg = load_config()
    contact = cfg.get("contact", {})
    adults = cfg.get("passengers", {}).get("adults", [])[:pax]

    while not war_worker.stop_requested:
        war_worker.current_round += 1
        round_num = war_worker.current_round
        war_worker.log(f"--- Putaran #{round_num} Memeriksa {len(dates)} Tanggal ---")

        for d_str in dates:
            if war_worker.stop_requested:
                break
            time.sleep(0.3)
            try:
                f_list = api_client.search_flights(
                    origin="JKTC",
                    destination="DPSC",
                    departure_date=d_str,
                    adult=pax
                )
                if not f_list:
                    continue

                f_list.sort(key=lambda x: x["price"])
                qualifying = [f for f in f_list if f["price"] <= max_price and f["flight_id"] not in booked_ids]

                if qualifying:
                    target = qualifying[0]
                    war_worker.log(f"🎉 TIKET TARGET DITEMUKAN pada {d_str}: {target['airline_name']} (Rp {target['price']:,})!")
                    war_worker.matched_tickets.append({"date": d_str, "flight": target})

                    # Immediate Auto-Booking
                    war_worker.log(f"⚡ Langsung mengeksekusi booking instan...")
                    try:
                        api_client.get_flight_detail(target["flight_id"], target["supplier_id"])
                        cart_id = api_client.add_to_cart(target["flight_id"], target["supplier_id"], target["price"])
                        cart_detail = api_client.get_cart(cart_id)
                        api_client.validate_itinerary(cart_id)
                        
                        formatted_adults = api_client.format_passengers_for_cart(adults, cart_detail)
                        booking_res = api_client.create_booking(cart_id, contact, formatted_adults)
                        
                        order_id = booking_res["order_id"]
                        order_hash = booking_res["order_hash"]
                        payment_url = booking_res["payment_url"]

                        va_number = None
                        try:
                            api_client.initiate_payment_landing(order_id, order_hash)
                            api_client.select_payment_detail(order_id, order_hash, "VA_BCA")
                            confirm_res = api_client.confirm_payment(order_id, order_hash, "VA_BCA")
                            va_number = (confirm_res.get("data") or {}).get("customAccount")
                        except Exception:
                            pass

                        booked_ids.add(target["flight_id"])
                        order_info = {
                            "order_id": order_id,
                            "order_hash": order_hash,
                            "payment_url": payment_url,
                            "va_number": va_number,
                            "date": d_str,
                            "airline": target["airline_name"],
                            "price": target["price"],
                            "round": round_num
                        }
                        war_worker.completed_orders.append(order_info)
                        war_worker.log(f"🏆 BOOKING SUKSES! Order ID: {order_id} | VA: {va_number} | Link: {payment_url}")
                        
                        # Once booked, stop war
                        war_worker.is_running = False
                        return
                    except Exception as be:
                        war_worker.log(f"❌ Gagal booking: {be}")
                else:
                    cheapest = f_list[0]
                    war_worker.log(f"Tanggal {d_str}: Termurah {cheapest['airline_name']} (Rp {cheapest['price']:,}) > Target")
            except Exception as se:
                war_worker.log(f"Error pencarian {d_str}: {se}")

        if war_worker.stop_requested:
            break

        war_worker.log(f"Belum ada tiket target. Menunggu {interval}s sebelum putaran berikutnya...")
        time.sleep(interval)

    war_worker.is_running = False
    war_worker.log("War Bot dihentikan.")

@app.post("/api/war/start", tags=["War Bot"])
def start_war(req: WarStartRequest, background_tasks: BackgroundTasks):
    """Memulai mode War pemantauan background otomatis hingga tiket promo didapat."""
    if war_worker.is_running:
        raise HTTPException(status_code=400, detail="War Bot sudah sedang berjalan!")

    cfg = load_config()
    dates = req.dates or cfg.get("search", {}).get("target_dates", [])
    if not dates:
        raise HTTPException(status_code=400, detail="Daftar tanggal war tidak boleh kosong.")

    war_worker.reset()
    war_worker.is_running = True
    war_worker.start_time = time.time()
    war_worker.params = req.dict()

    t = threading.Thread(
        target=_run_war_loop,
        args=(dates, req.max_price, req.interval_seconds, req.pax, req.schedule_time),
        daemon=True
    )
    war_worker.thread = t
    t.start()

    return {
        "success": True,
        "message": "War Bot berhasil dijalankan di background!",
        "params": req.dict(),
        "dates_monitored": len(dates)
    }

@app.get("/api/war/status", tags=["War Bot"])
def get_war_status():
    """Melihat status real-time, putaran, dan log dari War Bot yang sedang berjalan."""
    elapsed = round(time.time() - war_worker.start_time, 1) if war_worker.start_time else 0
    return {
        "is_running": war_worker.is_running,
        "elapsed_seconds": elapsed,
        "current_round": war_worker.current_round,
        "params": war_worker.params,
        "completed_orders": war_worker.completed_orders,
        "matched_tickets": war_worker.matched_tickets,
        "recent_logs": war_worker.logs[-15:]
    }

@app.post("/api/war/stop", tags=["War Bot"])
def stop_war():
    """Menghentikan War Bot yang sedang berjalan."""
    if not war_worker.is_running:
        return {"success": True, "message": "War Bot memang sedang tidak berjalan."}
    
    war_worker.stop_requested = True
    return {"success": True, "message": "Permintaan penghentian War Bot telah dikirim."}

# --- AI AGENT / MUSE TOOL MANIFEST ---

@app.get("/ai/tools", tags=["AI Integration"])
def get_ai_tools_spec():
    """
    Spesifikasi Tool Calling JSON Schema (OpenAI / Anthropic format)
    yang siap disalin atau di-fetch oleh AI Muse Anda.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "check_flight_status",
                "description": "Periksa status sesi login tiket.com dan parameter pencarian saat ini (asal, tujuan, penumpang, batas harga).",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_flights",
                "description": "Cari jadwal dan harga tiket pesawat pada tanggal tertentu untuk mengetahui opsi penerbangan termurah.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Kode kota asal penerbangan, contoh 'JKTC' (Jakarta)",
                            "default": "JKTC"
                        },
                        "destination": {
                            "type": "string",
                            "description": "Kode kota tujuan penerbangan, contoh 'DPSC' (Denpasar Bali)",
                            "default": "DPSC"
                        },
                        "date": {
                            "type": "string",
                            "description": "Tanggal keberangkatan format YYYY-MM-DD, contoh '2026-11-06'"
                        },
                        "adult": {
                            "type": "integer",
                            "description": "Jumlah penumpang dewasa (1 atau 2)",
                            "default": 2
                        }
                    },
                    "required": ["date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "check_bali_promo_weekends",
                "description": "Cek ketersediaan tiket promo pesawat Jakarta -> Bali di semua tanggal weekend target (November & Desember) sekaligus.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "auto_book_cheapest_flight",
                "description": "Cari penerbangan termurah pada tanggal tertentu, jika harganya <= max_price, otomatis langsung lakukan booking dan dapatkan nomor pembayaran BCA Virtual Account.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "origin": {
                            "type": "string",
                            "description": "Kode asal, contoh 'JKTC'",
                            "default": "JKTC"
                        },
                        "destination": {
                            "type": "string",
                            "description": "Kode tujuan, contoh 'DPSC'",
                            "default": "DPSC"
                        },
                        "departure_date": {
                            "type": "string",
                            "description": "Tanggal terbang format YYYY-MM-DD"
                        },
                        "max_price": {
                            "type": "integer",
                            "description": "Batas harga maksimum per orang (contoh 500000 untuk promo)",
                            "default": 500000
                        },
                        "adult": {
                            "type": "integer",
                            "description": "Jumlah penumpang (1 atau 2)",
                            "default": 2
                        }
                    },
                    "required": ["departure_date"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "start_promo_war_monitor",
                "description": "Mulai mode War otomatis di background. Bot akan terus me-refresh pencarian setiap beberapa detik dan langsung mengamankan tiket saat promo muncul.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_price": {
                            "type": "integer",
                            "description": "Batas harga tiket target promo (default 500000)",
                            "default": 500000
                        },
                        "schedule_time": {
                            "type": "string",
                            "description": "Jadwal jam mulai war otomatis (format HH:MM, misal '11:59' atau '16:59')"
                        },
                        "interval_seconds": {
                            "type": "number",
                            "description": "Jeda waktu refresh antar putaran dalam detik (default 2.0)",
                            "default": 2.0
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_war_status",
                "description": "Periksa perkembangan War Bot (putaran ke berapa, apakah tiket sudah berhasil didapat, Order ID, nomor VA).",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "stop_promo_war_monitor",
                "description": "Hentikan mode War Bot yang sedang berjalan di background.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    ]
    return {
        "framework": "OpenAI / Anthropic Function Calling Schema",
        "base_url": "http://localhost:8000",
        "tools": tools
    }

@app.get("/ai/prompt", tags=["AI Integration"])
def get_ai_prompt():
    """Petunjuk System Prompt yang bisa disalin ke AI Muse."""
    prompt = """
Kamu adalah AI Muse Travel Assistant yang terhubung ke Tiket.com Public API.
Kamu memiliki kemampuan langsung untuk mengecek harga tiket pesawat, memantau promo gledek, dan melakukan pemesanan (booking) otomatis.

BASE_URL API: http://localhost:8000

Instruksi Kerjamu:
1. Ketika pengguna bertanya jadwal / harga tiket, gunakan endpoint:
   GET /api/flights/search?origin=JKTC&destination=DPSC&date=YYYY-MM-DD&adult=2
   atau GET /api/promo/bali untuk cek semua tanggal liburan weekend sekaligus.

2. Ketika pengguna meminta untuk memesan atau mem-booking tiket pesawat:
   Gunakan endpoint:
   POST /api/flights/auto-book-cheapest
   dengan JSON body:
   {"origin":"JKTC","destination":"DPSC","departure_date":"YYYY-MM-DD","max_price":500000,"adult":2}
   Sampaikan nomor Order ID, batas waktu, dan Nomor Virtual Account BCA kepada pengguna.

3. Ketika pengguna ingin kamu siap-siap war promo (misal jam gledek):
   Gunakan endpoint:
   POST /api/war/start
   dengan JSON body:
   {"max_price": 500000, "interval_seconds": 2.0, "pax": 2, "schedule_time": "11:59"}
   Lalu kamu bisa memantau statusnya menggunakan GET /api/war/status.
"""
    return {"system_prompt": prompt.strip()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
