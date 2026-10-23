import json
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from whoosh_api import WhooshAPI
from tabulate import tabulate

def search():
    with open('config.json', 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    
    api = WhooshAPI(cfg.get('auth', {}))
    whoosh_cfg = cfg.get('whoosh', {})
    origin = whoosh_cfg.get('origin', 'IDHMA')
    dest = whoosh_cfg.get('destination', 'IDTLA')
    adult = whoosh_cfg.get('adult', 2)

    dates = ['2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31']
    print(f"Rute: {origin} -> {dest} | Penumpang: {adult} Dewasa\n")

    summary = []

    for d in dates:
        print(f"==================================================")
        print(f"📅 TANGGAL: {d}")
        print(f"==================================================")
        try:
            trains = api.search_whoosh(origin, dest, d, adult)
        except Exception as e:
            print(f"Error: {e}")
            continue

        if not trains:
            print("Tidak ada jadwal kereta ditemukan.\n")
            continue

        # Sort by departure time
        trains.sort(key=lambda x: (x['depart_time'], x['price']))

        # Find cheapest Economy Premium
        pe_trains = [t for t in trains if t['subClass'] == 'PE']
        cheapest_pe = min(pe_trains, key=lambda x: x['price']) if pe_trains else None

        if cheapest_pe:
            summary.append([
                d,
                f"{cheapest_pe['trainName']} {cheapest_pe['trainNumber']}",
                cheapest_pe['depart_time'],
                cheapest_pe['arrival_time'],
                f"Rp {cheapest_pe['price']:,.0f}".replace(",", "."),
                cheapest_pe['available_seats']
            ])

        table_data = []
        for t in trains:
            table_data.append([
                t['trainNumber'],
                t['wagonDetail'],
                t['depart_time'],
                t['arrival_time'],
                f"Rp {t['price']:,.0f}".replace(",", "."),
                t['available_seats']
            ])
        
        print(tabulate(table_data, headers=['No. Kereta', 'Kelas', 'Berangkat', 'Tiba', 'Harga/Pax', 'Sisa Kursi'], tablefmt='fancy_grid'))
        print()

    print("==================================================")
    print("📊 RINGKASAN HARGA PE (EKONOMI PREMIUM) TERMURAH PER TANGGAL:")
    print("==================================================")
    print(tabulate(summary, headers=['Tanggal', 'Kereta Termurah', 'Berangkat', 'Tiba', 'Harga/Pax', 'Sisa Kursi'], tablefmt='fancy_grid'))

if __name__ == "__main__":
    search()
