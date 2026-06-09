# Great Mosque, Kilwa Kisiwani (reference dataset)

A dense heritage capture of the Great Mosque at Kilwa Kisiwani, Tanzania
(UNESCO World Heritage Site), by CyArk, distributed through Open Heritage 3D
under `https://doi.org/10.26301/bfzm-v295`. Collected 11 to 19 December 2018.

This is not an Al-Haouz earthquake site. It serves as a methodological
reference: a properly overlapping terrestrial-LiDAR plus aerial-photogrammetry
survey that bootstraps the COLMAP to gsplat pipeline (Layers III and IV) on
real survey data, where the Moulay Brahim Wikimedia photos could not (see
`docs/audits/2026-05-06-colmap-on-wikimedia-fails.md`).

## What is here

Tracked in git: this `README.md` and `manifest.toml` only. The binaries live
under `$GL_STORAGE_ROOT/sites/great-mosque-kilwa/` (default
`/mnt/ASF-EX2/governing-landscape/sites/great-mosque-kilwa/`):

```
raw/lidar_terrestrial/GRM_Great_Mosque_2018_12.e57       12.4 GiB
raw/photogrammetry_aerial/GTM_{AGR,AOR}_*.JPG            410 files, 3.4 GiB
raw/photogrammetry_terrestrial/GTM_{PEX,PIN}_*_*.JPG     1529 photos, 14.4 GiB
```

### Terrestrial LiDAR

- ASTM E57 v1.0, Faro Focus S350, 61 registered scans sharing one local frame.
- 673,191,640 points total (~11.03 M per scan).
- Per-point fields: cartesianX/Y/Z, intensity, rowIndex, columnIndex. Intensity
  only, no per-point colour.
- Local extent roughly 274 x 279 x 20 m.

The file is bit-intact: 8/8 sampled E57 page CRC-32C checks pass across the
full 12.4 GiB, and the XML parses strictly with all 124 binary offsets numeric.
Read gotcha: E57 stores 1024-byte physical pages (1020 payload bytes plus a
4-byte big-endian CRC-32C), and the offsets are physical. Reading the XML as one
flat block sweeps up the per-page CRC bytes, which look like ~0.19% scattered
"corruption" (they land only at page offsets 1020 to 1023). Read page-aware, or
just use `pye57` / `libE57Format`, which handle pages and CRCs correctly.

### Aerial photogrammetry

- 410 DJI Phantom 4 Pro photos (EXIF camera `FC2103`; the OH3D page labels the
  platform "DJI Mavic Pro"), 4056 x 3040, all geotagged.
- Captured 2018-12-18 over a 22-minute window, ~21 m above the structure.
- Six flight blocks: five nadir grid strips (`GTM_AGR_01..05`, 325 photos) and
  one oblique orbit (`GTM_AOR_01`, 85 photos).

### Terrestrial photogrammetry

- 1529 ground-level photos from two cameras: Apple iPhone X (1126, geotagged,
  4032 x 3024) and Nikon D810 (405, 36 MP, 7360 x 4912).
- Captured 2018-12-17 over roughly two hours. The iPhone frames carry GPS.
- Seven runs by filename prefix: four exterior (`GTM_PEX_01..04`, 247 photos)
  and three interior (`GTM_PIN_01..03`, 1282 photos).
- The archive also holds 2 short `.MOV` clips and 1 `.AAE` Apple edit sidecar
  under `GTM_PIN_03`; these are incidental and not part of the photo set.

This component supplies per-image colour, where the terrestrial LiDAR e57 is
intensity-only.

## Setup

The lidar + aerial zips were extracted with `unzip -n` (idempotent). The
terrestrial photogrammetry zip is Zip64, which Info-ZIP `unzip 6.00` cannot
read, so it was extracted with `7z x -aos` (idempotent):

```bash
SITE=/mnt/ASF-EX2/governing-landscape/sites/great-mosque-kilwa
unzip -n bfzm-v295_photogrammetry_aerial.zip      -d "$SITE/raw"
unzip -n bfzm-v295_lidar_terrestrial.zip          -d "$SITE/raw"
7z x -aos bfzm-v295_photogrammetry_terrestrial.zip -o"$SITE/raw"   # lands raw/photogrammetry_terrestrial/
```

## Attribution

CC BY-NC-SA (non-commercial). The required citation and provider details are in
the repository-root `attributions.md`. Cite CyArk and Open Heritage 3D in any
work that uses this dataset, and do not redistribute the binaries.
