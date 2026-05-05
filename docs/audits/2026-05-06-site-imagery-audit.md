# Site imagery audit, Moulay Brahim selected

Date: 2026-05-06
Question: which of {Tafza, Moulay Brahim, Imi N'Tala} is the right milestone-1 target site for the 4D Gaussian Splatting + governance hypergraph reconstruction?

## Decision

**Moulay Brahim.**

It is the only one of the three with non-trivial pre-quake public-internet imagery and post-quake Maxar Open Data AOI coverage. The other two fail one or both axes.

## Findings

| Criterion                          | Tafza               | Moulay Brahim                                          | Imi N'Tala                       |
|-----------------------------------|---------------------|--------------------------------------------------------|----------------------------------|
| Wikimedia Commons pre-quake        | 0 usable            | 26-file category, multi-viewpoint mosque / minaret     | 0 (all 27 hits are post-quake)   |
| Google Street View                 | none                | none                                                   | none                             |
| Mapillary / KartaView              | none                | unconfirmed in this pass                               | none                             |
| Academic photogrammetry pre-quake  | none                | none                                                   | none                             |
| Other pre-quake material           | scattered blogs     | journalism (CNN, Reuters, Le Matin), tourism literature| 2017 trekking blog (small set)   |
| Maxar Open Data AOI                | yes                 | yes                                                    | yes                              |
| Academic post-quake reconnaissance | not named           | StEER PVRR canonical case + Swiss Sci. Rep. 2025      | MDPI Buildings 2024 (no SfM)     |
| Damage magnitude                   | low                 | mosque collapse, partial hotel collapse                | catastrophic, ~70 deaths         |
| SfM tractability from public data  | poor                | marginal-to-good around mosque / main square           | effectively zero                 |

## Why not Imi N'Tala

Imi N'Tala is the most dramatic damage story in the quake (catastrophic loss, total village destruction). It would be the natural narrative choice, but it has zero pre-quake imagery on the public internet at building-detail density. With no t0 baseline, the reconstruction problem is 3D (post-quake state alone) rather than 4D (pre, post, proposed). The whole point of the framework is the temporal triplet, so Imi N'Tala is the wrong site to validate the pipeline on, even if it is the right site to apply the pipeline to once it works.

## Why not Tafza

Tafza is empty on both axes: 1 misindexed Wikimedia hit (which is in Algeria), low damage magnitude, no academic damage product, no journalism cluster. There is nothing to reconstruct that the framework would distinguish from a vanilla NeRF demo.

## What Moulay Brahim gives us, and the caveat

A 26-file Wikimedia Commons category, multi-viewpoint, with a 10-photo MyPic series taken at varied angles around the mosque and minaret. Pre-quake journalism photography from CNN, Reuters, Le Matin. StEER's Preliminary Virtual Reconnaissance Report (Oct 2023) treats Moulay Brahim as a canonical case and includes targeted exterior photos of the minaret and the partial-collapse hotel. Swiss reconnaissance team's 2025 Sci. Rep. paper covers it. Maxar Open Data has it at ~0.5 m WV-2 from 2023-09-10 to 2023-09-11.

**Caveat:** the pre-quake coverage is tourist-grade and clusters around the mosque, minaret, and main square. SfM via COLMAP / hloc will register tens of cameras around those landmarks; it will not register the whole village. Milestone 1's reconstruction target is therefore "mosque + main square subset", not the entire settlement. Whole-village reconstruction needs a Stanford / Hamza-mediated drone permit pass once the framework works on the public-data subset. This is fine for proving the Layer I to Layer IV pipeline.

## Sources

The audit was conducted by web-research subagent on 2026-05-06. Primary sources verified:

- Wikimedia category: <https://commons.wikimedia.org/wiki/Category:Moulay_Brahim>
- Maxar Open Data TSV: <https://github.com/opengeos/maxar-open-data/blob/master/datasets/Morocco-Earthquake-Sept-2023.tsv>
- StEER PVRR: <https://www.researchgate.net/publication/375163415>
- Geoengineer.org drone footage: <https://www.geoengineer.org/videos/suZ2a6c5k8HG2ifq>
- Swiss reconnaissance, Sci. Rep. 2025: <https://www.nature.com/articles/s41598-025-00659-2>
- UNOSAT Adassil damage product (Imi N'Tala adjacent): <https://reliefweb.int/map/morocco/preliminary-satellite-derived-damage-assessment-adassilal-haouz-68m-earthquake-08-09-2023-2211-utc-chichaoua-province-marrakech-safi-region-morocco>
- Imi N'Tala Wikipedia: <https://en.wikipedia.org/wiki/Imi_N%27Tala>

The full source manifest for Moulay Brahim is `data/sites/moulay-brahim/manifest.toml`.
