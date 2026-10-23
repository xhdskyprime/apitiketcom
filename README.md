# Tiket.com Flight, Kereta Cepat (Whoosh), & Berburu Tiket Murah Auto-Order CLI Bot

Bot Command Line Interface (CLI) otomatisasi pemesanan tiket **Pesawat**, **Kereta Cepat (Whoosh)**, & War Event **Berburu Tiket Murah (Harta Karun)** di **tiket.com** berbasis HTTP API (`ms-gateway`). Bot ini bekerja secara langsung melalui koneksi API tanpa membuka antarmuka browser.

---

## 📁 Struktur Berkas

- 📄 `api_server.py` : REST API Publik (FastAPI) dengan dokumentasi Swagger & Tool Schema AI untuk AI Muse.
- 📄 `bot.py` : Script utama CLI pemesanan tiket **pesawat** dengan antarmuka terminal interaktif.
- 📄 `cek_promo_bali.py` : Script cepat verifikasi sesi/cookie & pemantau tiket promo Jakarta -> Bali (DPSC).
- 📄 `tiket_api.py` : API client untuk tiket **pesawat** (`ms-gateway`).
- 📄 `bot_whoosh.py` : Script utama CLI pemesanan tiket **Kereta Cepat (Whoosh)**.
- 📄 `whoosh_api.py` : API client untuk **Kereta Cepat (Whoosh)** (`ms-gateway/tix-train-*`).
- 📄 `bot_berburu.py` : Script utama CLI War Event **Berburu Tiket Murah (Harta Karun)**.
- 📄 `berburu_api.py` : API client untuk event **Berburu Tiket Murah** (`ms-gateway/ggwp-server/harta-karun`).
- 📄 `config.json` : Konfigurasi akun, data kontak, data penumpang, parameter pencarian, & metode pembayaran.
- 📄 `berburutiket.har` : Berkas HTTP log untuk analisis endpoint Berburu Tiket Murah.
- 📄 `keretacepat.har` : Berkas HTTP log untuk analisis endpoint Kereta Cepat Whoosh.
- 📄 `requirements.txt` : Dependensi Python (`curl_cffi`, `requests`, `colorama`, `tabulate`, `fastapi`, `uvicorn`).

---

## 🌴 Mode Khusus: War Promo Gledek Bali (Mulai Rp 399rb)

1. **Uji Validitas Cookie & Sesi Akun**:
   ```bash
   python cek_promo_bali.py
   ```
2. **War Otomatis saat Jam Gledek Tiba (Refresh per 2 detik di semua tanggal target)**:
   ```bash
   python bot.py --auto --watch --interval 2 --all-dates --pax 2
   ```
3. **Standby dengan Timer Hitung Mundur (Contoh: Menuju Jam 11:59 atau 16:59 WIB)**:
   ```bash
   python bot.py --auto --watch --interval 2 --all-dates --pax 2 --schedule 11:59
   ```

---

## 🚀 Cara Penggunaan

### 1. Bot Tiket Pesawat (`bot.py`)

- **Cari Tiket Pesawat Termurah**:
  ```bash
  python bot.py --search-only --pax 2
  ```

- **Auto-Order Tiket Pesawat Termurah**:
  ```bash
  python bot.py --auto --pax 2
  ```

- **Cari & Bandingkan 5 Hari Jumat (Pesawat)**:
  ```bash
  python bot.py --fridays 5 --search-only --start-date 2026-08-28 --pax 2
  ```

---

### 2. Bot Kereta Cepat Whoosh (`bot_whoosh.py`)

- **Cari Jadwal Kereta Whoosh Termurah (Halim -> Tegalluar)**:
  ```bash
  python bot_whoosh.py --search-only --pax 2
  ```

- **Auto-Order Tiket Kereta Cepat Whoosh Termurah**:
  ```bash
  python bot_whoosh.py --auto --pax 2
  ```

- **Cari & Bandingkan 5 Hari Jumat (Whoosh)**:
  ```bash
  python bot_whoosh.py --fridays 5 --search-only --start-date 2026-08-28 --pax 2
  ```

- **Mode Simulasi / Dry-Run (Whoosh)**:
  ```bash
  python bot_whoosh.py --auto --dry-run --pax 2
  ```

---

### 3. Bot War Event Berburu Tiket Murah / Harta Karun (`bot_berburu.py`)

- **Jalankan Bot War Berburu Tiket Murah**:
  ```bash
  python bot_berburu.py
  ```

- **Strategi Bot**:
  - **Sniper Mode**: Memantau sisa waktu countdown secara real-time dan melakukan HIT presisi ketika sisa waktu `<= 2.5` detik jika posisi harta karun belum berada di akun kita.
  - **Efisiensi Token**: Tidak membuang token jika akun kita sudah berada pada posisi terdepan (`LEADING`).
  - **Auto Re-Steal**: Otomatis merebut kembali jika player lain mengambil alih posisi harta karun sebelum timer habis.

---

### 4. Mode War / Refresh Kontinu (`--watch` & `--interval`)

Memantau & melakukan **refresh pencarian secara terus-menerus** hingga tiket dengan harga target (`max_price`) tersedia, lalu **langsung melakukan booking instan**:

- **Mode War Kereta Cepat Whoosh (Refresh tiap 2 detik)**:
  ```bash
  python bot_whoosh.py --auto --watch --interval 2 --pax 2
  ```

- **Mode War Tiket Pesawat Single Date (Refresh tiap 3 detik)**:
  ```bash
  python bot.py --auto --watch --interval 3 --pax 2
  ```

- **Mode War Memantau 5 Hari Jumat Sekaligus (Pesawat)**:
  ```bash
  python bot.py --fridays 5 --auto --watch --interval 3 --pax 2
  ```

- **Mode War Memantau 5 Hari Jumat Sekaligus (Whoosh)**:
  ```bash
  python bot_whoosh.py --fridays 5 --auto --watch --interval 2 --pax 2
  ```

---

### 5. Public REST API & Integrasi AI Muse (`api_server.py`)

Menjalankan backend REST API agar AI Muse / Agent LLM dapat melakukan pencarian, pemesanan tiket otomatis, dan war tiket sendiri:

- **Menjalankan Server API**:
  ```bash
  python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
  ```
- **Dokumentasi Interaktif Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Tool Calling Schema untuk AI Muse**: [http://localhost:8000/ai/tools](http://localhost:8000/ai/tools)
- **System Prompt Guide untuk AI Muse**: [http://localhost:8000/ai/prompt](http://localhost:8000/ai/prompt)
- **Membuka Akses Publik ke Internet (Cloudflare Tunnel)**:
  ```bash
  "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000
  ```
