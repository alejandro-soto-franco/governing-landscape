#!/usr/bin/env python3
"""Fetch the Wikimedia Commons `Category:Moulay_Brahim` photo set.

Downloads every file in the category (mixed pre- and post-2023-09-08 quake),
records each file's metadata + sha256 in `manifest.json`, and stores binaries
under `$GL_STORAGE_ROOT/sites/moulay-brahim/raw/wikimedia/`.

Defaults to `GL_STORAGE_ROOT=/mnt/ASF-EX2/governing-landscape`. Idempotent:
re-running skips files whose sha256 already matches the manifest.

No third-party deps; stdlib only. Wikimedia API etiquette:
https://www.mediawiki.org/wiki/API:Etiquette.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "governing-landscape/0.1.0 "
    "(https://github.com/alejandro-soto-franco/governing-landscape; "
    "sotofranco.eng@gmail.com)"
)
QUAKE_DATE = "2023-09-08T00:00:00Z"


def default_storage_root() -> Path:
    return Path(os.environ.get("GL_STORAGE_ROOT", "/mnt/ASF-EX2/governing-landscape"))


def http_get_json(url: str, params: dict, timeout: int = 30) -> dict:
    full = f"{url}?{urlencode(params)}"
    req = Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return resp.read()


def list_category(category: str) -> list[dict]:
    """Return one record per file in the category, with imageinfo metadata."""
    files: list[dict] = []
    cont: dict | None = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": "500",
            "prop": "imageinfo",
            "iiprop": "url|mime|size|timestamp|user|extmetadata",
        }
        if cont:
            params.update(cont)
        data = http_get_json(API_ENDPOINT, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo")
            if not ii:
                continue
            files.append({"title": page["title"], **ii[0]})
        cont = data.get("continue")
        if not cont:
            break
        time.sleep(0.3)
    return files


def keep_image(rec: dict) -> bool:
    mime = rec.get("mime", "")
    return mime.startswith("image/") and not mime.endswith("svg+xml")


def license_short(rec: dict) -> str:
    md = rec.get("extmetadata", {}) or {}
    return (md.get("LicenseShortName") or {}).get("value", "unknown")


def normalize_filename(title: str) -> str:
    base = title.removeprefix("File:").replace(" ", "_")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in base)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def upload_phase(timestamp: str) -> str:
    """`pre_quake`, `post_quake`, or `unknown` based on upload timestamp."""
    if not timestamp:
        return "unknown"
    return "pre_quake" if timestamp < QUAKE_DATE else "post_quake"


def fetch(category: str, root: Path, dry_run: bool) -> None:
    raw_dir = root / "sites" / "moulay-brahim" / "raw" / "wikimedia"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "manifest.json"

    existing: dict[str, dict] = {}
    if manifest_path.exists():
        existing = {e["filename"]: e for e in json.loads(manifest_path.read_text())["files"]}

    print(f"querying {API_ENDPOINT} for Category:{category}")
    records = list_category(category)
    images = [r for r in records if keep_image(r)]
    print(f"{len(records)} entries in category, {len(images)} images after MIME filter")

    out: list[dict] = []
    for i, rec in enumerate(images, 1):
        filename = normalize_filename(rec["title"])
        target = raw_dir / filename
        url = rec["url"]
        ts = rec.get("timestamp", "")
        phase = upload_phase(ts)
        prior = existing.get(filename)

        if target.exists() and prior:
            local_sha = sha256_bytes(target.read_bytes())
            if local_sha == prior["sha256"]:
                print(f"  [{i:>2}/{len(images)}] skip (unchanged): {filename}")
                out.append(prior)
                continue

        if dry_run:
            print(f"  [{i:>2}/{len(images)}] DRY-RUN would fetch: {filename}  ({phase}, {ts})")
            continue

        print(f"  [{i:>2}/{len(images)}] fetch ({phase}): {filename}")
        try:
            blob = http_get_bytes(url)
        except Exception as e:
            print(f"     ! fetch failed: {e}", file=sys.stderr)
            continue
        target.write_bytes(blob)
        out.append(
            {
                "filename": filename,
                "url": url,
                "sha256": sha256_bytes(blob),
                "size_bytes": len(blob),
                "mime": rec.get("mime", ""),
                "uploaded_at": ts,
                "uploader": rec.get("user", ""),
                "license": license_short(rec),
                "phase": phase,
                "wikimedia_title": rec["title"],
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        time.sleep(0.5)

    if dry_run:
        return

    manifest_path.write_text(
        json.dumps(
            {
                "category": f"Category:{category}",
                "n_files": len(out),
                "n_pre_quake": sum(1 for f in out if f["phase"] == "pre_quake"),
                "n_post_quake": sum(1 for f in out if f["phase"] == "post_quake"),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "files": out,
            },
            indent=2,
        )
    )
    print(f"\nwrote {manifest_path}")
    print(
        f"  pre-quake: {sum(1 for f in out if f['phase'] == 'pre_quake')}, "
        f"post-quake: {sum(1 for f in out if f['phase'] == 'post_quake')}, "
        f"unknown: {sum(1 for f in out if f['phase'] == 'unknown')}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--category",
        default="Moulay_Brahim",
        help="Wikimedia Commons category name without the 'Category:' prefix",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=default_storage_root(),
        help="Storage root (default: $GL_STORAGE_ROOT or /mnt/ASF-EX2/governing-landscape)",
    )
    ap.add_argument("--dry-run", action="store_true", help="List files without downloading")
    args = ap.parse_args()
    fetch(args.category, args.root, args.dry_run)


if __name__ == "__main__":
    main()
