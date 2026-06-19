#!/usr/bin/env python3
"""Per-block COLMAP orchestrator for the Great Mosque of Kilwa aerial set.

Reconstructs each photogrammetry block as an independent sparse model by
invoking ``m1_reconstruct.py --stage colmap --subset <block>`` as a SEPARATE
subprocess. Each subprocess self-cages (re-exec under a systemd-run cgroup
scope), so the OOM risk is bounded per block.

Design goals (see docs/specs/2026-06-19-oom-guards-design.md):

  * Crash-safe: a block that fails or gets OOM-killed is recorded and the loop
    CONTINUES to the next block. A JSON checkpoint is updated after each block
    so re-runs skip already-ok blocks (use --force to redo them).
  * Single-instance: the whole run holds one flock; concurrent runs refuse.
  * Exhaustive guard: refuse O(N^2) exhaustive matching on blocks > 80 images
    (the OOM risk this work guards against) — that block is skipped.

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Robust import of the sibling _memcage module (single_instance_lock) whether
# this file is run as a script or imported.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import _memcage  # type: ignore[import-not-found]  # noqa: E402 — stdlib-only sibling

# Same flat-source image extensions m1_reconstruct recognises, for auto-discovery.
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# Match a trailing "_<digits>.<ext>" so e.g. "GTM_AGR_01_0042.JPG" -> "GTM_AGR_01".
_TRAILING_INDEX = re.compile(r"_\d+\.[^.]+$")

# Blocks larger than this are unsafe for exhaustive (O(N^2)) matching.
EXHAUSTIVE_MAX_IMAGES = 80

# Parse e.g. "  rec 0: 89 registered images, 12345 3D points"
_REC_LINE = re.compile(
    r"\brec\s+\d+:\s+(\d+)\s+registered images,\s+(\d+)\s+3D points"
)


def default_storage_root() -> Path:
    return Path(os.environ.get("GL_STORAGE_ROOT", "/mnt/ASF-EX2/governing-landscape"))


def raw_source_dir(root: Path, site: str, source: str) -> Path:
    return root / "sites" / site / "raw" / source


def discover_blocks(raw: Path) -> list[str]:
    """Auto-discover block prefixes from the raw image filenames.

    Strips a trailing ``_<digits>.<ext>`` from each image filename and returns
    the sorted unique prefixes.
    """
    if not raw.is_dir():
        sys.exit(f"missing source dir {raw}")
    blocks: set[str] = set()
    for p in raw.iterdir():
        if p.suffix.lower() not in IMAGE_EXTS:
            continue
        prefix = _TRAILING_INDEX.sub("", p.name)
        if prefix and prefix != p.name:
            blocks.add(prefix)
    if not blocks:
        sys.exit(
            f"could not auto-discover blocks under {raw} "
            f"(no files matching '<prefix>_<digits>.<ext>'); pass --blocks"
        )
    return sorted(blocks)


def count_block_images(raw: Path, block: str) -> int:
    """Count raw images whose filename starts with the block prefix."""
    return sum(
        1
        for p in raw.iterdir()
        if p.suffix.lower() in IMAGE_EXTS and p.name.startswith(block)
    )


def status_path(root: Path, site: str) -> Path:
    return root / "sites" / site / "colmap" / "_bucketed_status.json"


def load_status(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  ! could not read status file {path}: {exc}; starting fresh",
              file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_status(path: Path, status: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic, no timestamps (per spec).
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")


def parse_counts(stdout: str) -> tuple[int | None, int | None]:
    """Extract the best (largest registered-image) rec counts from stdout.

    m1_reconstruct prints one "rec i: N registered images, M 3D points" line per
    reconstruction; pick the one with the most registered images.
    """
    best: tuple[int, int] | None = None
    for m in _REC_LINE.finditer(stdout):
        n_reg = int(m.group(1))
        n_pts = int(m.group(2))
        if best is None or n_reg > best[0]:
            best = (n_reg, n_pts)
    if best is None:
        return None, None
    return best


def build_subprocess_argv(
    *,
    site: str,
    source: str,
    block: str,
    matcher: str,
    max_image_size: int,
    max_num_features: int,
    num_threads: int,
    exclusive: bool,
    root: Path,
    min_free_gib: float | None = None,
) -> list[str]:
    # Invoke m1_reconstruct.py with THIS interpreter (sys.executable) and an
    # absolute path, NOT `uv run python …`. That propagates the orchestrator's
    # own environment (e.g. the venv that has pycolmap) to the per-block child
    # AND keeps it consistent with _memcage's `[sys.executable, *sys.argv]`
    # cage re-exec; a fresh `uv run` would resolve an env without pycolmap.
    argv = [
        sys.executable, str(_HERE / "m1_reconstruct.py"),
        "--stage", "colmap",
        "--site", site,
        "--source", source,
        "--subset", block,
        "--matcher", matcher,
        "--max-image-size", str(max_image_size),
        "--max-num-features", str(max_num_features),
        "--num-threads", str(num_threads),
        "--root", str(root),
    ]
    if exclusive:
        argv.append("--exclusive")
    if min_free_gib is not None:
        argv += ["--min-free-gib", str(min_free_gib)]
    return argv


def run_block(
    block: str,
    *,
    site: str,
    source: str,
    matcher: str,
    max_image_size: int,
    max_num_features: int,
    num_threads: int,
    exclusive: bool,
    root: Path,
    min_free_gib: float | None = None,
) -> dict[str, object]:
    """Run one block as a self-caging subprocess; return its status record."""
    argv = build_subprocess_argv(
        site=site,
        source=source,
        block=block,
        matcher=matcher,
        max_image_size=max_image_size,
        max_num_features=max_num_features,
        num_threads=num_threads,
        exclusive=exclusive,
        root=root,
        min_free_gib=min_free_gib,
    )
    print(f"\n=== block {block}: {' '.join(argv)}")
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv,
        cwd=str(_HERE.parent),
        capture_output=True,
        text=True,
    )
    # Echo the child's output so the operator sees progress / errors.
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    n_reg, n_pts = parse_counts(proc.stdout)
    if proc.returncode == 0:
        return {
            "status": "ok",
            "returncode": proc.returncode,
            "n_reg_images": n_reg,
            "n_points": n_pts,
            "note": "reconstructed",
        }
    # Nonzero: failed or OOM-killed. A SIGKILL (OOM) surfaces as -9 / 137.
    oom = proc.returncode in (-9, 137)
    note = "OOM-killed (in-cage)" if oom else "subprocess returned nonzero"
    return {
        "status": "failed",
        "returncode": proc.returncode,
        "n_reg_images": n_reg,
        "n_points": n_pts,
        "note": note,
    }


def print_summary(blocks: list[str], status: dict[str, dict[str, object]]) -> None:
    print("\n" + "=" * 64)
    print(f"{'block':<16} {'status':<8} {'reg imgs':>9} {'points':>10}")
    print("-" * 64)
    for block in blocks:
        rec = status.get(block, {})
        st = str(rec.get("status", "—"))
        ri = rec.get("n_reg_images")
        pts = rec.get("n_points")
        ri_s = str(ri) if ri is not None else "—"
        pts_s = str(pts) if pts is not None else "—"
        print(f"{block:<16} {st:<8} {ri_s:>9} {pts_s:>10}")
    print("=" * 64)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", default="great-mosque-kilwa")
    ap.add_argument("--source", default="photogrammetry_aerial")
    ap.add_argument(
        "--blocks",
        help="comma-separated block prefixes "
        "(default: auto-discover from raw filenames)",
    )
    ap.add_argument("--exclusive", action="store_true",
                    help="use the exclusive (24 GiB) cage tier in each subprocess")
    ap.add_argument(
        "--matcher",
        choices=["exhaustive", "sequential", "spatial"],
        default="sequential",
        help="feature matcher passed to each block (default sequential)",
    )
    ap.add_argument("--max-image-size", type=int, default=3200)
    ap.add_argument("--max-num-features", type=int, default=8192)
    ap.add_argument("--num-threads", type=int, default=8,
                    help="SIFT extraction threads per block (default 8; -1 = all cores)")
    ap.add_argument("--min-free-gib", type=float, default=None,
                    help="conscious override of each block's cage preflight start gate "
                         "(GiB); for small/validation blocks on a busy box")
    ap.add_argument("--root", type=Path, default=default_storage_root())
    ap.add_argument(
        "--force",
        action="store_true",
        help="re-run blocks already marked ok in the status file",
    )
    args = ap.parse_args()

    raw = raw_source_dir(args.root, args.site, args.source)

    if args.blocks:
        blocks = [b.strip() for b in args.blocks.split(",") if b.strip()]
    else:
        blocks = discover_blocks(raw)
    print(f"blocks ({len(blocks)}): {', '.join(blocks)}")

    st_path = status_path(args.root, args.site)
    status = load_status(st_path)
    # Ensure the colmap dir exists before we try to lock inside it.
    st_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = st_path.parent / ".bucketed.lock"

    with _memcage.single_instance_lock(str(lock_path)):
        for block in blocks:
            prior = status.get(block)
            if (
                not args.force
                and isinstance(prior, dict)
                and prior.get("status") == "ok"
            ):
                print(f"\n=== block {block}: already ok, skipping (use --force to redo)")
                continue

            n_imgs = count_block_images(raw, block)
            if args.matcher == "exhaustive" and n_imgs > EXHAUSTIVE_MAX_IMAGES:
                note = (
                    f"refused exhaustive matcher on {n_imgs} images "
                    f"(> {EXHAUSTIVE_MAX_IMAGES}); exhaustive is O(N^2) and is the "
                    f"OOM risk this orchestrator guards against — use --matcher "
                    f"sequential or spatial for this block"
                )
                print(f"\n=== block {block}: SKIP — {note}", file=sys.stderr)
                status[block] = {
                    "status": "skipped",
                    "returncode": 0,
                    "n_reg_images": None,
                    "n_points": None,
                    "note": note,
                }
                save_status(st_path, status)
                continue

            record = run_block(
                block,
                site=args.site,
                source=args.source,
                matcher=args.matcher,
                max_image_size=args.max_image_size,
                max_num_features=args.max_num_features,
                num_threads=args.num_threads,
                exclusive=args.exclusive,
                root=args.root,
                min_free_gib=args.min_free_gib,
            )
            status[block] = record
            # Checkpoint after EACH block so a crash/OOM preserves prior progress.
            save_status(st_path, status)
            print(
                f"=== block {block}: {record['status']} "
                f"(rc={record['returncode']}, "
                f"reg={record['n_reg_images']}, pts={record['n_points']})"
            )

    print_summary(blocks, status)


if __name__ == "__main__":
    main()
