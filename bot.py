import json
import argparse
import sys
import os
import logging
import time
from datetime import datetime, timedelta

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from colorama import init, Fore, Style
from tabulate import tabulate
from tiket_api import TiketAPI

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TiketBot")

def load_config(config_path):
    if not os.path.exists(config_path):
        print(Fore.RED + f"❌ File konfigurasi '{config_path}' tidak ditemukan!")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def format_price(amount):
    return f"Rp {amount:,.0f}".replace(",", ".")

def get_upcoming_fridays(start_date_str, count=5):
    try:
        start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    except Exception:
        start_dt = datetime.now()
        
    days_until_friday = (4 - start_dt.weekday()) % 7
    first_friday = start_dt + timedelta(days=days_until_friday)
    
    fridays = []
    for i in range(count):
        f_date = first_friday + timedelta(days=7 * i)
        fridays.append(f_date.strftime("%Y-%m-%d"))
    return fridays

def wait_until_schedule(target_time_str):
    if not target_time_str:
        return
    now = datetime.now()
    try:
        parts = list(map(int, target_time_str.split(':')))
        hour = parts[0]
        minute = parts[1]
        second = parts[2] if len(parts) > 2 else 0
        target_dt = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    except Exception as e:
        print(Fore.RED + f"❌ Format waktu schedule '{target_time_str}' tidak valid. Gunakan format HH:MM (contoh: 11:00)")
        return

    if target_dt <= now:
        print(Fore.YELLOW + f"⏰ Waktu {target_time_str} sudah lewat atau sekarang. Langsung memulai bot...")
        return

    print(Fore.CYAN + Style.BRIGHT + f"\n⏱️ BOT MENUNGGU WAKTU WAR: {target_time_str} (Waktu Sekarang: {now.strftime('%H:%M:%S')})")
    while True:
        current = datetime.now()
        rem = (target_dt - current).total_seconds()
        if rem <= 0:
            print(Fore.GREEN + Style.BRIGHT + f"\n🔥 WAKTU WAR {target_time_str} TELAH TIBA! MEMULAI WAR PENCARIAN TIKET SEKARANG!\n")
            break
        mins, secs = divmod(int(rem), 60)
        hrs, mins = divmod(mins, 60)
        sys.stdout.write(f"\r⏳ Hitung Mundur: {hrs:02d}:{mins:02d}:{secs:02d} tersisa | Menunggu jam {target_time_str}... ")
        sys.stdout.flush()
        time.sleep(0.5)

def display_flights_table(flights):
    headers = ["No", "Maskapai", "Kode", "No. Penerbangan", "Berangkat", "Tiba", "Harga (IDR)"]
    table_data = []
    for idx, f in enumerate(flights, start=1):
        table_data.append([
            idx,
            f["airline_name"],
            f["airline_code"],
            f["flight_number"],
            f["depart_time"],
            f["arrival_time"],
            format_price(f["price"])
        ])
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))

def main():
    parser = argparse.ArgumentParser(description="Tiket.com Auto-Order Flight Ticket CLI Bot")
    parser.add_argument("--config", default="config.json", help="Path ke file config.json")
    parser.add_argument("--search-only", action="store_true", help="Hanya melakukan pencarian dan menampilkan daftar penerbangan")
    parser.add_argument("--auto", action="store_true", help="Otomatis memilih penerbangan termurah sesuai kriteria & langsung booking")
    parser.add_argument("--dry-run", action="store_true", help="Menjalankan simulasi sampai Add-to-Cart tanpa membuat booking sungguhan")
    parser.add_argument("--pax", "--passengers", "-p", type=int, choices=[1, 2], help="Jumlah penumpang dewasa (1 = Muhamad Lutfi, 2 = Muhamad Lutfi & Firdha Amalia)")
    parser.add_argument("--fridays", type=int, nargs="?", const=5, help="Mencari penerbangan termurah di N hari Jumat berturut-turut (default: 5 hari Jumat)")
    parser.add_argument("--dates", nargs="+", help="Daftar tanggal spesifik untuk dipantau (format: YYYY-MM-DD YYYY-MM-DD ...)")
    parser.add_argument("--all-dates", "--war-dates", action="store_true", help="Pantau semua tanggal target yang ada di config.json")
    parser.add_argument("--schedule", "--wait-until", help="Jadwalkan bot untuk menunggu sampai jam tertentu (format: HH:MM, misal 11:00) sebelum memulai war")
    parser.add_argument("--max-price", type=int, help="Override target harga maksimum (isi 0 untuk harga bebas / tanpa batas harga)")
    parser.add_argument("--max-bookings", "--orders", "-n", type=int, default=1, help="Jumlah target orderan yang ingin dibuat (default: 1, set ke 2 untuk 2x orderan)")
    parser.add_argument("--start-date", help="Tanggal awal pencarian (format: YYYY-MM-DD, default dari config.json)")
    parser.add_argument("--watch", "-w", action="store_true", help="Mode War: Refresh terus-menerus sampai tiket harga target ditemukan")
    parser.add_argument("--interval", "-i", type=float, default=3.0, help="Jeda waktu refresh dalam detik untuk Mode War (default: 3.0 detik)")
    
    args = parser.parse_args()
    
    print(Fore.CYAN + Style.BRIGHT + "="*65)
    print(Fore.CYAN + Style.BRIGHT + "   🤖 TIKET.COM AUTO-ORDER FLIGHT TICKET CLI BOT ✈️   ")
    print(Fore.CYAN + Style.BRIGHT + "="*65)
    
    config = load_config(args.config)
    auth_cfg = config.get("auth", {})
    search_cfg = config.get("search", {})
    contact_cfg = config.get("contact", {})
    passengers_cfg = config.get("passengers", {})
    payment_cfg = config.get("payment", {})
    
    # Override jumlah penumpang jika opsi --pax diisi
    if args.pax is not None:
        search_cfg["adult"] = args.pax
        if "adults" in passengers_cfg:
            passengers_cfg["adults"] = passengers_cfg["adults"][:args.pax]
            
    api = TiketAPI(auth_cfg)
    
    origin = search_cfg.get("origin", "JKTC")
    destination = search_cfg.get("destination", "DPSC")
    dep_date = args.start_date or search_cfg.get("departureDate", "2026-08-28")
    adults_count = search_cfg.get("adult", 1)
    childs_count = search_cfg.get("child", 0)
    infants_count = search_cfg.get("infant", 0)
    cabin_class = search_cfg.get("cabinClass", "ECONOMY")
    max_price = args.max_price if args.max_price is not None else search_cfg.get("max_price", 0)
    pref_airline = search_cfg.get("preferred_airline_code", "").upper()
    
    adult_names = [p.get("fullName") for p in passengers_cfg.get("adults", [])]

    # Cek penjadwalan waktu (misal jam 11:00)
    if args.schedule:
        wait_until_schedule(args.schedule)

    start_time = time.time()

    # Tentukan daftar tanggal yang akan dicari
    dates_to_search = None
    if args.dates:
        dates_to_search = args.dates
    elif args.all_dates:
        dates_to_search = search_cfg.get("target_dates") or [dep_date]
    elif args.fridays is not None:
        dates_to_search = get_upcoming_fridays(dep_date, args.fridays)
    elif "target_dates" in search_cfg and not args.start_date and (args.watch or args.auto):
        dates_to_search = search_cfg.get("target_dates")
    
    target_booking_count = args.max_bookings
    completed_orders = []
    booked_flight_ids = set()

    while len(completed_orders) < target_booking_count:
        order_num = len(completed_orders) + 1
        if target_booking_count > 1:
            print(Fore.CYAN + Style.BRIGHT + f"\n==================================================")
            print(Fore.CYAN + Style.BRIGHT + f"🎯 BERBURU PESANAN KE-{order_num} DARI TOTAL {target_booking_count} ORDERAN")
            print(Fore.CYAN + Style.BRIGHT + f"==================================================")

        selected_flight = None
        dep_date_selected = None

        # Handle Mode Multi-Date Search
        if dates_to_search:
            print(Fore.CYAN + Style.BRIGHT + f"\n🗓️ MEMANTAU TIKET TERMURAH DI {len(dates_to_search)} TANGGAL TARGET")
            print(Fore.CYAN + f"📍 Rute: {origin} -> {destination} | Penumpang ({adults_count}): {', '.join(adult_names)}")
            if max_price > 0:
                print(Fore.CYAN + f"🎯 Target Harga Maksimum: {format_price(max_price)}")
            print(Fore.CYAN + "="*65)
            
            attempt = 1
            interval = max(0.5, args.interval)
            results_by_date = []

            try:
                while True:
                    results_by_date = []
                    target_matched = []
                    print(Fore.YELLOW + f"\n[Putaran #{attempt}] 🔍 Memeriksa {len(dates_to_search)} Tanggal Target...")
                    
                    for idx, date_str in enumerate(dates_to_search, start=1):
                        try:
                            f_list = api.search_flights(
                                origin=origin,
                                destination=destination,
                                departure_date=date_str,
                                adult=adults_count,
                                child=childs_count,
                                infant=infants_count,
                                cabin_class=cabin_class
                            )
                            if pref_airline:
                                f_list = [f for f in f_list if pref_airline in f["airline_code"].upper()]
                                
                            if f_list:
                                f_list.sort(key=lambda x: x["price"])
                                cheapest_overall = f_list[0]
                                
                                # Filter sesuai harga max dan hindari flight_id yang sudah dibooking
                                qualifying = [f for f in f_list if (max_price == 0 or f["price"] <= max_price) and f["flight_id"] not in booked_flight_ids]
                                
                                is_target = len(qualifying) > 0
                                results_by_date.append({
                                    "date": date_str,
                                    "flight": cheapest_overall,
                                    "target_flight": qualifying[0] if is_target else None,
                                    "is_target": is_target,
                                    "total_flights": len(f_list)
                                })
                                
                                if is_target:
                                    target_matched.append({
                                        "date": date_str,
                                        "flight": qualifying[0]
                                    })
                                    print(Fore.GREEN + f"   [{idx}/{len(dates_to_search)}] Tanggal {date_str} -> 🎉 DITEMUKAN: {qualifying[0]['airline_name']} ({format_price(qualifying[0]['price'])})")
                                else:
                                    print(Fore.YELLOW + f"   [{idx}/{len(dates_to_search)}] Tanggal {date_str} -> ⚠️ Termurah: {cheapest_overall['airline_name']} ({format_price(cheapest_overall['price'])})")
                            else:
                                print(Fore.RED + f"   [{idx}/{len(dates_to_search)}] Tanggal {date_str} -> ❌ tidak ada penerbangan.")
                        except Exception as e:
                            print(Fore.RED + f"   [{idx}/{len(dates_to_search)}] Tanggal {date_str} -> ❌ Error: {e}")

                    if target_matched or args.search_only:
                        if target_matched and attempt > 1:
                            print(Fore.GREEN + Style.BRIGHT + f"\n🎉 TIKET TARGET DITEMUKAN PADA PUTARAN #{attempt}!")
                        break

                    if args.watch or args.auto:
                        print(Fore.YELLOW + f"⏳ Belum ada tiket <= {format_price(max_price)} di {len(dates_to_search)} Tanggal Target. Refreshing putaran berikutnya dalam {interval:.1f}s... (Ctrl+C untuk stop)")
                        time.sleep(interval)
                        attempt += 1
                    else:
                        break

            except KeyboardInterrupt:
                print(Fore.YELLOW + "\n\n👋 Pemantauan dihentikan oleh pengguna.")
                sys.exit(0)

            summary_table = []
            for idx, res in enumerate(results_by_date, start=1):
                fl = res["flight"]
                stat = f"✅ Target (<={format_price(max_price)})" if res["is_target"] else f"⚠️ > {format_price(max_price)}"
                summary_table.append([
                    idx,
                    res["date"],
                    fl["airline_name"],
                    fl["depart_time"],
                    fl["arrival_time"],
                    format_price(fl["price"]),
                    stat
                ])
                
            print(Fore.GREEN + Style.BRIGHT + f"\n📊 RINGKASAN HARGA TERMURAH DI {len(dates_to_search)} TANGGAL TARGET:")
            print(tabulate(summary_table, headers=["No", "Tanggal", "Maskapai Termurah", "Berangkat", "Tiba", "Harga/Pax", "Status"], tablefmt="fancy_grid"))

            if args.search_only:
                print(Fore.CYAN + "\nℹ️ Mode search-only selesai. Tidak ada transaksi yang diproses.")
                return

            if not target_matched:
                print(Fore.RED + f"\n❌ Tidak ditemukan penerbangan <= {format_price(max_price)} pada semua tanggal target.")
                print(Fore.CYAN + "💡 Jalankan bot dengan '--watch' atau '--auto' saat mendekati Jam 11:00 untuk terus memantau tiket promo!")
                sys.exit(1)

            if args.auto:
                best_target = min(target_matched, key=lambda x: x["flight"]["price"])
                selected_flight = best_target["flight"]
                dep_date_selected = best_target["date"]
                print(Fore.GREEN + Style.BRIGHT + f"\n⚡ Mode Auto: Memilih tanggal & penerbangan termurah -> {dep_date_selected} | {selected_flight['airline_name']} - {format_price(selected_flight['price'])}")
            else:
                print(Fore.YELLOW + f"\nSilakan pilih nomor Tanggal Target [1 - {len(target_matched)}] yang ingin dipesan (atau 'q' untuk keluar): ", end="")
                choice = input().strip()
                if choice.lower() == 'q':
                    print("Pemesanan dibatalkan.")
                    return
                try:
                    c_idx = int(choice) - 1
                    if 0 <= c_idx < len(target_matched):
                        selected_flight = target_matched[c_idx]["flight"]
                        dep_date_selected = target_matched[c_idx]["date"]
                    else:
                        print(Fore.RED + "Pilihan nomor tidak valid.")
                        return
                except ValueError:
                    print(Fore.RED + "Input tidak valid.")
                    return

        else:
            # Mode Pencarian Single Date dengan Loop Watch / Refresh Kontinu
            dep_date_selected = dep_date
            print(Fore.YELLOW + f"\n🔍 Memulai pencarian penerbangan: {origin} -> {destination} | Tanggal: {dep_date_selected} | Penumpang ({adults_count}): {', '.join(adult_names)}")
            if max_price > 0:
                print(Fore.CYAN + f"🎯 Target Harga Maksimum: {format_price(max_price)}")
            print(Fore.CYAN + "="*65)

            attempt = 1
            interval = max(0.5, args.interval)
            filtered_flights = []

            try:
                while True:
                    try:
                        flights = api.search_flights(
                            origin=origin,
                            destination=destination,
                            departure_date=dep_date_selected,
                            adult=adults_count,
                            child=childs_count,
                            infant=infants_count,
                            cabin_class=cabin_class
                        )
                    except Exception as e:
                        if args.watch or args.auto:
                            print(Fore.RED + f"\r[Percobaan #{attempt}] ❌ Error pencarian: {e}. Retry dalam {interval}s...", end="", flush=True)
                            time.sleep(interval)
                            attempt += 1
                            continue
                        else:
                            print(Fore.RED + f"❌ Error pencarian penerbangan: {e}")
                            sys.exit(1)

                    filtered_flights = [f for f in flights if f["flight_id"] not in booked_flight_ids]
                    if max_price > 0:
                        filtered_flights = [f for f in filtered_flights if f["price"] <= max_price]
                    if pref_airline:
                        filtered_flights = [f for f in filtered_flights if pref_airline in f["airline_code"].upper()]

                    if filtered_flights:
                        if attempt > 1:
                            print(Fore.GREEN + Style.BRIGHT + f"\n\n🎉 TIKET DITEMUKAN PADA PERCOBAAN #{attempt}!")
                        else:
                            print(Fore.GREEN + f"\n✅ Ditemukan {len(filtered_flights)} jadwal penerbangan yang memenuhi kriteria.\n")
                        display_flights_table(filtered_flights)
                        break

                    # Jika belum ditemukan tiket yang memenuhi kriteria filter
                    if args.watch or args.auto:
                        print(Fore.YELLOW + f"\r[Percobaan #{attempt}] ⏳ Belum ada tiket <= {format_price(max_price)}. Refreshing dalam {interval:.1f}s... (Ctrl+C untuk stop)", end="", flush=True)
                        time.sleep(interval)
                        attempt += 1
                    else:
                        print(Fore.RED + f"\n❌ Tidak ada penerbangan yang memenuhi filter (Harga Maks: {format_price(max_price)}, Airline: {pref_airline or 'Semua'}).")
                        print(Fore.CYAN + "💡 Petunjuk: Gunakan opsi '--watch' atau '--auto' untuk memantau & refresh otomatis sampai tiket harga target ditemukan.")
                        sys.exit(1)

            except KeyboardInterrupt:
                print(Fore.YELLOW + "\n\n👋 Mode War / Refresh dihentikan oleh pengguna.")
                sys.exit(0)

            if args.search_only:
                print(Fore.CYAN + "\nℹ️ Mode search-only selesai. Tidak ada transaksi yang diproses.")
                return

            filtered_flights.sort(key=lambda x: x["price"])
            
            if args.auto:
                selected_flight = filtered_flights[0]
                print(Fore.GREEN + Style.BRIGHT + f"\n⚡ Mode Auto: Memilih penerbangan termurah -> {selected_flight['airline_name']} ({selected_flight['flight_number']}) - {format_price(selected_flight['price'])}")
            else:
                print(Fore.YELLOW + f"\nSilakan pilih nomor penerbangan [1 - {len(filtered_flights)}] (atau 'q' untuk keluar): ", end="")
                choice = input().strip()
                if choice.lower() == 'q':
                    print("Pemesanan dibatalkan.")
                    return
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(filtered_flights):
                        selected_flight = filtered_flights[idx]
                    else:
                        print(Fore.RED + "Pilihan nomor tidak valid.")
                        return
                except ValueError:
                    print(Fore.RED + "Input tidak valid.")
                    return

        # Proses Pemesanan
        flight_id = selected_flight["flight_id"]
        supplier_id = selected_flight["supplier_id"]
        price = selected_flight["price"]
        booked_flight_ids.add(flight_id)
        
        print(Fore.CYAN + "\n==================================================")
        print(Fore.CYAN + f"🚀 MEMULAI PROSES AUTO-ORDER TIKET #{order_num} ({adults_count} PENUMPANG)")
        print(Fore.CYAN + "==================================================")
        
        # Step 1: Detail PRP
        print(Fore.YELLOW + "1️⃣ Ambil Detail Penerbangan...")
        try:
            api.get_flight_detail(flight_id, supplier_id)
            print(Fore.GREEN + "   ✔ Detail penerbangan terverifikasi.")
        except Exception as e:
            print(Fore.RED + f"   ✖ Gagal get flight detail: {e}")

        # Step 2: Add to Cart
        print(Fore.YELLOW + "2️⃣ Menambahkan Tiket ke Keranjang (Cart)...")
        try:
            cart_id = api.add_to_cart(flight_id, supplier_id, price)
            print(Fore.GREEN + f"   ✔ Tiket berhasil masuk keranjang! Cart ID: {cart_id}")
            api.get_cart(cart_id)
        except Exception as e:
            print(Fore.RED + f"   ✖ Gagal add to cart: {e}")
            sys.exit(1)

        if args.dry_run:
            completed_orders.append({
                "order_num": order_num,
                "order_id": f"DRY-RUN-{cart_id[:8]}",
                "order_hash": "DRY-RUN-HASH",
                "payment_url": "SIMULASI-ONLY",
                "airline": selected_flight['airline_name'],
                "dep_date": dep_date_selected,
                "price": price,
                "pay_method": "DRY-RUN"
            })
            print(Fore.MAGENTA + Style.BRIGHT + f"\n🧪 [DRY-RUN] Simulasi Order #{order_num} berhasil sampai Cart ID: {cart_id}")
            if len(completed_orders) < target_booking_count:
                print(Fore.CYAN + f"🔄 Melanjutkan ke simulasi orderan ke-{len(completed_orders)+1}/{target_booking_count}...")
                time.sleep(1.0)
                continue
            else:
                break

        # Step 3: Validate Itinerary
        print(Fore.YELLOW + "3️⃣ Validasi Jadwal & Harga Tiket...")
        cart_detail = None
        try:
            cart_detail = api.get_cart(cart_id)
            api.validate_itinerary(cart_id)
            print(Fore.GREEN + "   ✔ Validasi itinerary selesai.")
        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️ Peringatan itinerary validation: {e}")

        # Step 4: Booking Order
        print(Fore.YELLOW + f"4️⃣ Membuat Order Booking ({', '.join(adult_names)})...")
        adult_list = passengers_cfg.get("adults", [])
        child_list = passengers_cfg.get("childs", [])
        infant_list = passengers_cfg.get("infants", [])
        
        # Format penumpang secara otomatis sesuai kebutuhan form maskapai
        formatted_adults = api.format_passengers_for_cart(adult_list, cart_detail)
        
        try:
            booking_res = api.create_booking(cart_id, contact_cfg, formatted_adults, child_list, infant_list)
            order_id = booking_res["order_id"]
            order_hash = booking_res["order_hash"]
            payment_url = booking_res["payment_url"]
            print(Fore.GREEN + Style.BRIGHT + f"   ✔ ORDER SUCCESS! Order ID: {order_id} | Hash: {order_hash}")
        except Exception as e:
            print(Fore.RED + f"   ✖ Gagal membuat booking: {e}")
            sys.exit(1)

        # Step 5: Select Payment Method & Confirm
        pay_method = payment_cfg.get("method", "VA_BCA")
        print(Fore.YELLOW + f"5️⃣ Konfirmasi Metode Pembayaran ({pay_method})...")
        va_number = None
        try:
            api.initiate_payment_landing(order_id, order_hash)
            api.select_payment_detail(order_id, order_hash, pay_method)
            confirm_res = api.confirm_payment(order_id, order_hash, pay_method)
            conf_data = confirm_res.get("data") if isinstance(confirm_res, dict) else {}
            va_number = conf_data.get("customAccount")
            print(Fore.GREEN + f"   ✔ Metode pembayaran {pay_method} berhasil dikonfirmasi.")
            if va_number:
                print(Fore.GREEN + Style.BRIGHT + f"   🏦 Nomor Virtual Account BCA: {va_number}")
        except Exception as e:
            print(Fore.YELLOW + f"   ⚠️ Pembayaran otomatis belum selesai: {e}")

        completed_orders.append({
            "order_num": order_num,
            "order_id": order_id,
            "order_hash": order_hash,
            "payment_url": payment_url,
            "va_number": va_number,
            "airline": selected_flight['airline_name'],
            "dep_date": dep_date_selected,
            "price": price,
            "pay_method": pay_method
        })

        if len(completed_orders) < target_booking_count:
            print(Fore.GREEN + Style.BRIGHT + f"\n🎉 ORDERAN KE-{order_num} BERHASIL DIBUAT (Order ID: {order_id})!")
            print(Fore.CYAN + Style.BRIGHT + f"🔄 Melanjutkan perburuan untuk orderan ke-{len(completed_orders)+1}/{target_booking_count}...\n")
            time.sleep(1.0)

    # Ringkasan Akhir Pemesanan
    elapsed = time.time() - start_time
    print(Fore.GREEN + Style.BRIGHT + "\n" + "="*70)
    print(Fore.GREEN + Style.BRIGHT + f"🎉 TOTAL {len(completed_orders)} PESANAN TIKET PESAWAT BERHASIL DIBUAT! 🎉")
    print(Fore.GREEN + Style.BRIGHT + "="*70)
    
    summary_orders = []
    for o in completed_orders:
        summary_orders.append([
            f"Order #{o['order_num']}",
            o['order_id'],
            o['dep_date'],
            o['airline'],
            format_price(o['price']),
            o['pay_method']
        ])
    print(tabulate(summary_orders, headers=["No", "Order ID", "Tanggal", "Maskapai", "Total Harga", "Metode Bayar"], tablefmt="fancy_grid"))
    
    for o in completed_orders:
        print(f"\n📌 Order #{o['order_num']} ID: {Fore.YELLOW}{o['order_id']}{Style.RESET_ALL} | Hash: {o['order_hash']}")
        print(f"   🔗 Link Bayar: {Fore.CYAN}{o['payment_url']}")
        if o.get("va_number"):
            print(f"   🏦 Nomor VA BCA: {Fore.GREEN}{Style.BRIGHT}{o['va_number']}")

    print(Fore.CYAN + Style.BRIGHT + f"\n⏱️ TOTAL WAKTU EKSEKUSI BOT ({len(completed_orders)} ORDERAN): {elapsed:.2f} detik ({elapsed*1000:.0f} ms)")
    print(Fore.GREEN + Style.BRIGHT + "="*70 + "\n")

if __name__ == "__main__":
    main()
