# Great Zimbabwe (reconstruction target — data not yet acquired)

Great Zimbabwe is an extensive ruined city in southeastern Zimbabwe (Masvingo Province), comprising the Great Enclosure and Hill Complex — monumental dry-stone ruins of a medieval Shona state capital (c. 11th–15th centuries). It is a UNESCO World Heritage Site and a prime candidate for digital heritage reconstruction via photogrammetry and structure-from-motion.

This directory is a **placeholder** awaiting acquisition of survey data. No imagery, LiDAR, or terrestrial scans are currently staged on disk.

## Candidate data sources

The following sources are known to hold or have published Great Zimbabwe heritage documentation. Licensing and access terms must be confirmed before download.

### Zamani Project (University of Cape Town)

The Zamani Project (University of Cape Town) maintains the **African Cultural Heritage Sites and Landscapes Database** and is known to have laser-scanned Great Zimbabwe as part of their systematic documentation of Southern African heritage. Access and re-use licensing must be confirmed with UCT.

### Open Heritage 3D

Open Heritage 3D (`https://openheritage3d.org`) publishes structured heritage documentation under various licences (typically CC-BY-NC-SA or similar). Great Zimbabwe may be present in their catalogue; check their project list and confirm the licence terms before acquisition.

### CyArk

CyArk (Cyberarchaeology) has documented UNESCO sites globally. They may hold Great Zimbabwe survey data; check their project list and licensing (typically CC-BY-NC-SA, non-commercial share-alike).

## Acquisition plan / next steps

1. **Source identification:** Contact or search the Zamani Project, Open Heritage 3D, and CyArk to confirm which source(s) hold Great Zimbabwe data and in what format (e57 LiDAR, aerial JPGs, terrestrial photos, etc.).

2. **License confirmation:** Verify that the source's licence permits download and local archival under this project's terms (see repository-root `attributions.md`). Note any restrictions (non-commercial, share-alike, attribution requirements).

3. **Data download:** Once a source is confirmed, download the dataset to `$GL_STORAGE_ROOT/sites/great-zimbabwe/raw/<component>/` (mirroring the Kilwa layout: `raw/lidar_terrestrial/`, `raw/photogrammetry_aerial/`, etc.).

4. **Manifest update:** Write a real `manifest.toml` following the Kilwa template (`../great-mosque-kilwa/manifest.toml`), documenting:
   - Site metadata: name, monument, coordinates, UNESCO status.
   - Dataset tables: title, provider, DOI, URL, licence, collection date.
   - Component tables: file counts, formats, sensors, point counts, extents, registered/colour flags.
   - Acquisition metadata: storage paths, zip sources, integrity checks (CRC, XML validation, e57 page-aware read notes if applicable).
   - Next steps for reconstruction (COLMAP, gsplat, e57 downsampling).

5. **README refresh:** Update this file to document the source, download date, and any data-specific notes (e.g., E57 page-alignment gotchas, geotag coverage, camera metadata).

Once data is acquired and manifest is complete, the site is ready for COLMAP reconstruction via `examples/m1_reconstruct.py` or `examples/m1_bucketed.py` under the memory-guarded cage.
