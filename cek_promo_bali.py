import json
import sys
import os

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from colorama import init, Fore, Style
from tabulate import tabulate
from tiket_api import TiketAPI

init(autoreset=True)

def main():
    print(Fore.CYAN + Style.BRIGHT + "=" * 70)
    print(Fore.CYAN + Style.BRIGHT + "  🌴 CEK KETERSEDIAAN PROMO TIKET PESAWAT JAKARTA -> BALI ✈️  ")
    print(Fore.CYAN + Style.BRIGHT + "=" * 70)

    config_path = "config.json"
    if not os.path.exists(config_path):
        print(Fore.RED + f"❌ File {config_path} tidak ditemukan!")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    auth = cfg.get("auth", {})
    search = cfg.get("search", {})
    passengers = cfg.get("passengers", {})

    api = TiketAPI(auth)

    # 1. Validasi Sesi / Cookie Akun
    print(Fore.YELLOW + "\n1️⃣ Memeriksa status sesi & cookie akun tiket.com...")
    session_data = None
    try:
        session_data = api.validate_session()
    except Exception as e:
        session_data = None

    if session_data and session_data.get("code") == "SUCCESS":
        user_email = (session_data.get("data") or {}).get("email") or auth.get("account_id")
        print(Fore.GREEN + f"   ✔ Sesi AKTIF! Login sebagai: {user_email}")
    else:
        print(Fore.RED + Style.BRIGHT + "   ✖ Sesi EXPIRED atau Cookie Belum Terisi!")
        print(Fore.YELLOW + "   👉 Silakan perbarui 'cookie' di config.json sebelum war dimulai:")
        print(Fore.WHITE + "      1. Buka https://www.tiket.com di Google Chrome / Edge & Login ke akun.")
        print(Fore.WHITE + "      2. Buka DevTools (F12) -> Tab 'Network' -> Filter: 'ms-gateway'")
        print(Fore.WHITE + "      3. Klik salah satu request API -> Tab 'Headers' -> Copy isi 'Cookie'")
        print(Fore.WHITE + "      4. Buka config.json -> Paste ke field auth.cookie\n")
        print(Fore.CYAN + "   💡 Setelah diupdate, jalankan kembali 'python cek_promo_bali.py' untuk tes.")
        return

    # 2. Cek Parameter Pencarian
    origin = search.get("origin", "JKTC")
    destination = search.get("destination", "DPSC")
    adult_count = search.get("adult", 2)
    max_price = search.get("max_price", 500000)
    target_dates = search.get("target_dates", [])
    adult_names = [p.get("fullName") for p in passengers.get("adults", [])[:adult_count]]

    print(Fore.CYAN + f"\n📍 Rute: {origin} -> {destination} (Jakarta -> Bali)")
    print(Fore.CYAN + f"👥 Penumpang ({adult_count}): {', '.join(adult_names)}")
    print(Fore.CYAN + f"🎯 Target Harga Maksimum: Rp {max_price:,.0f}".replace(",", "."))
    print(Fore.CYAN + f"📅 Total Tanggal Target: {len(target_dates)} tanggal weekend")
    print(Fore.CYAN + "-" * 70)

    if not target_dates:
        print(Fore.RED + "❌ Tidak ada 'target_dates' yang diatur di config.json!")
        return

    summary_rows = []
    found_promo = []

    print(Fore.YELLOW + "\n2️⃣ Memeriksa jadwal & harga tiket di setiap tanggal target...")
    for idx, d_str in enumerate(target_dates, start=1):
        import time
        time.sleep(0.4)
        sys.stdout.write(f"\r🔍 [{idx}/{len(target_dates)}] Memeriksa tanggal {d_str}... ")
        sys.stdout.flush()
        try:
            flights = api.search_flights(
                origin=origin,
                destination=destination,
                departure_date=d_str,
                adult=adult_count
            )
        except Exception as e:
            print(Fore.RED + f"\n   ❌ {d_str}: Gagal ({e})")
            continue

        if not flights:
            summary_rows.append([idx, d_str, "-", "-", "-", "-", "❌ Tidak ada penerbangan"])
            continue

        flights.sort(key=lambda x: x["price"])
        cheapest = flights[0]

        is_under = cheapest["price"] <= max_price
        status_str = f"🎉 PROMO! (<= Rp {max_price:,.0f})".replace(",", ".") if is_under else f"⚠️ Di atas target"

        price_str = f"Rp {cheapest['price']:,.0f}".replace(",", ".")
        summary_rows.append([
            idx,
            d_str,
            cheapest["airline_name"],
            cheapest["depart_time"],
            cheapest["arrival_time"],
            price_str,
            status_str
        ])

        if is_under:
            found_promo.append((d_str, cheapest))

    print("\r" + " " * 60 + "\r", end="")

    headers = ["No", "Tanggal", "Maskapai Termurah", "Berangkat", "Tiba", "Harga/Pax", "Status Promo"]
    print("\n" + tabulate(summary_rows, headers=headers, tablefmt="fancy_grid"))

    if found_promo:
        print(Fore.GREEN + Style.BRIGHT + f"\n🎉 DITEMUKAN {len(found_promo)} PENERBANGAN DENGAN HARGA PROMO (<= Rp {max_price:,.0f})!".replace(",", "."))
        for d, f in found_promo:
            print(Fore.GREEN + f"   - {d} | {f['airline_name']} ({f['depart_time']} - {f['arrival_time']}) -> Rp {f['price']:,.0f}".replace(",", "."))
        print(Fore.CYAN + "\n🚀 Untuk langsung auto-booking tiket ini, jalankan:")
        print(Fore.WHITE + Style.BRIGHT + "   python bot.py --auto --all-dates")
    else:
        print(Fore.YELLOW + f"\nℹ️ Belum ada tiket di bawah/sama dengan Rp {max_price:,.0f}.".replace(",", "."))
        print(Fore.CYAN + "💡 Saat Jam War Promo Gledek dibuka pada tanggal 26, jalankan mode war:")
        print(Fore.WHITE + Style.BRIGHT + "   python bot.py --auto --watch --interval 2 --all-dates")

if __name__ == "__main__":
    main()
