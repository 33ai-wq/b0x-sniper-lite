# Publish record: x402-market-recon (ClawHub)

Folder yang dipublish (isi repo ini): `dist/clawhub/x402-market-recon/`

    SKILL.md                        instruksi + tabel permission untuk agent lain
    scripts/recon_x402_market.py    census / probe / manifest, hanya stdlib, read-only
    references/decision-rules.md    ambang + arti tiap temuan
    references/findings-baseline.md snapshot ekosistem bertanggal

Tidak ada kunci, token, atau kredensial di dalam paket. Artefak ini memang tidak punya
jalur pembayaran: mengukur itu tugasnya, membayar bukan.

## Perintah publish (metadata katalog ikut, per-versi)

```
cd /home/ubuntu/staging/clawhub
clawhub skill publish ./x402-market-recon --slug x402-market-recon \
  --name "X402 Market Recon" --version <x.y.z> \
  --categories research,development \
  --topics x402,market-research,discovery,evidence,agents \
  --source-repo https://github.com/33ai-wq/b0x-sniper-lite \
  --source-commit <sha commit paket ini> \
  --source-path dist/clawhub/x402-market-recon \
  --changelog "<alasan versi ini>" --json --dry-run
```

Urutannya: commit + push paket ini dulu, baru publish dengan `--source-commit` sha tersebut.

## Keadaan yang sudah terbukti (1.0.2, 16 Okt 2026)

- `clawhub skill verify x402-market-recon --json` -> `decision: pass`, `reasons: []`
- `security.status: clean`, `verdict: benign`, `confidence: high`, tanpa finding
- kartu skill tersedia: `skill-card.md` sha256 `870e6c1401a859f4185f7d6a919350bc19a42e781319c84b59603cbcc01db0a8`
- halaman skill menampilkan kategori **Research Development** dan topik
  `#x402 #market-research #discovery #evidence` (sebelum 1.0.2: kategori **Other**, tanpa chip topik)
- judul di kartu **masih slug** `x402-market-recon`: `--name` dikirim dan diterima receipt publish,
  tetapi record publik tidak ikut berubah (dicek lewat `GET /api/v1/skills/x402-market-recon`).
  Judul tampilan tampaknya hanya ditetapkan saat skill dibuat, jadi mengubahnya perlu UI pemilik.

Catatan: `--dry-run` tidak memvalidasi slug kategori (publish sungguhan yang memvalidasi, ~1 percobaan/menit),
dan setelah publish `verify` sempat `fail / [card.missing]` sekitar 3-4 menit selagi kartu digenerate.
