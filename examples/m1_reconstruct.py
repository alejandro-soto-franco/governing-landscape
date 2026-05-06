#!/usr/bin/env python3
"""Milestone-1 reconstruction pipeline: COLMAP SfM + gsplat training.

Stages (run independently):

    --stage colmap   produce sparse cameras + point cloud from the curated photos
    --stage gsplat   initialise a 3D-GS scene from the sparse cloud, train, export .ply

Inputs:
    $GL_STORAGE_ROOT/sites/<site>/raw/wikimedia/manifest.json
    $GL_STORAGE_ROOT/sites/<site>/raw/wikimedia/*.jpg

Outputs:
    $GL_STORAGE_ROOT/sites/<site>/colmap/<phase>/sparse/0/
    $GL_STORAGE_ROOT/sites/<site>/gsplat/<phase>/scene.ply

Prereqs:
    --stage colmap : pip install governing-landscape[sfm]   (pycolmap)
    --stage gsplat : pip install governing-landscape[splat] (torch + gsplat) + CUDA GPU

A dedicated phase ("pre_quake" or "post_quake") is processed per run; the 4D
keyframe coupling and the §3.3 SE(3) rigid alignment between keyframes
land in a follow-up M2 script.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


def default_storage_root() -> Path:
    return Path(os.environ.get("GL_STORAGE_ROOT", "/mnt/ASF-EX2/governing-landscape"))


def stage_image_dir(root: Path, site: str, phase: str) -> Path:
    """Symlink-tree of just the {phase} images, suitable for COLMAP."""
    raw = root / "sites" / site / "raw" / "wikimedia"
    manifest_path = raw / "manifest.json"
    if not manifest_path.exists():
        sys.exit(f"missing {manifest_path}; run scripts/fetch_moulay_brahim.py first")
    manifest = json.loads(manifest_path.read_text())
    files = [f for f in manifest["files"] if f["phase"] == phase]
    if not files:
        sys.exit(f"no images with phase={phase!r} in {manifest_path}")

    staged = root / "sites" / site / "colmap" / phase / "images"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    for f in files:
        src = raw / f["filename"]
        if not src.exists():
            print(f"  ! missing {src}, skipping", file=sys.stderr)
            continue
        (staged / f["filename"]).symlink_to(src)
    print(f"staged {len(files)} {phase} images at {staged}")
    return staged


def run_colmap(root: Path, site: str, phase: str) -> Path:
    try:
        import pycolmap
    except ImportError:
        sys.exit(
            "pycolmap not installed. "
            "Run: uv pip install 'governing-landscape[sfm]'"
        )

    images = stage_image_dir(root, site, phase)
    out = root / "sites" / site / "colmap" / phase
    db_path = out / "database.db"
    sparse_dir = out / "sparse"

    if db_path.exists():
        db_path.unlink()
    if sparse_dir.exists():
        shutil.rmtree(sparse_dir)
    sparse_dir.mkdir(parents=True)

    print(f"colmap: extracting features from {images}")
    pycolmap.extract_features(db_path, images)
    print("colmap: matching features (exhaustive)")
    pycolmap.match_exhaustive(db_path)
    print("colmap: incremental mapping")
    maps = pycolmap.incremental_mapping(db_path, images, sparse_dir)
    if not maps:
        sys.exit(
            "incremental mapping produced no reconstruction; "
            "the input set may not have enough overlap. "
            "Try: pre-curate the photo set to a sub-cluster around the mosque/main square."
        )
    n = len(maps)
    print(f"colmap: {n} reconstruction(s) at {sparse_dir}")
    for i, rec in maps.items():
        print(
            f"  rec {i}: {rec.num_reg_images()} registered images, "
            f"{rec.num_points3D()} 3D points"
        )
    return sparse_dir


def run_gsplat(root: Path, site: str, phase: str, n_iters: int) -> Path:
    try:
        import torch
        import gsplat  # noqa: F401
    except ImportError:
        sys.exit(
            "torch / gsplat not installed. "
            "Run: uv pip install 'governing-landscape[splat]'"
        )
    if not torch.cuda.is_available():
        sys.exit("gsplat training requires CUDA; no GPU detected")

    sparse = root / "sites" / site / "colmap" / phase / "sparse" / "0"
    if not sparse.exists():
        sys.exit(f"no COLMAP reconstruction at {sparse}; run --stage colmap first")

    out = root / "sites" / site / "gsplat" / phase
    out.mkdir(parents=True, exist_ok=True)

    # TODO(M1.5): full gsplat training loop.
    #
    # Outline:
    #   1. Read COLMAP cameras + images + points3D from `sparse/`.
    #   2. Initialise per-Gaussian state:
    #        means       <- points3D xyz
    #        colours     <- points3D rgb / 255
    #        opacities   <- 0.1 (constant init)
    #        scales      <- log of mean-knn-distance per point
    #        quats       <- identity
    #   3. Build a torch.optim.Adam over those tensors with the gsplat-recommended
    #      per-parameter LRs (means 1.6e-4, opacity 5e-2, scales 5e-3, quats 1e-3).
    #   4. For each iteration:
    #        - sample a registered camera + its rendered image
    #        - call gsplat.rasterization(...) to produce a rendered RGB
    #        - photometric loss = (1 - lambda_dssim) * L1 + lambda_dssim * (1 - SSIM)
    #        - backprop, step, schedule densify/prune at gsplat's recommended cadence
    #   5. Export .ply via gsplat's write helper, or write our own:
    #      header with x,y,z,nx,ny,nz,red,green,blue,alpha,scale_0..2,rot_0..3.
    raise NotImplementedError(
        f"gsplat training stub. Inputs ready at {sparse}, "
        f"output target {out}. Implementation gated on M1.5 + Hamza's compute."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["colmap", "gsplat"], required=True)
    ap.add_argument("--site", default="moulay-brahim")
    ap.add_argument("--phase", choices=["pre_quake", "post_quake"], required=True)
    ap.add_argument("--n-iters", type=int, default=1000, help="gsplat training iterations")
    ap.add_argument("--root", type=Path, default=default_storage_root())
    args = ap.parse_args()

    if args.stage == "colmap":
        run_colmap(args.root, args.site, args.phase)
    elif args.stage == "gsplat":
        run_gsplat(args.root, args.site, args.phase, args.n_iters)


if __name__ == "__main__":
    main()
