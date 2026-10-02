# TASK BRIEF UNTUK Nomad 7
# Proyek: Otomasi Konten Blog "Minum Kopiku"

---

## KONTEKS

Blog: `minumkopiku.blogspot.com` — platform Blogger, niche kopi, sudah 39 artikel, terakhir posting Juni 2025 (terjeda ±1 tahun). Contoh artikel referensi gaya tulisan: `https://minumkopiku.blogspot.com/2025/06/5-alasan-yang-memperkuat-kopi-sebagai.html`

Label yang sudah ada: Tentang Kopi, Kopi Sehat, Proses Kopi, Resep Kopi, Pasar Kopi, Mesin Kopi, Tips Kopi, Formula, Spesifikasi, Desain, Buku Kopi.

## OBJEKTIF

Bangun sistem otomatis yang jalan 2x sehari via cron di VPS:
1. Generate 1 artikel baru bertema kopi
2. Publish otomatis ke Blogger
3. Kirim notifikasi ke Telegram (sukses/gagal)
4. Siapkan (bukan eksekusi) readiness untuk monetisasi AdSense

---

## 1. CONTENT GENERATION

**Gaya tulisan** — ikuti pola artikel referensi di atas:
- Judul deskriptif, panjang 800–1200 kata
- Intro 2 paragraf pembuka konteks
- 4–6 subjudul H2, tiap bagian 1 poin utama
- Paragraf "Tantangan/Catatan" opsional sebelum kesimpulan
- Kesimpulan yang merangkum + ajakan halus (bukan hard-sell)
- Bahasa Indonesia natural, bukan hasil translate kaku, hindari repetisi kata "kopi" berlebihan (SEO over-optimization)
- Tag/label diambil dari daftar label yang sudah ada atau bikin label baru kalau topik memang beda

**Rotasi topik** — WAJIB anti-duplikat:
- Simpan daftar 60 topik kopi (cukup untuk ±1 bulan @ 2x/hari) di `CONTENT_TOPICS.md`, kategori campuran: kesehatan, budaya, bisnis/pasar, brewing method, jenis biji, mesin/alat, resep, tren
- Sebelum generate, cek `CONTENT_LOG.md` (judul + tanggal + label yang sudah pernah dipakai) supaya gak ada topik/angle yang keulang persis
- Setelah publish, tulis entry baru ke `CONTENT_LOG.md`: `- [YYYY-MM-DD HH:mm] Judul | Label | URL post`

**Gambar** — kalau ada akses image generation, sertakan 1 gambar ilustrasi per artikel (caption singkat, mirip pola blog lama). Kalau belum ada setup image gen, publish dulu tanpa gambar dan laporkan itu sebagai keterbatasan di `<result>`.

## 2. AUTO-PUBLISH KE BLOGGER

- Gunakan **Blogger API v3** (`googleapis` untuk Node atau `google-api-python-client` untuk Python)
- Perlu: OAuth2 credentials (client ID/secret) dari Google Cloud Console + Blog ID (didapat via endpoint `blogs.getByUrl` pakai URL blog)
- Simpan token & credential di `.env`, JANGAN hardcode, JANGAN commit ke repo
- Status publish: langsung publish (bukan draft) — kecuali aku bilang lain
- Kalau API call gagal, retry maks 3x, kalau tetap gagal → simpan draft artikel lokal + kirim alert Telegram bahwa publish gagal (jangan hilang begitu saja)

## 3. NOTIFIKASI TELEGRAM

- Pakai Telegram Bot API (`sendMessage`), token bot & chat ID disimpan di `.env`
- Format notifikasi sukses:
  ```
  ✅ Artikel baru published
  Judul: {judul}
  Label: {label}
  URL: {url}
  Waktu: {timestamp}
  ```
- Format notifikasi gagal:
  ```
  ❌ Publish gagal
  Judul: {judul}
  Error: {error_message}
  Draft disimpan di: {path}
  ```

## 4. CRON SCHEDULE

- 2x sehari, jam disarankan: **08:00 dan 16:00 WIB** (sesuaikan ke UTC di crontab VPS, cek dulu `timedatectl`)
- Pakai `flock` supaya run gak numpuk kalau run sebelumnya belum selesai
- Semua output di-log ke file, jangan silent fail

## 5. MONETISASI ADSENSE — INI PENTING, BACA DULU

Cron **tidak bisa** mengurus approval AdSense — itu proses manual Google yang butuh review manusia dan akses akun Google Boss langsung. Yang bisa Hermes lakukan cuma **menyiapkan kesiapan**, bukan mengeksekusi approval:

Tugas Kamu di bagian ini (sekali jalan, bukan cron):
1. Audit halaman wajib yang Google minta: Privacy Policy, Term of Service, Disclaimer, About — cek apakah sudah lengkap & sesuai standar AdSense (blog ini sepertinya sudah punya ketiganya, tolong cek isinya)
2. Cek jumlah & kualitas konten — Google biasanya minta konten orisinal, cukup banyak (30+ artikel biasanya cukup, blog ini sudah 39), dan aktivitas publish yang konsisten (bukan terjeda 1 tahun kayak sekarang — makanya kita mulai posting rutin lagi)
3. Rangkum checklist kesiapan dalam laporan ke aku, termasuk apa saja yang masih kurang
4. **Aku yang akan submit aplikasi AdSense manual** lewat akun Google-ku sendiri setelah checklist ini beres — Hermes tidak eksekusi bagian ini

---

## YANG AKU MINTA DARI KAMU

1. Buat `<plan>` dulu sebelum eksekusi — termasuk struktur folder script, dependency yang dipakai, dan urutan setup (credentials Blogger API → credentials Telegram → script generate+publish → cron entry → testing manual 1x sebelum di-cron-kan)
2. Setelah plan disetujui, eksekusi bertahap, commit tiap milestone ke `PROJECT_MEMORY.md`
3. Sebelum aktifin cron permanen, jalankan **1x manual test run** dan kirim hasilnya ke aku dulu buat direview
4. Tutup dengan `<result>` lengkap: file apa saja yang dibuat, cron entry final, status test run, dan checklist kesiapan AdSense

## GURU FILE BOSS UNTUK KAMU

1. Gunakan 'Prompting-Claude-Opus-5.md' jika kamu tersesat
2. Jika kamu merasa tidak tersesat, lanjutkan
3. Boss percaya bahwa kamu tahu apa yang harus kamu lakukan


Kalau ada yang butuh keputusan dariku (misalnya: mau pakai akun Google mana buat Blogger API, budget image gen, atau topik yang mau diprioritaskan duluan), tanya di awal sebelum eksekusi — jangan nebak.
