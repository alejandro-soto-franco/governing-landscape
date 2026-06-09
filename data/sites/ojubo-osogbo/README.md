# Ojúbo Òsogbo, Osun-Osogbo Sacred Grove (reference dataset)

A dense heritage capture of Ojúbo Òsogbo, the shrines and sculptures of the
Osun-Osogbo Sacred Grove at Osogbo, Osun State, Nigeria (UNESCO World Heritage
Site, inscribed 2005), by CyArk with ímísí3D, distributed through Open Heritage
3D under `https://doi.org/10.26301/wr06-mh92`. Aerial imagery captured 21 to 22
September 2019.

This is a second methodological reference alongside the Great Mosque at Kilwa
Kisiwani: a properly overlapping terrestrial-LiDAR plus aerial- and
terrestrial-photogrammetry survey of a living cultural landscape, which
bootstraps the COLMAP to gsplat pipeline (Layers III and IV) on real survey
data. It sits outside the Al-Haouz earthquake scope.

## What is here

Tracked in git: this `README.md` and `manifest.toml` only. The binaries live
under `$GL_STORAGE_ROOT/sites/ojubo-osogbo/` (default
`/mnt/ASF-EX2/governing-landscape/sites/ojubo-osogbo/`):

```
raw/photogrammetry_aerial/AOR_{01,02,03}_*.jpg        1010 files, 12.5 GiB   [extracted]
raw/lidar_terrestrial/OSU_Ojubo_Osogbo_Cyclone.e57    48.7 GiB e57           [extracted]
raw/photogrammetry_terrestrial/{PEX,PIN}_*_*.jpg      2793 files, 30.4 GiB   [extracted]
```

### Aerial photogrammetry

- 1010 DJI Phantom 4 Pro photos (EXIF camera `FC6310`), 5464 x 3640.
- Captured 21 to 22 September 2019.
- Three aerial oblique runs by filename prefix: `AOR_01` (319), `AOR_02` (33),
  and `AOR_03` (658).
- 810 of 1010 photos are geotagged; 200 carry a null (0,0) GPS tag, so scale
  and georeference lean on the terrestrial LiDAR.

The extraction is faithful: 1010 JPGs at 13,472,558,882 bytes on disk against a
13,471,457,162-byte published zip (JPGs barely compress), with readable EXIF
across sampled blocks.

### Terrestrial LiDAR

- ASTM E57 v1.0, registered in Leica Cyclone, 82 scans sharing one local frame.
- 2,312,404,068 points total (~28.2 M per scan).
- Per-point fields: cartesianX/Y/Z, intensity, **colorRed/Green/Blue**,
  rowIndex, columnIndex, cartesianInvalidState. This e57 carries per-point RGB,
  unlike the intensity-only Faro scan at great-mosque-kilwa.
- Scan-0 local extent roughly 149 x 161 x 42 m; registered 2019-09-27.

The file reads cleanly through `pye57` (which is page-aware): the typed E57 root
parses, all 82 scan headers resolve, and the point counts sum as above. The E57
page-CRC read gotcha documented for great-mosque-kilwa applies if the binary or
XML regions are read as a flat block; use `pye57` / `libE57Format`.

### Terrestrial photogrammetry

- 2793 photos from two cameras: Nikon D5600 (1187) and Fujifilm X-T2 (1606),
  24 MP (6000 x 4000; 3 frames portrait).
- Captured 24 August to 22 September 2019. None geotagged (terrestrial), so
  scale and georeference lean on the LiDAR.
- Ten runs by filename prefix: five exterior (`PEX_01..05`, 757 photos) and five
  interior (`PIN_01..05`, 2036 photos).

## Setup

The zips were extracted with `7z x -aos` (idempotent; the OH3D zips are Zip64,
which Info-ZIP `unzip 6.00` cannot read but `7z` handles) into the storage root:

```bash
SITE=/mnt/ASF-EX2/governing-landscape/sites/ojubo-osogbo
7z x -aos wr06-mh92_photogrammetry_aerial.zip      -o"$SITE/raw/photogrammetry_aerial"
7z x -aos wr06-mh92_lidar_terrestrial.zip          -o"$SITE/raw/lidar_terrestrial"
7z x -aos wr06-mh92_photogrammetry_terrestrial.zip -o"$SITE/raw/photogrammetry_terrestrial"
```

## Attribution

CC BY-NC-SA (non-commercial). The required citation and provider details are in
the repository-root `attributions.md`. Cite CyArk, ímísí3D, and Open Heritage 3D
in any work that uses this dataset, and do not redistribute the binaries.
