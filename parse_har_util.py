import json
import os
import argparse
import sys

def parse_har_summary(har_path):
    if not os.path.exists(har_path):
        print(f"File {har_path} tidak ditemukan!")
        sys.exit(1)
        
    print(f"Membaca file HAR: {har_path} ({os.path.getsize(har_path):,} bytes)...")
    with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
        data = json.load(f)
        
    entries = data.get('log', {}).get('entries', [])
    print(f"Total entri HTTP: {len(entries)}")
    
    ms_entries = []
    for i, entry in enumerate(entries):
        req = entry.get('request', {})
        url = req.get('url', '')
        if 'ms-gateway' in url:
            ms_entries.append((i, req.get('method'), url, entry.get('response', {}).get('status')))
            
    print(f"\nDiscovered {len(ms_entries)} tiket.com ms-gateway API endpoints:")
    print("="*80)
    for idx, method, url, status in ms_entries:
        print(f"[{idx:4d}] {method:6s} {status} -> {url}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HAR Parser Utility for Tiket.com")
    parser.add_argument("--har", default="www.tiket.comhar.har", help="Path file HAR")
    args = parser.parse_args()
    parse_har_summary(args.har)
