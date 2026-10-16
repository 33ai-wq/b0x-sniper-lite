# Publish record: x402-market-recon (ClawHub)

Folder yang dipublish (isi repo ini): `dist/clawhub/x402-market-recon/`

    SKILL.md                        instruksi + tabel permission untuk agent lain
    scripts/recon_x402_market.py    census / probe / manifest, hanya stdlib, read-only
    references/decision-rules.md    ambang + arti tiap temuan
    references/findings-baseline.md snapshot ekosistem bertanggal
    agents/openai.yaml              display_name yang ditampilkan ClawHub (ditambah di 1.0.3)

Tidak ada kunci, token, atau kredensial di dalam paket. Artefak ini memang tidak punya
jalur pembayaran: mengukur itu tugasnya, membayar bukan.

## Perintah publish (metadata katalog ikut, per-versi)

```
cd /home/ubuntu/prpo_ai/dist/clawhub
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

## Judul tampilan: bagaimana ClawHub sebenarnya menentukannya (dibaca dari sumber openclaw/clawhub)

`convex/lib/skillPresentation.ts` -> `resolveSkillPresentation()` menentukan nama yang tampil, berurutan:

1. `publisherDisplayName` = `--name` yang DIKIRIM SAAT PUBLISH, tetapi hanya dipakai kalau nilainya
   BERBEDA dari dua kandidat turunan (lihat jebakan di bawah).
2. `agents/openai.yaml` -> `interface.display_name` (maks 120 karakter, emoji dibuang).
3. `name:` di frontmatter SKILL.md (skill ini: `x402-market-recon`, huruf kecil apa adanya).
4. `titleizeSlug(slug)` -> "X402 Market Recon".

`convex/lib/skillPublish.ts` baris 305-316: kalau `--name` sama dengan frontmatter `name:` ATAU sama
dengan hasil titleize slug, maka nilai itu dianggap "turunan" dan DIBUANG (`publisherDisplayName =
undefined`) - penyebab kenapa publish 1.0.2 dengan `--name "X402 Market Recon"` tidak mengubah apa pun:
namanya sama dengan titleize slug, jadi yang menang justru frontmatter `name:` (slug mentah).

Tidak ada jalur dashboard: `convex/skills.ts` hanya mengekspos mutation `updateSummary`,
`setCatalogMetadata` (kategori/topik), `updateTags`, `renameOwnedSkill` (slug + redirect), `merge`.
Tidak ada mutation untuk display name, dan API v1 tidak punya route metadata (PATCH/PUT/POST 404).

Perbaikan yang dipakai (terukur): tambah `agents/openai.yaml` -> rank 2, di atas frontmatter name.

## Keadaan yang sudah terbukti (1.0.2, 16 Okt 2026)

- `clawhub skill verify x402-market-recon --json` -> `decision: pass`, `reasons: []`
- `security.status: clean`, `verdict: benign`, `confidence: high`, tanpa finding
- kartu skill tersedia: `skill-card.md` sha256 `870e6c1401a859f4185f7d6a919350bc19a42e781319c84b59603cbcc01db0a8`
- halaman skill menampilkan kategori **Research Development** dan topik
  `#x402 #market-research #discovery #evidence` (sebelum 1.0.2: kategori **Other**, tanpa chip topik)

## 1.0.3 - nama tampilan diperbaiki (16 Okt 2026)

- Yang diubah: `agents/openai.yaml` (`interface.display_name: "x402 Market Recon"`). Tidak ada perubahan kode.
- Publish: versionId `k975pdcwvh93r97355bn7t1gyx8gdfp0`, attemptId `zx73b62xeqdt54hzr96rmn0bcd8gdv48`,
  fingerprint `a9a4215b04ea5d57582c542c3206d6a8f8e077f793c5a27e96da49dda6cd8048`, fileCount 5.
- Sumber: commit `b9974c1` (sudah di push; `ls-remote origin main` = HEAD lokal).
- Hasil terukur: `GET /api/v1/skills/x402-market-recon` -> `displayName: "x402 Market Recon"`,
  `tags.latest: 1.0.3`; `clawhub inspect x402-market-recon` -> `x402-market-recon  X402 Market Recon`.
  Namanya sekarang identik dengan kartu Agent Skill di xhagents.xyz. `verify` -> `ok: true`,
  `security.status: clean`, kartu ada.

Catatan: `--dry-run` tidak memvalidasi slug kategori (publish sungguhan yang memvalidasi, ~1 percobaan/menit),
dan setelah publish `verify` sempat `fail / [card.missing]` sekitar 3-4 menit selagi kartu digenerate.
