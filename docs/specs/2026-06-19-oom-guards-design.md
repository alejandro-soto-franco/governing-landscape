# OOM guards for the reconstruction pipeline — design

Date: 2026-06-19
Status: approved (brainstorm), implementation in progress on `feature/oom-guards`

## Problem

Running `examples/m1_reconstruct.py` (pycolmap SfM) on the Great Mosque of Kilwa
datasets keeps OOM-ing. Root cause is hardware, not a bug: this box has **30 GiB
RAM** (≈7.6 GiB free at idle, 22 GiB used) and **47 GiB swap (already 8.6 GiB
deep)**, an RTX 5060 Laptop (8 GB VRAM), and COLMAP runs **CPU-bound** (the GPU
"needs a driver reload"). The pipeline has **no memory guards at all**: no cgroup,
no `ulimit`, no pre-flight check, no image-count caps, and it can run exhaustive
O(N²) matching on hundreds of images. When it overruns, the **global** OOM-killer
fires and the machine thrashes 47 GiB of swap on the way down.

Only the smallest aerial block (`GTM_AGR_03`, 26 images) has reconstructed so far.

## Data on disk (verified 2026-06-19, under `GL_STORAGE_ROOT=/mnt/ASF-EX2/governing-landscape`)

- **Great Mosque of Kilwa** (`sites/great-mosque-kilwa`): 410 aerial JPGs (3.4 GB,
  uppercase `.JPG`) in 6 blocks — `GTM_AGR_01`(89), `_02`(89), `_03`(26),
  `_04`(46), `_05`(75), `GTM_AOR_01`(85); 1,529 terrestrial JPGs (15 GB); and a
  13.3 GB / 673 M-point intensity-only e57 LiDAR (`GRM_Great_Mosque_2018_12.e57`).
- **Great Zimbabwe**: **no data anywhere** (searched both disks by name + Zamani/
  Masvingo/OH3D aliases + all `.e57/.laz/.las`). Scaffold is placeholder-only.

## Decisions (from brainstorm)

1. **Memory contract:** default a **16 GiB co-tenant cage** per caged job; provide
   `--exclusive` (~24 GiB) for the rare all-blocks-at-once run. No blanket cargo
   blocking — small builds coexist; only a big-workspace full rebuild needs a lean
   profile or deferral (out of scope for this work).
2. **Merge strategy:** per-block reconstruction, checkpointed; M1 ships N
   independent sparse models. Cross-block fusion is deferred to M2 SE(3) alignment.
3. **e57:** page-aware streaming, voxel-grid downsample to one PLY (bounded memory).
4. **Great Zimbabwe:** placeholder site dir + manifest + acquisition-plan README.

## Mechanism: cage via self-re-exec under `systemd-run --user --scope`

pycolmap runs **in-process**, so we cage by re-exec'ing the whole Python process
under a transient cgroup-v2 scope (verified working without root on this Fedora 44
box: `systemd-run --user --scope -p MemoryMax=… true` → OK).

`MemorySwapMax` is the load-bearing line: capping swap turns an overrun into a
**clean, in-cgroup OOM-kill** instead of a global-killer roulette across 47 GiB of
swap. Mandatory: if `systemd-run` is unavailable we **refuse**, we do not fall back
to `RLIMIT_AS` (it miscounts COLMAP's mmap'd DB and breaks it).

## Components & interface contracts

### `examples/_memcage.py` (NEW) — the guard core

```python
# Budgets (GiB strings for systemd -p flags)
#   default : MemoryMax=16G  MemoryHigh=14G  MemorySwapMax=2G   required floor 16
#   exclusive: MemoryMax=24G MemoryHigh=22G MemorySwapMax=4G    required floor 24
GL_CAGED_ENV = "GL_CAGED"   # sentinel set on the re-exec'd child to avoid re-exec loop

def cage_budget(exclusive: bool) -> dict:
    "Return {'max','high','swap_max','required_gib'} for the chosen tier."

def mem_available_gib(meminfo_text: str | None = None) -> float:
    "Parse MemAvailable from /proc/meminfo (or the passed text, for tests)."

def have_systemd_run() -> bool: ...

def build_caged_argv(inner_argv: list[str], budget: dict, *, label: str) -> list[str]:
    "['systemd-run','--user','--scope','--quiet','--collect',
      '-p','MemoryAccounting=yes','-p',f'MemoryMax={max}','-p',f'MemoryHigh={high}',
      '-p',f'MemorySwapMax={swap_max}','--', *inner_argv]  (pure, unit-tested)"

def preflight(exclusive: bool) -> None:
    "Print the budget; SystemExit with a clear hint if mem_available_gib() < floor."

def reexec_caged_if_needed(exclusive: bool, *, label: str) -> None:
    "No-op if os.environ[GL_CAGED] set. Else: require systemd-run (SystemExit if
     missing), preflight(), then os.execvp the same argv wrapped by build_caged_argv,
     with GL_CAGED=1 added to the env."

@contextlib.contextmanager
def single_instance_lock(lock_path: str):
    "fcntl.flock LOCK_EX|LOCK_NB; SystemExit('another job holds the lock') if held."
```

Unit tests (`examples/tests/test_memcage.py`): `mem_available_gib` on sample text;
`cage_budget` values for both tiers; `build_caged_argv` contains the right `-p`
flags and order; `preflight` refuses when injected available < floor; `single_instance_lock`
raises on a held lock.

### `examples/m1_reconstruct.py` (EDIT) — wire the cage + SIFT caps

- Add args: `--cage/--no-cage` (default **on**), `--exclusive`,
  `--max-image-size` (default 3200), `--max-num-features` (default 8192).
- At the **start of the COLMAP stage**, before any pycolmap call:
  `if args.cage: _memcage.reexec_caged_if_needed(args.exclusive, label=f"colmap:{site}:{bucket}")`.
- Pass the caps into `pycolmap.extract_features` via its SIFT options (agent picks
  the exact pycolmap 4.x API). Keep all existing behaviour otherwise.
- Leave the gsplat stage untouched.

### `examples/m1_bucketed.py` (NEW) — per-block orchestrator

- CLI: `--site` (default great-mosque-kilwa), `--source` (default
  photogrammetry_aerial), `--blocks GTM_AGR_01,…` (default: auto-discover by
  stripping the trailing `_<digits>.<ext>` from filenames), `--exclusive`,
  `--matcher` (default sequential), `--max-image-size`, `--max-num-features`,
  `--root`.
- Hold a `single_instance_lock` for the whole run.
- For each block: run `uv run python examples/m1_reconstruct.py --stage colmap
  --site … --source … --subset <block> --matcher … --exclusive?` as a **subprocess**
  (it self-cages). Capture returncode + stdout tail.
- **Crash-safe:** a block that fails/OOMs is recorded and **skipped**; completed
  blocks survive. Write/update `…/colmap/_bucketed_status.json`:
  `{block: {status: ok|failed|skipped, returncode, n_reg_images?, n_points?, note}}`.
- **Guard:** refuse `--matcher exhaustive` for any block with > 80 images (print why).
- Print a summary table at the end.

### `examples/e57_to_ply.py` (NEW) — streaming LiDAR downsampler

- CLI: `<input.e57> --out <out.ply> [--voxel 0.05] [--max-points N]
  [--exclusive] [--no-cage]`.
- `reexec_caged_if_needed` unless `--no-cage`.
- Guard `import pye57` (SystemExit with `uv pip install 'governing-landscape[lidar]'`
  hint, mirroring the existing pycolmap pattern). Add a `[project.optional-dependencies]
  lidar = ["pye57>=0.4"]` extra to `crates/governing-landscape-py/pyproject.toml`.
- Read **scan-by-scan** (`E57.scan_count`, `read_scan_raw(i)`) — page-aware via
  pye57 (do NOT read the file as one flat block; see the manifest's E57 page/CRC
  gotcha). Voxel-quantize coords incrementally (dict keyed by floored
  `(x,y,z)/voxel`, keep one point per voxel) → memory bounded by occupied voxels,
  not the 673 M input. Log per-scan progress.
- Write one PLY (binary little-endian): `x,y,z` float + `intensity` as a uint8 gray
  channel (e57 is intensity-only, no RGB).
- Factor a pure `voxel_downsample(points: np.ndarray, voxel: float) -> np.ndarray`
  for unit testing on synthetic arrays.

Unit test (`examples/tests/test_e57_to_ply.py`): `voxel_downsample` collapses many
points sharing a voxel to one, preserves distinct-voxel points, is order-independent.

### `data/sites/great-zimbabwe/` (NEW, data only)

- `manifest.toml` mirroring Kilwa's shape: `[site]` name="Great Zimbabwe",
  monument, country="Zimbabwe", region="Masvingo Province", lat≈-20.2674,
  lon≈30.9336, status="UNESCO World Heritage Site",
  role="reconstruction target (data not yet acquired)";
  `[dataset] status = "awaiting data acquisition"`.
- `README.md`: candidate sources (Zamani Project / UCT African Cultural Heritage,
  Open Heritage 3D, CyArk), licensing caveats, and the acquisition plan / next steps.
  No code wiring.

## Cross-cutting

- **Scratch:** COLMAP db/temp stay under `GL_STORAGE_ROOT`; SIFT `TMPDIR` should be
  a real SSD scratch, never `/tmp` (tmpfs). Scripts warn if `TMPDIR` is on tmpfs.
- **Type-check** all Python with `uvc`. Follow uv-only tooling (no bare pip).
- **No `Date.now()`-style nondeterminism needed**; status JSON omits timestamps.

## Testing summary

- Unit: `_memcage` (budgets, argv, preflight, lock), `voxel_downsample`.
- Integration smoke: run `m1_bucketed.py --site great-mosque-kilwa --blocks
  GTM_AGR_03` (26 imgs, known-good) end to end under the cage; assert a sparse model
  and a status entry are produced. (Full-site / e57 runs are manual, hardware-bound.)
