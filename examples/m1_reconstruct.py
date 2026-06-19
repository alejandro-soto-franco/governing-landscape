#!/usr/bin/env python3
"""Milestone-1 reconstruction pipeline: COLMAP SfM + gsplat training.

Stages (run independently):

    --stage colmap   produce sparse cameras + point cloud from a site's photos
    --stage gsplat   initialise a 3D-GS scene from the sparse cloud, train, export .ply

Image sources (per site, see --source):

    wikimedia             phased manifest.json (per-image pre_quake/post_quake),
                          staged by --phase. Used by moulay-brahim.
    photogrammetry_aerial flat directory of geotagged JPGs (single epoch),
                          optionally narrowed by --subset (filename prefix).
                          Used by great-mosque-kilwa.

Inputs:
    $GL_STORAGE_ROOT/sites/<site>/raw/<source>/...

Outputs:
    $GL_STORAGE_ROOT/sites/<site>/colmap/<bucket>/sparse/0/
    $GL_STORAGE_ROOT/sites/<site>/gsplat/<bucket>/scene.ply

  where <bucket> is the --phase (phased sources) or the --subset / "all"
  (flat sources).

Prereqs:
    --stage colmap : pip install governing-landscape[sfm]   (pycolmap)
    --stage gsplat : pip install governing-landscape[splat] (torch + gsplat) + CUDA GPU

Matching: aerial strips are ordered and geotagged, so --matcher sequential
(default for the aerial source) is far cheaper than exhaustive; --matcher
spatial uses the EXIF GPS priors. Small phased sets default to exhaustive.

A dedicated bucket is processed per run; the 4D keyframe coupling and the §3.3
SE(3) rigid alignment between keyframes land in a follow-up M2 script.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Robust import of the sibling _memcage module whether this file is run as a
# script (``python examples/m1_reconstruct.py``) or imported as part of a
# package. When run as a script the script's own directory is on sys.path[0],
# but be defensive and ensure it is present.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import _memcage  # type: ignore[import-not-found]  # noqa: E402 — stdlib-only sibling

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def default_storage_root() -> Path:
    return Path(os.environ.get("GL_STORAGE_ROOT", "/mnt/ASF-EX2/governing-landscape"))


def detect_source(root: Path, site: str) -> str:
    """Pick a source for the site if --source was not given."""
    site_raw = root / "sites" / site / "raw"
    if (site_raw / "wikimedia" / "manifest.json").exists():
        return "wikimedia"
    if (site_raw / "photogrammetry_aerial").is_dir():
        return "photogrammetry_aerial"
    sys.exit(
        f"could not detect an image source under {site_raw}; "
        f"pass --source explicitly"
    )


def select_images(
    raw: Path, *, phase: str | None, subset: str | None
) -> tuple[list[str], str]:
    """Return (image filenames, output bucket name) for a source directory.

    Phased manifest source: filter manifest.json by `phase`.
    Flat source: glob image files, optionally keep those whose name starts
    with `subset`.
    """
    manifest_path = raw / "manifest.json"
    if manifest_path.exists():
        if not phase:
            sys.exit(f"{manifest_path} is phased; pass --phase pre_quake|post_quake")
        manifest = json.loads(manifest_path.read_text())
        names = [f["filename"] for f in manifest["files"] if f["phase"] == phase]
        if not names:
            sys.exit(f"no images with phase={phase!r} in {manifest_path}")
        return names, phase

    names = sorted(
        p.name for p in raw.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    if not names:
        sys.exit(f"no image files ({sorted(IMAGE_EXTS)}) under {raw}")
    if subset:
        names = [n for n in names if n.startswith(subset)]
        if not names:
            sys.exit(f"no images with prefix {subset!r} under {raw}")
    return names, (subset or "all")


def stage_image_dir(
    root: Path, site: str, source: str, *, phase: str | None, subset: str | None
) -> tuple[Path, str]:
    """Symlink-tree of the selected images, suitable for COLMAP."""
    raw = root / "sites" / site / "raw" / source
    if not raw.is_dir():
        sys.exit(f"missing source dir {raw}")
    names, bucket = select_images(raw, phase=phase, subset=subset)

    staged = root / "sites" / site / "colmap" / bucket / "images"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir(parents=True)
    n = 0
    for name in names:
        src = raw / name
        if not src.exists():
            print(f"  ! missing {src}, skipping", file=sys.stderr)
            continue
        (staged / name).symlink_to(src)
        n += 1
    print(f"staged {n} images ({source}/{bucket}) at {staged}")
    return staged, bucket


def resolve_device(name: str):
    import pycolmap  # type: ignore[import-not-found]

    return {
        "auto": pycolmap.Device.auto,
        "cpu": pycolmap.Device.cpu,
        "cuda": pycolmap.Device.cuda,
    }[name]


def run_match(db_path: Path, matcher: str, device) -> None:
    import pycolmap  # type: ignore[import-not-found]

    if matcher == "exhaustive":
        print("colmap: matching features (exhaustive)")
        pycolmap.match_exhaustive(db_path, device=device)
    elif matcher == "sequential":
        print("colmap: matching features (sequential)")
        pycolmap.match_sequential(db_path, device=device)
    elif matcher == "spatial":
        print("colmap: matching features (spatial, GPS priors)")
        pycolmap.match_spatial(db_path, device=device)
    else:
        sys.exit(f"unknown matcher {matcher!r}")


def build_sift_options(max_image_size: int, max_num_features: int):
    """Construct pycolmap SIFT extraction options with the requested caps.

    Returns ``None`` if the installed pycolmap does not expose the expected
    options type, so the caller can fall back to the library defaults rather
    than crash the existing extraction path.

    NOTE: pycolmap 4.x exposes SIFT caps via ``pycolmap.SiftExtractionOptions``
    with ``max_image_size`` / ``max_num_features`` fields, passed to
    ``extract_features`` as the ``sift_options=`` keyword. This is the assumed
    API — verify against the installed pycolmap on the reconstruction hardware
    (pycolmap is not installed in this dev env, so it could not be probed).
    """
    import pycolmap  # type: ignore[import-not-found]

    opts_cls = getattr(pycolmap, "SiftExtractionOptions", None)
    if opts_cls is None:
        print(
            "  ! pycolmap.SiftExtractionOptions unavailable; "
            "using library default SIFT caps",
            file=sys.stderr,
        )
        return None
    opts = opts_cls()
    try:
        opts.max_image_size = max_image_size
        opts.max_num_features = max_num_features
    except (AttributeError, TypeError) as exc:  # pragma: no cover - API drift guard
        print(
            f"  ! could not set SIFT caps on {opts_cls.__name__}: {exc}; "
            "using library defaults",
            file=sys.stderr,
        )
        return None
    return opts


def run_colmap(
    root: Path,
    site: str,
    source: str,
    *,
    phase: str | None,
    subset: str | None,
    matcher: str,
    device_name: str,
    max_image_size: int,
    max_num_features: int,
) -> Path:
    try:
        import pycolmap  # type: ignore[import-not-found]
    except ImportError:
        sys.exit("pycolmap not installed. Run: uv pip install 'governing-landscape[sfm]'")

    device = resolve_device(device_name)
    images, bucket = stage_image_dir(root, site, source, phase=phase, subset=subset)
    out = root / "sites" / site / "colmap" / bucket
    db_path = out / "database.db"
    sparse_dir = out / "sparse"

    if db_path.exists():
        db_path.unlink()
    if sparse_dir.exists():
        shutil.rmtree(sparse_dir)
    sparse_dir.mkdir(parents=True)

    print(
        f"colmap: extracting features from {images} (device={device_name}, "
        f"max_image_size={max_image_size}, max_num_features={max_num_features})"
    )
    sift_options = build_sift_options(max_image_size, max_num_features)
    if sift_options is not None:
        pycolmap.extract_features(
            db_path, images, device=device, sift_options=sift_options
        )
    else:
        pycolmap.extract_features(db_path, images, device=device)
    run_match(db_path, matcher, device)
    print("colmap: incremental mapping")
    maps = pycolmap.incremental_mapping(db_path, images, sparse_dir)
    if not maps:
        sys.exit(
            "incremental mapping produced no reconstruction; "
            "the input set may not have enough overlap. "
            "Try a denser --subset, or --matcher exhaustive on a small set."
        )
    n = len(maps)
    print(f"colmap: {n} reconstruction(s) at {sparse_dir}")
    for i, rec in maps.items():
        print(
            f"  rec {i}: {rec.num_reg_images()} registered images, "
            f"{rec.num_points3D()} 3D points"
        )
    return sparse_dir


def run_gsplat(root: Path, site: str, bucket: str, n_iters: int) -> Path:
    try:
        import torch  # type: ignore[import-not-found]
        import gsplat  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        sys.exit(
            "torch / gsplat not installed. "
            "Run: uv pip install 'governing-landscape[splat]'"
        )
    if not torch.cuda.is_available():
        sys.exit("gsplat training requires CUDA; no GPU detected")

    sparse = root / "sites" / site / "colmap" / bucket / "sparse" / "0"
    if not sparse.exists():
        sys.exit(f"no COLMAP reconstruction at {sparse}; run --stage colmap first")

    out = root / "sites" / site / "gsplat" / bucket
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
    ap.add_argument(
        "--source",
        choices=["wikimedia", "photogrammetry_aerial"],
        help="image source under raw/ (auto-detected if omitted)",
    )
    ap.add_argument(
        "--phase",
        choices=["pre_quake", "post_quake"],
        help="bucket for phased sources (wikimedia)",
    )
    ap.add_argument(
        "--subset",
        help="filename prefix to narrow a flat source, e.g. GTM_AGR_03 (the bucket name)",
    )
    ap.add_argument(
        "--matcher",
        choices=["exhaustive", "sequential", "spatial"],
        help="feature matcher (default: exhaustive for wikimedia, sequential otherwise)",
    )
    ap.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="compute device for SIFT extract/match (GPU currently needs a driver reload)",
    )
    ap.add_argument("--n-iters", type=int, default=1000, help="gsplat training iterations")
    ap.add_argument("--root", type=Path, default=default_storage_root())
    ap.add_argument(
        "--cage",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="run the COLMAP stage inside a systemd-run memory cage (default: on). "
        "Use --no-cage to disable (e.g. when already caged externally).",
    )
    ap.add_argument(
        "--exclusive",
        action="store_true",
        help="use the exclusive (24 GiB) cage tier instead of the default 16 GiB co-tenant tier",
    )
    ap.add_argument(
        "--max-image-size",
        type=int,
        default=3200,
        help="SIFT: downscale images so the larger side is at most this many px (default 3200)",
    )
    ap.add_argument(
        "--max-num-features",
        type=int,
        default=8192,
        help="SIFT: maximum number of features per image (default 8192)",
    )
    args = ap.parse_args()

    source = args.source or detect_source(args.root, args.site)
    matcher = args.matcher or ("exhaustive" if source == "wikimedia" else "sequential")

    if args.stage == "colmap":
        # Cage the COLMAP stage (pycolmap runs in-process) by re-exec'ing the
        # whole process under a cgroup-v2 scope BEFORE importing/using pycolmap.
        # This call never returns on success (the cage child takes over); when
        # already caged (GL_CAGED set) it is a no-op and we fall through.
        if args.cage:
            bucket = args.phase or args.subset or "all"
            _memcage.reexec_caged_if_needed(
                args.exclusive, label=f"colmap:{args.site}:{bucket}"
            )
        run_colmap(
            args.root,
            args.site,
            source,
            phase=args.phase,
            subset=args.subset,
            matcher=matcher,
            device_name=args.device,
            max_image_size=args.max_image_size,
            max_num_features=args.max_num_features,
        )
    elif args.stage == "gsplat":
        bucket = args.phase or args.subset or "all"
        run_gsplat(args.root, args.site, bucket, args.n_iters)


if __name__ == "__main__":
    main()
