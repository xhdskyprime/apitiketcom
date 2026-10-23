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
from whoosh_api import WhooshAPI

init(autoreset=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("WhooshBot")

# Stasiun Whoosh Mapping
STATIONS = {
    "IDHMA": "Halim (Jakarta)",
    "IDTLA": "Tegalluar Summarecon (Bandung)",
    "IDPDK": "Padalarang (Bandung)",
    "IDBDG": "Bandung City"
}

def get_station_name(code):
    return STATIONS.get(code, code)

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

def wait_until_target_time(target_time_str):
    try:
        now = datetime.now()
        parts = [int(p) for p in target_time_str.split(":")]
        if len(parts) == 2:
            target = now.replace(hour=parts[0], minute=parts[1], second=0, microsecond=0)
        elif len(parts) == 3:
            target = now.replace(hour=parts[0], minute=parts[1], second=parts[2], microsecond=0)
        else:
            print(Fore.RED + f"❌ Format --start-at tidak valid: '{target_time_str}'. Gunakan HH:MM atau HH:MM:SS.")
            sys.exit(1)

        if target < now:
            print(Fore.YELLOW + f"⚠️ Waktu target {target.strftime('%H:%M:%S')} sudah lewat. Memulai war langsung!")
            return

        print(Fore.CYAN + Style.BRIGHT + f"\n⏱️  MODE WAR SCHEDULED: Menunggu jam {target.strftime('%H:%M:%S')} WIB...")
        while True:
            now = datetime.now()
            diff = (target - now).total_seconds()
            if diff <= 0:
                print(Fore.GREEN + Style.BRIGHT + f"\n🔥 JAM {target.strftime('%H:%M:%S')} TELAH TIBA! MEMULAI WAR TIKET SEKARANG! 🚀\n")
                break
            
            hours, remainder = divmod(int(diff), 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            print(Fore.YELLOW + f"\r⏳ Menunggu jam {target.strftime('%H:%M:%S')} WIB... (Sisa waktu: {countdown_str})", end="", flush=True)
            
            sleep_dur = min(1.0, max(0.05, diff))
            time.sleep(sleep_dur)
    except Exception as e:
        print(Fore.RED + f"❌ Gagal memproses --start-at: {e}")
        sys.exit(1)

def display_trains_table(trains):
    headers = ["No", "Kereta", "Kelas", "No. Kereta", "Berangkat", "Tiba", "Kursi Sisa", "Harga (IDR)"]
    table_data = []
    for idx, t in enumerate(trains, start=1):
        table_data.append([
            idx,
            t["trainName"],
            t["wagonDetail"],
            t["trainNumber"],
            t["depart_time"],
            t["arrival_time"],
            t["available_seats"],
            format_price(t["price"])
        ])
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))

def main():
    parser = argparse.ArgumentParser(description="Tiket.com Auto-Order Kereta Cepat Whoosh CLI Bot")
    parser.add_argument("--config", default="config.json", help="Path ke file config.json")
    parser.add_argument("--origin", help="Kode stasiun asal (IDHMA = Halim, IDTLA = Tegalluar, IDPDK = Padalarang)")
    parser.add_argument("--dest", "--destination", help="Kode stasiun tujuan")
    parser.add_argument("--search-only", action="store_true", help="Hanya melakukan pencarian dan menampilkan daftar jadwal kereta Whoosh")
    parser.add_argument("--auto", action="store_true", help="Otomatis memilih jadwal kereta Whoosh termurah & langsung booking")
    parser.add_argument("--dry-run", action="store_true", help="Menjalankan simulasi sampai Add-to-Cart tanpa membuat booking sungguhan")
    parser.add_argument("--pax", "--passengers", "-p", type=int, choices=[1, 2], help="Jumlah penumpang dewasa (1 = Muhamad Lutfi, 2 = Muhamad Lutfi & Firdha Amalia)")
    parser.add_argument("--fridays", type=int, nargs="?", const=5, help="Mencari kereta Whoosh termurah di N hari Jumat berturut-turut (default: 5 hari Jumat)")
    parser.add_argument("--dates", nargs="+", help="Daftar tanggal spesifik untuk dicari (misal: 28 29 30 31 atau 2026-08-28 2026-08-29)")
    parser.add_argument("--start-date", help="Tanggal awal pencarian (format: YYYY-MM-DD, default dari config.json)")
    parser.add_argument("--max-price", type=int, help="Filter harga maksimum per tiket (override config.json)")
    parser.add_argument("--watch", "-w", action="store_true", help="Mode War: Refresh terus-menerus sampai tiket harga target ditemukan")
    parser.add_argument("--interval", "-i", type=float, default=3.0, help="Jeda waktu refresh dalam detik untuk Mode War (default: 3.0 detik)")
    parser.add_argument("--start-at", help="Waktu mulai war tiket (format: HH:MM atau HH:MM:SS, misal: 16:00 atau 16:00:00)")
    
    args = parser.parse_args()
    
    print(Fore.CYAN + Style.BRIGHT + "="*65)
    print(Fore.CYAN + Style.BRIGHT + " 🚄 TIKET.COM AUTO-ORDER KERETA CEPAT WHOOSH CLI BOT 🚄 ")
    print(Fore.CYAN + Style.BRIGHT + "="*65)
    
    config = load_config(args.config)
    auth_cfg = config.get("auth", {})
    whoosh_cfg = config.get("whoosh", {})
    contact_cfg = config.get("contact", {})
    passengers_cfg = config.get("passengers", {})
    payment_cfg = config.get("payment", {})
    
    # Override jumlah penumpang jika opsi --pax diisi
    adults_count = args.pax if args.pax is not None else whoosh_cfg.get("adult", 1)
    if "adults" in passengers_cfg and args.pax is not None:
        passengers_cfg["adults"] = passengers_cfg["adults"][:args.pax]
            
    api = WhooshAPI(auth_cfg)
    
    origin = args.origin or whoosh_cfg.get("origin", "IDHMA")
    destination = args.dest or whoosh_cfg.get("destination", "IDTLA")
    dep_date = args.start_date or whoosh_cfg.get("departureDate", "2026-08-28")
    max_price = args.max_price if args.max_price is not None else whoosh_cfg.get("max_price", 0)
    
    adult_names = [p.get("fullName") for p in passengers_cfg.get("adults", [])[:adults_count]]

    if args.start_at:
        wait_until_target_time(args.start_at)

    # Handle Mode Multi-Date Search (via --dates atau --fridays)
    if args.dates is not None or args.fridays is not None:
        if args.dates is not None:
            prefix = dep_date[:7] if len(dep_date) >= 7 else "2026-08"
            dates_to_search = []
            for d in args.dates:
                d_clean = str(d).strip()
                if len(d_clean) <= 2 and d_clean.isdigit():
                    dates_to_search.append(f"{prefix}-{int(d_clean):02d}")
                else:
                    dates_to_search.append(d_clean)
            mode_title = f"MEMANTAU WHOOSH DI {len(dates_to_search)} TANGGAL PILIHAN ({', '.join(dates_to_search)})"
        else:
            count = args.fridays
            dates_to_search = get_upcoming_fridays(dep_date, count)
            mode_title = f"MEMANTAU WHOOSH TERMURAH DI {len(dates_to_search)} HARI JUMAT BERTURUT-TURUT"
        
        print(Fore.CYAN + Style.BRIGHT + f"\n🗓️ {mode_title}")
        print(Fore.CYAN + f"📍 Rute: {get_station_name(origin)} -> {get_station_name(destination)} | Tanggal Awal: {dep_date} | Penumpang ({adults_count}): {', '.join(adult_names)}")
        if max_price > 0:
            print(Fore.CYAN + f"🎯 Target Harga Maksimum: {format_price(max_price)}")
        print(Fore.CYAN + "="*65)
        
        attempt = 1
        interval = max(0.05, args.interval)
        results_by_date = []
        day_names_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

        try:
            while True:
                results_by_date = []
                print(Fore.YELLOW + f"\n[Putaran #{attempt}] 🔍 Memeriksa {len(dates_to_search)} Tanggal...")
                
                for idx, date_str in enumerate(dates_to_search, start=1):
                    try:
                        try:
                            dt = datetime.strptime(date_str, "%Y-%m-%d")
                            day_label = day_names_id[dt.weekday()]
                        except Exception:
                            day_label = ""
                            
                        t_list = api.search_whoosh(
                            origin=origin,
                            destination=destination,
                            departure_date=date_str,
                            adult=adults_count
                        )
                        if max_price > 0:
                            t_list = [t for t in t_list if t["price"] <= max_price]
                            
                        if t_list:
                            t_list.sort(key=lambda x: x["price"])
                            cheapest = t_list[0]
                            results_by_date.append({
                                "date": date_str,
                                "day": day_label,
                                "train": cheapest,
                                "total_trains": len(t_list)
                            })
                            print(Fore.GREEN + f"   [{idx}/{len(dates_to_search)}] {day_label} {date_str} -> ✅ {cheapest['trainName']} {cheapest['trainNumber']} ({format_price(cheapest['price'])})")
                        else:
                            print(Fore.YELLOW + f"   [{idx}/{len(dates_to_search)}] {day_label} {date_str} -> ❌ Belum ada tiket <= {format_price(max_price)}")
                    except Exception as e:
                        print(Fore.RED + f"   [{idx}/{len(dates_to_search)}] {date_str} -> ❌ Error: {e}")

                if results_by_date:
                    if attempt > 1:
                        print(Fore.GREEN + Style.BRIGHT + f"\n🎉 TIKET DITEMUKAN PADA PUTARAN #{attempt}!")
                    break

                if args.watch or args.auto:
                    print(Fore.YELLOW + f"⏳ Belum ada tiket <= {format_price(max_price)} di {len(dates_to_search)} Tanggal. Refreshing putaran berikutnya dalam {interval:.1f}s... (Ctrl+C untuk stop)")
                    time.sleep(interval)
                    attempt += 1
                else:
                    print(Fore.RED + f"\n❌ Tidak ditemukan kereta Whoosh <= {format_price(max_price)} untuk {len(dates_to_search)} Tanggal.")
                    print(Fore.CYAN + "💡 Petunjuk: Gunakan opsi '--watch' atau '--auto' untuk memantau tanggal secara berulang.")
                    sys.exit(1)

        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n👋 Pemantauan tanggal dihentikan oleh pengguna.")
            sys.exit(0)

        summary_table = []
        for idx, res in enumerate(results_by_date, start=1):
            tr = res["train"]
            summary_table.append([
                idx,
                res["date"],
                res["day"],
                f"{tr['trainName']} {tr['trainNumber']}",
                tr["wagonDetail"],
                tr["depart_time"],
                tr["arrival_time"],
                format_price(tr["price"])
            ])
            
        print(Fore.GREEN + Style.BRIGHT + f"\n📊 RINGKASAN WHOOSH TERMURAH DI {len(results_by_date)} TANGGAL:")
        print(tabulate(summary_table, headers=["No", "Tanggal", "Hari", "No. Kereta", "Kelas", "Berangkat", "Tiba", "Harga (IDR)"], tablefmt="fancy_grid"))

        if args.search_only:
            print(Fore.CYAN + "\nℹ️ Mode search-only selesai. Tidak ada transaksi yang diproses.")
            return

        selected_train = None
        if args.auto:
            best_res = min(results_by_date, key=lambda x: x["train"]["price"])
            selected_train = best_res["train"]
            dep_date = best_res["date"]
            print(Fore.GREEN + Style.BRIGHT + f"\n⚡ Mode Auto: Memilih tanggal & kereta termurah -> {dep_date} | {selected_train['trainNumber']} ({selected_train['wagonDetail']}) - {format_price(selected_train['price'])}")
        else:
            print(Fore.YELLOW + f"\nSilakan pilih nomor Jumat [1 - {len(results_by_date)}] yang ingin dipesan (atau 'q' untuk keluar): ", end="")
            choice = input().strip()
            if choice.lower() == 'q':
                print("Pemesanan dibatalkan.")
                return
            try:
                c_idx = int(choice) - 1
                if 0 <= c_idx < len(results_by_date):
                    selected_train = results_by_date[c_idx]["train"]
                    dep_date = results_by_date[c_idx]["date"]
                else:
                    print(Fore.RED + "Pilihan nomor tidak valid.")
                    return
            except ValueError:
                print(Fore.RED + "Input tidak valid.")
                return

    else:
        # Mode Pencarian Single Date dengan Loop Watch / Refresh Kontinu
        print(Fore.YELLOW + f"\n🔍 Memulai pencarian Kereta Cepat Whoosh: {get_station_name(origin)} -> {get_station_name(destination)} | Tanggal: {dep_date} | Penumpang ({adults_count}): {', '.join(adult_names)}")
        if max_price > 0:
            print(Fore.CYAN + f"🎯 Target Harga Maksimum: {format_price(max_price)}")
        print(Fore.CYAN + "="*65)
        
        attempt = 1
        interval = max(0.05, args.interval)
        filtered_trains = []

        try:
            while True:
                try:
                    trains = api.search_whoosh(
                        origin=origin,
                        destination=destination,
                        departure_date=dep_date,
                        adult=adults_count
                    )
                except Exception as e:
                    if args.watch or args.auto:
                        print(Fore.RED + f"\r[Percobaan #{attempt}] ❌ Error pencarian: {e}. Retry dalam {interval}s...", end="", flush=True)
                        time.sleep(interval)
                        attempt += 1
                        continue
                    else:
                        print(Fore.RED + f"❌ Error pencarian kereta Whoosh: {e}")
                        sys.exit(1)

                filtered_trains = trains
                if max_price > 0:
                    filtered_trains = [t for t in filtered_trains if t["price"] <= max_price]
                    
                if filtered_trains:
                    if attempt > 1:
                        print(Fore.GREEN + Style.BRIGHT + f"\n\n🎉 TIKET DITEMUKAN PADA PERCOBAAN #{attempt}!")
                    else:
                        print(Fore.GREEN + f"\n✅ Ditemukan {len(filtered_trains)} jadwal Kereta Cepat Whoosh yang memenuhi kriteria.\n")
                    display_trains_table(filtered_trains)
                    break
                    
                # Jika belum ditemukan tiket yang memenuhi kriteria filter
                if args.watch or args.auto:
                    print(Fore.YELLOW + f"\r[Percobaan #{attempt}] ⏳ Belum ada tiket <= {format_price(max_price)}. Refreshing dalam {interval:.1f}s... (Ctrl+C untuk stop)", end="", flush=True)
                    time.sleep(interval)
                    attempt += 1
                else:
                    print(Fore.RED + f"\n❌ Tidak ada jadwal kereta yang memenuhi filter (Harga Maks: {format_price(max_price)}).")
                    print(Fore.CYAN + "💡 Petunjuk: Gunakan opsi '--watch' atau '--auto' untuk memantau & refresh otomatis sampai tiket harga target ditemukan.")
                    sys.exit(1)

        except KeyboardInterrupt:
            print(Fore.YELLOW + "\n\n👋 Mode War / Refresh dihentikan oleh pengguna.")
            sys.exit(0)

        if args.search_only:
            print(Fore.CYAN + "\nℹ️ Mode search-only selesai. Tidak ada transaksi yang diproses.")
            return

        # Urutkan berdasarkan harga termurah
        filtered_trains.sort(key=lambda x: x["price"])
        
        selected_train = None
        if args.auto:
            selected_train = filtered_trains[0]
            print(Fore.GREEN + Style.BRIGHT + f"\n⚡ Mode Auto: Memilih jadwal termurah -> {selected_train['trainName']} {selected_train['trainNumber']} ({selected_train['wagonDetail']}) - {format_price(selected_train['price'])}")
        else:
            print(Fore.YELLOW + f"\nSilakan pilih nomor jadwal [1 - {len(filtered_trains)}] (atau 'q' untuk keluar): ", end="")
            choice = input().strip()
            if choice.lower() == 'q':
                print("Pemesanan dibatalkan.")
                return
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(filtered_trains):
                    selected_train = filtered_trains[idx]
                else:
                    print(Fore.RED + "Pilihan nomor tidak valid.")
                    return
            except ValueError:
                print(Fore.RED + "Input tidak valid.")
                return

    # Proses Pemesanan
    price = selected_train["price"]
    
    print(Fore.CYAN + "\n==================================================")
    print(Fore.CYAN + f"🚀 MEMULAI PROSES AUTO-ORDER WHOOSH ({adults_count} PENUMPANG)")
    print(Fore.CYAN + "==================================================")
    
    # Step 1: Add to Cart
    print(Fore.YELLOW + "1️⃣ Menambahkan Tiket Kereta ke Keranjang (Cart)...")
    try:
        cart_id, secret = api.add_to_cart(selected_train, adult_count=adults_count)
        print(Fore.GREEN + f"   ✔ Kereta berhasil masuk keranjang! Cart ID: {cart_id}")
    except Exception as e:
        print(Fore.RED + f"   ✖ Gagal add to cart Whoosh: {e}")
        sys.exit(1)

    if args.dry_run:
        print(Fore.MAGENTA + Style.BRIGHT + "\n🧪 [DRY-RUN] Simulasi berhasil sampai tahap Cart ID. Pemesanan tidak dilanjutkan ke pembuatan booking.")
        return

    # Step 2: Get Cart Detail & Update Passengers
    print(Fore.YELLOW + f"2️⃣ Mengisi Data Kontak & Penumpang ({', '.join(adult_names)})...")
    adult_list = passengers_cfg.get("adults", [])[:adults_count]
    try:
        api.get_cart(cart_id, secret)
        api.update_passengers(cart_id, secret, contact_cfg, adult_list)
        print(Fore.GREEN + "   ✔ Data kontak & penumpang berhasil diperbarui.")
    except Exception as e:
        print(Fore.RED + f"   ✖ Gagal update penumpang: {e}")
        sys.exit(1)

    # Step 3: Create Order Booking
    print(Fore.YELLOW + "3️⃣ Membuat Order Booking Whoosh...")
    try:
        booking_res = api.create_order(cart_id, secret)
        order_id = booking_res["order_id"]
        order_hash = booking_res["order_hash"]
        payment_url = booking_res["payment_url"]
        print(Fore.GREEN + Style.BRIGHT + f"   ✔ ORDER SUCCESS! Order ID: {order_id} | Hash: {order_hash}")
    except Exception as e:
        print(Fore.RED + f"   ✖ Gagal membuat order Whoosh: {e}")
        sys.exit(1)

    # Step 4: Select Payment Method & Confirm
    pay_method = payment_cfg.get("method", "VA_BCA")
    print(Fore.YELLOW + f"4️⃣ Konfirmasi Metode Pembayaran ({pay_method})...")
    try:
        api.initiate_payment_landing(order_id, order_hash)
        api.select_payment_detail(order_id, order_hash, pay_method)
        confirm_res = api.confirm_payment(order_id, order_hash, pay_method)
        print(Fore.GREEN + f"   ✔ Metode pembayaran {pay_method} berhasil dikonfirmasi.")
    except Exception as e:
        print(Fore.YELLOW + f"   ⚠️ Pembayaran otomatis belum selesai: {e}")

    # Ringkasan Akhir Pemesanan
    print(Fore.GREEN + Style.BRIGHT + "\n" + "="*65)
    print(Fore.GREEN + Style.BRIGHT + "🎉 PESANAN TIKET KERETA CEPAT WHOOSH BERHASIL DIBUAT! 🎉")
    print(Fore.GREEN + Style.BRIGHT + "="*65)
    print(f"📌 Order ID     : {Fore.YELLOW}{order_id}")
    print(f"🔑 Order Hash   : {order_hash}")
    print(f"🚄 Kereta       : {selected_train['trainName']} {selected_train['trainNumber']} ({selected_train['wagonDetail']})")
    print(f"📍 Rute         : {get_station_name(origin)} -> {get_station_name(destination)} ({dep_date})")
    print(f"⏰ Jam          : {selected_train['depart_time']} - {selected_train['arrival_time']}")
    print(f"👥 Penumpang    : {', '.join(adult_names)}")
    print(f"💰 Total Harga  : {Fore.GREEN}{format_price(price * adults_count)}")
    print(f"💳 Pembayaran   : {pay_method}")
    print(f"🔗 Link Bayar   : {Fore.CYAN}{payment_url}")
    print(Fore.GREEN + Style.BRIGHT + "="*65 + "\n")

if __name__ == "__main__":
    main()
