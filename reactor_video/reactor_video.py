#!/usr/bin/env python3
"""
reactor_video.py — Reactor.inc photo->video prototype (Fase 1, Arah A)
Turns product photo(s) into a short motion video MP4 via
H3 Reference Turbo Realtime (queue-based, klip diskrit 5-15 dtk).

MODEL: reactor/h3-reference-to-video-turbo-realtime  (70 cred/s)
  - PER SEMUA kategori produk (X2 di-drop; helios/fast-h3 disimpan utk nanti).
  - BERBASIS QUEUE (bukan set_prompt+start): enqueue(prompt+references) -> clip_generated -> play.
  - Klip diskrit ~5-15 detik (predictable biaya), 0-9 ref image, output main_video+main_audio.
  - CATATAN: nama command/params H3 (enqueue/play/references) adalah asumsi dari round3 Claude;
    schema per-model resmi di-gate. Jika server menolak saat uji, sesuaikan di sini (biaya uji kecil,
    hard-cap tetap menjaga).

KRITIS (update2/round3): bill per-detik selama SESSION terbuka. WAJIB 3-lapis hard-stop:
  1. Reactor(max_session_duration_seconds=N)  — cap keras server.
  2. asyncio.wait_for(runner(), timeout=N)      — timeout keras client.
  3. finally: await reactor.disconnect()         — selalu stop billing.

Simpan hasil: SDK built-in recording -> MPEG-TS (.ts) -> remux ffmpeg -c copy menjadi .mp4
(lossless, cepat) — JANGAN buffer-frame manual + rawvideo (sudah nggak perlu).

Requirements: reactor-sdk (di /home/ubuntu/prpo_ai/venv).
Usage:
  source /home/ubuntu/.reactor_key_env
  /home/ubuntu/prpo_ai/venv/bin/python reactor_video.py <image1.jpg> [image2.jpg ...] [--seconds 6] [--out out.ts]
  # prompt: --prompt atau env REACTOR_PROMPT; default menyebut background+lighting eksplisit.
"""
import argparse
import asyncio
import os
import subprocess
from pathlib import Path

from reactor_sdk import Reactor

MODEL = os.environ.get("REACTOR_MODEL", "h3-reference-to-video-turbo-realtime")
HARD_TIMEOUT_SECONDS = float(os.environ.get("REACTOR_HARD_TIMEOUT", 45))
OUT_DIR = Path(os.environ.get("REACTOR_OUT_DIR", "/home/ubuntu/prpo_ai/reactor_video/out"))

DEFAULT_PROMPT = (
    "cozy bright living room, warm lighting, product rotates slowly, "
    "fabric sways gently, cinematic, sharp detail, studio quality"
)


def get_api_key():
    k = os.environ.get("REACTOR_API_KEY", "")
    if not k:
        raise RuntimeError("REACTOR_API_KEY not set (source ~/.reactor_key_env)")
    return k


def save_as_mp4(ts_path: Path, mp4_path: Path) -> Path:
    """Remux .ts -> .mp4 lossless (fast)."""
    if not ts_path.exists():
        raise RuntimeError(f".ts not found: {ts_path}")
    if mp4_path.exists():
        return mp4_path
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(ts_path), "-c", "copy", str(mp4_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg remux failed: {r.stderr[-400:]}")
    return mp4_path


async def generate(refs: list[Path], out_ts: Path, prompt: str, seconds: float) -> Path:
    key = get_api_key()
    print(f"[reactor] model={MODEL} refs={len(refs)} target_clip={seconds}s hardcap={HARD_TIMEOUT_SECONDS}s")
    reactor = Reactor(
        model_name=MODEL,
        api_key=key,
        max_session_duration_seconds=int(HARD_TIMEOUT_SECONDS),  # hard-stop #1
    )

    async def runner():
        try:
            await reactor.connect()
            print("[reactor] connected:", reactor.get_status())

            # Upload reference images (SDK upload_file -> FileRef). H3 supports 0-9.
            file_refs = []
            for r in refs:
                fr = await reactor.upload_file(r, name="reference")
                file_refs.append(fr)
                print("[reactor] upload ok:", fr)

            # Queue a clip: prompt + references via protocol command (H3 mode queue).
            # Asumsi round3 — verifikasi saat uji jalur (cost kecil, hard-cap aman).
            await reactor.send_command("enqueue", {
                "prompt": prompt,
                "references": [fr.upload_id for fr in file_refs],  # or FileRef objects
            })
            await reactor.send_command("play", {})

            # Tunggu durasi target, lalu simpan klip via SDK built-in -> .ts
            await asyncio.sleep(max(seconds, 3.0))
            await reactor.download_clip(seconds, path=str(out_ts))
            print("[reactor] clip saved:", out_ts)
        finally:
            # hard-stop #3
            try:
                await reactor.disconnect()
                print("[reactor] disconnected (billing stopped)")
            except Exception as e:
                print("[reactor] disconnect err:", e)

    # hard-stop #2
    try:
        await asyncio.wait_for(runner(), timeout=HARD_TIMEOUT_SECONDS + 5)
    except asyncio.TimeoutError:
        print("[reactor] TIMEOUT - force disconnect")
        try:
            await reactor.disconnect()
        except Exception:
            pass
        raise
    return out_ts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", help="1+ reference image path(s)")
    ap.add_argument("--seconds", type=float, default=float(os.environ.get("REACTOR_TARGET_SECONDS", 6)))
    ap.add_argument("--out", default=None, help="output .ts path (default: out/<firstimg>_reactor.ts)")
    ap.add_argument("--prompt", default=os.environ.get("REACTOR_PROMPT", DEFAULT_PROMPT))
    args = ap.parse_args()

    refs = [Path(x) for x in args.images]
    for r in refs:
        if not r.exists():
            print(f"ERROR: image not found: {r}")
            raise SystemExit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_ts = Path(args.out) if args.out else OUT_DIR / f"{refs[0].stem}_reactor.ts"
    out_ts.parent.mkdir(parents=True, exist_ok=True)
    asyncio.run(generate(refs, out_ts, args.prompt, args.seconds))  # llama .ts
    print("DONE .ts:", out_ts)


if __name__ == "__main__":
    main()