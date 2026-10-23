import json
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tiket_api import TiketAPI
from tabulate import tabulate

def check_all_dates():
    with open('config.json', 'r', encoding='utf-8') as f:
        cfg = json.load(f)

    api = TiketAPI(cfg.get('auth', {}))

    # Requested dates:
    # 28 & 29 Aug 2026
    # Thursdays & Fridays in Sep 2026: 3, 4, 10, 11, 17, 18, 24, 25
    target_dates = [
        ('2026-08-28', 'Jumat'),
        ('2026-08-29', 'Sabtu'),
        ('2026-09-03', 'Kamis'),
        ('2026-09-04', 'Jumat'),
        ('2026-09-10', 'Kamis'),
        ('2026-09-11', 'Jumat'),
        ('2026-09-17', 'Kamis'),
        ('2026-09-18', 'Jumat'),
        ('2026-09-24', 'Kamis'),
        ('2026-09-25', 'Jumat'),
    ]

    print("=" * 70)
    print("🔍 PENCEKAN JADWAL PENERBANGAN JAKARTA (JKTC) -> BALI (DPSC)")
    print("🎯 Target Harga Maksimum: Rp 850.000 / pax")
    print("=" * 70 + "\n")

    overall_cheapest = []

    for d_str, day_name in target_dates:
        try:
            flights = api.search_flights('JKTC', 'DPSC', d_str, adult=1)
        except Exception as e:
            print(f"❌ {d_str} ({day_name}): Error - {e}")
            continue

        if not flights:
            print(f"❌ {d_str} ({day_name}): Tidak ada penerbangan ditemukan.")
            continue

        # Sort by price ascending
        flights.sort(key=lambda x: x['price'])
        cheapest = flights[0]
        
        under_target = [f for f in flights if f['price'] <= 850000]

        status = f"✅ AD TIKET <= 850rb ({len(under_target)})" if under_target else "⚠️ Harga terendah di atas 850rb"

        overall_cheapest.append([
            d_str,
            day_name,
            cheapest['airline_name'],
            cheapest['depart_time'],
            cheapest['arrival_time'],
            f"Rp {cheapest['price']:,.0f}".replace(",", "."),
            status
        ])

        print(f"📅 Tanggal: {d_str} ({day_name}) | Total Penerbangan: {len(flights)}")
        print(f"   Termurah: {cheapest['airline_name']} ({cheapest['depart_time']} - {cheapest['arrival_time']}) -> Rp {cheapest['price']:,.0f}".replace(",", "."))
        if under_target:
            print(f"   🎉 Ada {len(under_target)} penerbangan dibawah/sama Rp 850.000!")
            for u in under_target[:3]:
                print(f"      - {u['airline_name']} | {u['depart_time']} - {u['arrival_time']} | Rp {u['price']:,.0f}".replace(",", "."))
        else:
            print(f"   ℹ️ Belum ada tiket <= Rp 850.000")
        print("-" * 70)

    print("\n" + "=" * 70)
    print("📊 RINGKASAN HARGA TERMURAH PER TANGGAL:")
    print("=" * 70)
    print(tabulate(overall_cheapest, headers=['Tanggal', 'Hari', 'Maskapai Termurah', 'Berangkat', 'Tiba', 'Harga/Pax', 'Status 850rb'], tablefmt='fancy_grid'))

if __name__ == "__main__":
    check_all_dates()
