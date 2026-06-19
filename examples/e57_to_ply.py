#!/usr/bin/env python3
"""Streaming e57 → PLY converter with voxel-grid downsampling.

Reads an E57 LiDAR file scan-by-scan (page/CRC-aware via pye57), voxel-quantizes
coordinates incrementally to bound memory, then writes a single binary-little-endian
PLY with float x/y/z + uchar intensity.

Usage:
    e57_to_ply.py <input.e57> --out <out.ply> [--voxel 0.05] [--max-points N]
                  [--exclusive] [--no-cage]
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

# Make `from _memcage import ...` work whether invoked as a script from repo root
# or from within the examples/ directory.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


import numpy as np


# ---------------------------------------------------------------------------
# Pure, importable downsampling function (unit-tested without pye57)
# ---------------------------------------------------------------------------

def voxel_downsample(points: np.ndarray, voxel: float) -> np.ndarray:
    """Voxel-grid downsample an Nx3 or Nx4 (xyz[+intensity]) point array.

    One representative point is kept per occupied voxel (first-encounter wins).
    Returns an Mx3 or Mx4 array matching the input column count.

    Args:
        points: float array of shape (N, 3) or (N, 4).  Column order: x, y, z[, intensity].
        voxel:  edge length of each voxel cube (same units as xyz).

    Returns:
        Downsampled array of shape (M, ncols) where M <= N.
    """
    if points.ndim != 2 or points.shape[1] not in (3, 4):
        raise ValueError(f"points must be Nx3 or Nx4, got shape {points.shape}")
    if voxel <= 0:
        raise ValueError(f"voxel must be > 0, got {voxel}")

    inv = 1.0 / voxel
    keys = np.floor(points[:, :3] * inv).astype(np.int64)

    seen: dict[tuple[int, int, int], int] = {}
    kept: list[int] = []
    for idx in range(len(keys)):
        k = (int(keys[idx, 0]), int(keys[idx, 1]), int(keys[idx, 2]))
        if k not in seen:
            seen[k] = idx
            kept.append(idx)

    return points[np.array(kept, dtype=np.int64)]


# ---------------------------------------------------------------------------
# Incremental merge helper used by the streaming path
# ---------------------------------------------------------------------------

def _merge_chunk_into(
    voxel_map: dict[tuple[int, int, int], tuple[float, float, float, float]],
    chunk: np.ndarray,
    voxel: float,
    max_points: int | None,
) -> bool:
    """Insert chunk points into voxel_map; return True if max_points was hit."""
    inv = 1.0 / voxel
    for row in chunk:
        x, y, z = float(row[0]), float(row[1]), float(row[2])
        intensity = float(row[3]) if chunk.shape[1] >= 4 else 0.0
        k = (math.floor(x * inv), math.floor(y * inv), math.floor(z * inv))
        if k not in voxel_map:
            voxel_map[k] = (x, y, z, intensity)
            if max_points is not None and len(voxel_map) >= max_points:
                return True
    return False


# ---------------------------------------------------------------------------
# PLY writer (binary little-endian, no heavy deps)
# ---------------------------------------------------------------------------

def write_ply(path: Path, points: list[tuple[float, float, float, float]]) -> None:
    """Write a binary little-endian PLY with properties float x,y,z + uchar intensity."""
    n = len(points)
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {n}\n"
        "property float x\n"
        "property float y\n"
        "property float z\n"
        "property uchar intensity\n"
        "end_header\n"
    )
    row_fmt = struct.Struct("<fffB")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        buf = bytearray(row_fmt.size * n)
        offset = 0
        for x, y, z, intensity in points:
            # Clamp and scale intensity: e57 raw values are typically 0–1 floats
            # or 0–65535 uint16; normalise to 0–255.
            raw = float(intensity)
            if raw <= 1.0:
                gray = int(round(raw * 255.0))
            else:
                gray = int(round(raw / 65535.0 * 255.0))
            gray = max(0, min(255, gray))
            row_fmt.pack_into(buf, offset, float(x), float(y), float(z), gray)
            offset += row_fmt.size
        fh.write(buf)


# ---------------------------------------------------------------------------
# Streaming conversion entrypoint
# ---------------------------------------------------------------------------

def convert(
    input_path: Path,
    out_path: Path,
    *,
    voxel: float,
    max_points: int | None,
) -> None:
    """Stream-read e57 scan-by-scan, voxel-downsample incrementally, write PLY."""
    try:
        import pye57  # type: ignore[import-untyped]
    except ImportError:
        sys.exit("pye57 not installed. Run: uv pip install 'governing-landscape[lidar]'")

    e57 = pye57.E57(str(input_path))
    scan_count = e57.scan_count
    print(f"e57: {input_path.name}  {scan_count} scans", file=sys.stderr)

    voxel_map: dict[tuple[int, int, int], tuple[float, float, float, float]] = {}
    capped = False

    for i in range(scan_count):
        raw = e57.read_scan_raw(i)

        # Extract xyz arrays — key names follow the ASTM E57 spec
        try:
            xs = np.asarray(raw["cartesianX"], dtype=np.float64)
            ys = np.asarray(raw["cartesianY"], dtype=np.float64)
            zs = np.asarray(raw["cartesianZ"], dtype=np.float64)
        except KeyError as exc:
            print(f"  scan {i}: missing coordinate field {exc}, skipping", file=sys.stderr)
            continue

        n_pts = len(xs)
        if n_pts == 0:
            print(f"  scan {i}: 0 points, skipping", file=sys.stderr)
            continue

        # Intensity is optional in the spec; default to 0 if absent
        if "intensity" in raw:
            intensity_arr = np.asarray(raw["intensity"], dtype=np.float64)
        else:
            intensity_arr = np.zeros(n_pts, dtype=np.float64)

        chunk = np.column_stack([xs, ys, zs, intensity_arr])
        capped = _merge_chunk_into(voxel_map, chunk, voxel, max_points)

        print(
            f"  scan {i+1}/{scan_count}: {n_pts:,} pts read  →  {len(voxel_map):,} voxels kept",
            file=sys.stderr,
        )
        if capped:
            print(
                f"  --max-points {max_points} reached after scan {i+1}; stopping early",
                file=sys.stderr,
            )
            break

    kept = list(voxel_map.values())
    print(
        f"e57: writing {len(kept):,} points to {out_path}",
        file=sys.stderr,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_ply(out_path, kept)
    print("done.", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Stream an E57 LiDAR file through voxel downsampling and write a PLY.",
    )
    ap.add_argument("input", type=Path, help="Input .e57 file")
    ap.add_argument("--out", type=Path, required=True, help="Output .ply path")
    ap.add_argument(
        "--voxel",
        type=float,
        default=0.05,
        help="Voxel edge length in metres (default: 0.05)",
    )
    ap.add_argument(
        "--max-points",
        type=int,
        default=None,
        metavar="N",
        help="Stop after keeping N voxel representatives (hard memory cap)",
    )
    ap.add_argument(
        "--exclusive",
        action="store_true",
        help="Request the exclusive cgroup budget (~24 GiB) instead of co-tenant (~16 GiB)",
    )
    ap.add_argument(
        "--no-cage",
        action="store_true",
        help="Skip the systemd memory cage (not recommended for large files)",
    )
    args = ap.parse_args()

    if not args.no_cage:
        from _memcage import reexec_caged_if_needed  # type: ignore[import-not-found]
        reexec_caged_if_needed(
            args.exclusive,
            label=f"e57_to_ply:{args.input.name}",
        )

    if not args.input.exists():
        sys.exit(f"input file not found: {args.input}")

    convert(
        args.input,
        args.out,
        voxel=args.voxel,
        max_points=args.max_points,
    )


if __name__ == "__main__":
    main()
