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
