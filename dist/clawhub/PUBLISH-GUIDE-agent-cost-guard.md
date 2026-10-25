# Publish record: agent-cost-guard (ClawHub)

Folder yang dipublish (isi repo ini): `dist/clawhub/agent-cost-guard/`

    SKILL.md                        checklist audit biaya + daftar isi paket
    references/prices-reference.md  tabel harga penyedia (perkiraan Okt 2026)
    references/case-study.md        kasus komunitas di balik "inheritance trap"
    agents/openai.yaml              display_name + short_description untuk katalog

Tidak ada kode, kunci, token, atau kredensial di dalam paket. Paket ini read-only: tidak ada
jalur pembayaran, tidak ada panggilan jaringan, tidak membaca berkas.

## Perintah publish

```
cd /home/ubuntu/prpo_ai/dist/clawhub
clawhub skill publish ./agent-cost-guard --slug agent-cost-guard \
  --name "Agent Cost Guard" --version <x.y.z> \
  --categories agents \
  --topics cost,curator,background-work,guardrail,audit \
  --source-repo https://github.com/33ai-wq/b0x-sniper-lite \
  --source-commit <sha commit paket ini> \
  --source-path dist/clawhub/agent-cost-guard \
  --changelog "<alasan versi ini>" --json
```

`--source-repo` dan `--source-commit` harus dikirim BERSAMA (salah satu saja ditolak), dan commit
tersebut harus sudah ada di remote sebelum publish.

## Riwayat versi

### 1.0.0 - diblokir, tidak pernah tayang

- publish 24 Okt 2026; `versionId k974fyrnmkf46byfeme9s5gy0h8gwhhx`, fingerprint `d0c647e7...`.
- Status: `hidden by moderation (pending.publication)` selama >10 jam.
- `clawhub inspect agent-cost-guard` -> `Moderate CLEAN`, `Mod Note "No suspicious patterns detected."`,
  `Engine v2.4.26`. Jadi isinya tidak ditandai berbahaya.
- Zip pindai: `static-analysis.json` = clean (0 temuan), `manifest.json` = `status: succeeded`,
  `writtenBack: true` - tetapi `clawscan.json`, `endor.json`, `skillspector.json`, `virustotal.json`
  semuanya `null` -> SkillSpector tidak pernah menyelesaikan pemindaian, dan publikasi menunggu itu.
- Bukti pembanding: dua skill kita yang lolos (`xh-agents-x402`, `x402-market-recon`) memuat
  `security.scannerReports` dengan kunci `aig` + `skillspector`; rilis yang tertahan tidak punya itu.

### 1.0.1 - perbaikan graf berkas

Penyebab yang terukur: paket 1.0.0 **tidak merujuk satu berkas pun** dari SKILL.md, padahal ia mengirim
dua berkas referensi. Dua skill kita yang lolos merujuk SETIAP berkasnya dari SKILL.md. Dua changelog
publik menyebut kelas kegagalan yang sama: "Avoid a false missing-file reference so SkillSpector can
complete the full package scan".

Yang diubah: bagian **"What is in this package"** (daftar keempat berkas) + rujukan inline ke kedua berkas
referensi di Step 3 dan Step 4. Tidak ada perubahan perilaku paket - tetap dokumentasi read-only.

Paket diperiksa ulang sebelum publish: 4 berkas, setiap berkas dirujuk dari SKILL.md, ASCII murni (tanpa
em dash/arrow - karakter non-ASCII dibaca sebagai unicode deception oleh pemindai).

Receipt publish:

    source-commit : 76cc49ce6f8acd6a78c81c74ad875ccffdd2b2b6
    versionId     : k97bbx81zbe574pp06wyybhwqx8gynqx
    attemptId     : zx7cabkqe45j0sjpc1bsprpbp18gz7gx
    fingerprint   : 700cc773f3a3d8bdc4d15b1200daf243b3088515cde36b32ab5cee82a03e20b7
    fileCount     : 4
    publicationStatus: pending

Saat publish 1.0.1 (±1 menit setelah unggah): `static-analysis.json` clean, sisanya (`clawscan`,
`endor`, `skillspector`, `virustotal`) masih `null`, dan `clawhub inspect` masih menampilkan Mod Time
versi 1.0.0. Bukti perbaikan yang harus dicari: **Mod Time di `clawhub inspect` berubah**, dan/atau
`skillspector.json` di zip versi ini berisi isi (bukan `null`).

**KOREKSI sesudahnya:** catatan awal di sini menyebut "withdraw versi lama lalu unggah ulang". Itu **salah**.
Penyebabnya stall di sisi ClawHub, dan bukti dari tracker vendor menunjukkan yang bisa tembus justru
**kiriman versi BARU** (`withdraw` tidak menolong; `clawhub unhide` menjawab Forbidden untuk skill yang
disembunyikan moderasi). Lihat bagian 1.0.2 di bawah.

### 1.0.2 - kiriman ulang untuk re-queue (paket identik dengan 1.0.1)

Alasan: `pending.publication` pada rilis CLEAN adalah stall di sisi ClawHub (bukan isi paket). Bukti dari tracker
vendor menunjukkan stall ini **intermiten** dan **kiriman versi berikutnya bisa tembus** sementara versi yang
tersangkut tidak pernah pulih. Jadi versi baru adalah retry yang sah, bukan kerja ganda.

Yang dikirim: paket **byte-identik** dengan 1.0.1 (fingerprint sama, `700cc773...`) + catalog metadata
(`--categories agents,operations`, `--topics cost,curator,background-work,guardrail,audit`).

Receipt publish:

    source-commit : 76cc49ce6f8acd6a78c81c74ad875ccffdd2b2b6
    versionId     : k975vnhjjbds356zv6hfnsjvrs8gz6mz
    attemptId     : zx71wzsew5fbmhjp2vnx4zqzyh8gymce
    fingerprint   : 700cc773f3a3d8bdc4d15b1200daf243b3088515cde36b32ab5cee82a03e20b7
    fileCount     : 4
    publicationStatus: pending

Batas kesabaran yang disepakati: tunggu ~24 jam. Kalau masih beku, ini urusan **moderator** - jangan kirim versi
kelima. `clawhub scan --update` dan `clawhub unhide` sudah dibuktikan TIDAK bisa membuka stall ini.

## Cara memeriksa keadaan rilis tanpa dashboard

`clawhub skill verify <slug>` menjawab `403 Skill is hidden by moderation (<reason>)` selama rilis
pending - itu laporan keadaan, bukan kegagalan. Jendela yang benar-benar bisa dibaca:

- `clawhub inspect <slug>` - satu-satunya tempat `Moderate` / `Reason` / `Mod Time` / `Engine` /
  `Mod Note` terlihat saat skill masih tersembunyi.
- `clawhub scan download <slug> --version <ver>` - bekerja saat pending; di situ terlihat pemindai mana
  yang sudah jalan (`null` = belum jalan, bukan "lulus").
- Setelah tayang: `GET /api/v1/skills/<slug>` -> `displayName`, `latestVersion`, dan
  `security.scannerReports`. Halaman HTML `clawhub.ai/<owner>/skills/<slug>` dirender di klien, jadi
  jangan dipakai sebagai bukti.
- CLI ClawHub tidak punya konsep "skill berbayar" (`grep -rni 'paid|price|pricing'` di paket CLI-nya =
  nol hasil), jadi rilis yang tersangkut bukan soal klasifikasi monetisasi.
