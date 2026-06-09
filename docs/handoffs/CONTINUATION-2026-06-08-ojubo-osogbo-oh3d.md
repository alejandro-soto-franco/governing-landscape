# Continuation: Ojúbo Òsogbo site + OH3D terrestrial downloads

> **COMPLETED 2026-06-09.** All three downloads finished, extracted, surveyed,
> and written into the manifests/READMEs (Ojúbo all three components; Kilwa
> terrestrial photogrammetry added). Zips deleted (~63 GiB reclaimed), the
> `oh3d-downloads.service` retired and removed, sentinels/lock cleared. Repo
> left UNCOMMITTED for review. The steps below are kept as the record of what
> was done. Survey results landed in each site's `manifest.toml`.

Date: 2026-06-08. Author handoff before a context clear. Everything below is durable on disk.

## Goal

Add **Ojúbo Òsogbo** (Osun-Osogbo Sacred Grove, Nigeria; CyArk / ímísí3D / Open
Heritage 3D, DOI `10.26301/wr06-mh92`) as a **methodological reference dataset**,
mirroring `great-mosque-kilwa` (decided by the user). Also complete Kilwa by
fetching its terrestrial-photogrammetry component.

## Durable download state (runs WITHOUT any Claude session)

A user systemd service downloads the three missing zips and auto-resumes:

- Service: `oh3d-downloads.service` (`~/.config/systemd/user/`), enabled, `Linger=yes`.
  - `systemctl --user status oh3d-downloads` — watch it.
  - Runner: `/mnt/ASF-EX2/governing-landscape/_incoming/resume-downloads.sh`
    (flock single-instance; loops `aria2c -c` until done; then `touch DOWNLOADS_COMPLETE`).
  - aria2 input: `_incoming/aria2.in`; source links: `_incoming/oh3d_links.txt`
    (IP-tagged to 107.206.152.104 but server does NOT enforce; this box pulls fine).
  - **Links expire 2026-06-10 21:21 UTC.** If they lapse, Hamza re-requests from OH3D.
  - Logs: `_incoming/aria2.log`, `_incoming/resume.log`.
- Live TUI for the user: `bash _incoming/watch-downloads.sh` (du-based, non-invasive).
- Completion sentinel: `_incoming/DOWNLOADS_COMPLETE` appears when all three finish.

Downloading into `/mnt/ASF-EX2/governing-landscape/_incoming/` (EX2 had 546 GB free):

| zip | size | target site/component |
|---|---|---|
| `wr06-mh92_lidar_terrestrial.zip` | 20.09 GiB | ojubo-osogbo / lidar_terrestrial |
| `bfzm-v295_photogrammetry_terrestrial.zip` | 12.75 GiB | great-mosque-kilwa / photogrammetry_terrestrial |
| `wr06-mh92_photogrammetry_terrestrial.zip` | 30.37 GiB | ojubo-osogbo / photogrammetry_terrestrial |

## Already done

- **Ojúbo aerial** verified complete and FILED: `sites/ojubo-osogbo/raw/photogrammetry_aerial/`
  (1010 JPGs, 12.5 GiB; DJI FC6310 5464x3640; blocks AOR_01=319, AOR_02=33, AOR_03=658;
  captured 2019-09-21..22; 200/1010 have null (0,0) GPS).
- Repo scaffolding (uncommitted, reference-dataset framing, British English):
  - `data/sites/ojubo-osogbo/manifest.toml` + `README.md` (aerial surveyed; lidar +
    terrestrial-photogrammetry sections STUBBED with known zip sizes, pending extraction).
  - `attributions.md` — CyArk / ímísí3D citation block added.

## Remaining steps (do after DOWNLOADS_COMPLETE exists)

1. Sanity-check each zip (`unzip -t` or trust aria2 + Content-Length already matched).
2. Extract (idempotent `unzip -n`):
   - `wr06-mh92_lidar_terrestrial.zip` -> `sites/ojubo-osogbo/raw/lidar_terrestrial/`
   - `wr06-mh92_photogrammetry_terrestrial.zip` -> `sites/ojubo-osogbo/raw/photogrammetry_terrestrial/`
   - `bfzm-v295_photogrammetry_terrestrial.zip` -> `sites/great-mosque-kilwa/raw/photogrammetry_terrestrial/`
3. Survey each (counts, byte sizes, camera/resolution for photos; for any `.e57`
   honour the **E57 page-CRC read gotcha**: 1024-byte physical pages = 1020 payload +
   4-byte big-endian CRC-32C; read page-aware or use pye57/libE57Format).
4. Fill the stubbed sections in `ojubo-osogbo/manifest.toml` (lidar_terrestrial,
   photogrammetry_terrestrial), move them into `components_local`, update
   `[acquisition].status` and `[acquisition.integrity]`. Update `ojubo-osogbo/README.md`.
5. Update `great-mosque-kilwa/manifest.toml`: add `photogrammetry_terrestrial` to
   `components_local` (it currently lists only lidar_terrestrial + photogrammetry_aerial
   and calls terrestrial photogrammetry "not set up; Nikon D810 ~12.75 GB"); flip that
   and survey it. Update the Kilwa README's "What is here" block.
6. Reclaim space: once extraction is verified, the zips in `_incoming/` can be deleted
   (~63 GiB). Then retire the downloader:
   `systemctl --user disable --now oh3d-downloads.service` and
   `rm -f _incoming/DOWNLOADS_COMPLETE _incoming/.resume.lock`.
7. Leave the repo UNCOMMITTED for the user to review (their instruction), unless asked.

## Notes / gotchas

- gov-landscape binaries live on **ASF-EX2**, not EX1. Repo `target/` is a symlink
  (cargo-targets convention) — never make a real `target/` dir.
- aria2 writes sparse files: `du -B1 <file>` = real bytes; `ls` apparent size is misleading.
- The background task `brg4hb899` "failed exit 7" in the prior session was an intentional
  SIGTERM when re-anchoring aria2c to systemd; not a real error.
