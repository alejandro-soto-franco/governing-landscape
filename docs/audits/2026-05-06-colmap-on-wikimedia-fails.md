# COLMAP on Wikimedia data fails: M1 Layer I needs different imagery

Date: 2026-05-06
Outcome: BLOCKED on Layer I photogrammetric reconstruction from public Wikimedia data alone.

## What was attempted

`scripts/fetch_moulay_brahim.py` pulled 26 photos from `Category:Moulay_Brahim` (16 pre-quake, 10 post-quake, 23 MB total, all CC-compatible). `examples/m1_reconstruct.py --stage colmap --phase pre_quake` ran pycolmap 4.0.4 with default SIFT extraction, exhaustive matching, and incremental mapping.

## What happened

**Run 1: all 16 pre-quake images, default options.**

```
=> No good initial image pair found.
[5 init-relaxation steps, all fail]
E sfm.cc:279 Failed to create any sparse model
```

Database load reported "connected 5, loaded 5" — only 5 of 16 images had any matches at all.

**Run 2: just the 10 MyPic photos (one uploader, presumed tightest cluster), with relaxed init thresholds (`init_min_num_inliers=30`, `min_num_matches=10`).**

Same outcome: no initial pair found.

## SIFT diagnostics

```
== keypoints per image ==
  MyPic1.jpg     11080
  MyPic2.jpg     14172
  MyPic3.jpg     15670
  MyPic4.jpg     10093
  MyPic5.jpg     10096
  MyPic6.jpg     15362
  MyPic7.jpg     13688
  MyPic8.jpg     10307
  MyPic9.jpg     12570
  MyPic_10.jpg   15416

== geometrically verified pairs ==
  pair (MyPic2, MyPic3): 604 inliers
  (no others)
```

10–15k keypoints per image is healthy. The problem is matching: of 45 candidate pairs after exhaustive matching, exactly one survives geometric verification. The other 44 had between 16 and 35 raw NN matches each, none coherent enough to estimate a fundamental matrix.

## Why

The 10 MyPic photos by the same Wikimedia uploader (Elmido92) are 10 *different scenes* of Moulay Brahim, not 10 viewpoints of the same scene: the gorge, the mosque from a distance, a trail, a vista, etc. They are establishing shots, not a multi-view collection. The full 16-image pre-quake set is even more dispersed (the mosque, the river bathers, a road, the Lalla Takerkoust dam ~30 km south, a camel).

Tourist coverage of a small village is fundamentally not what SfM consumes. SfM needs dozens of overlapping views of the *same* set of buildings, taken close in time with similar lighting. Wikimedia's Moulay Brahim category does not provide that.

## What this means for M1

**The Rust + hypergraph + geometric-features + PyO3 work all stands.** Those are tested and validated independently of any imagery (24 Rust unit tests + 7 pytest smoke tests, all green).

**Layer I (4D Gaussian splatting from public data alone) is blocked.** Three paths forward, in increasing cost:

1. **Synthetic data for Layer I dev.** Generate a fake COLMAP output (handcrafted cameras + a hand-placed sparse point cloud of a model village geometry) and run gsplat against synthetic renders. This unblocks Layer III + IV development end-to-end without real imagery. Recommended as the immediate continuation; lets us prove the framework end-to-end before paying for data.
2. **Maxar pre-quake commercial archive.** WV-2/WV-3 has Moulay Brahim coverage from 2010–2013 but it's outside the Open Data Program. Stanford institutional access via Hamza is the realistic broker. Quote first; this might cost \$0–500 per scene depending on the academic agreement.
3. **On-site drone survey.** The path the paper actually proposes (§8 On-Site Data Collection Protocol). Months away. Requires Moroccan permits and community consent. Out of scope until M2.

## Decision

Pivot M1's "demo a real reconstruction" goal to "demo a synthetic reconstruction that exercises the full Rust + Python pipeline". The synthetic generator becomes the next concrete artefact; the real-data pull is held until either Maxar access or the drone survey lands.

The Wikimedia photos are not deleted — they remain on ASF-EX2 as a reference set. The post-quake StEER and Damages-in-Moulay-Brahim subsets may yet have value as a *qualitative* damage reference even though they do not register in SfM.

## Updated audit verdict

The 2026-05-06 site-imagery audit's "marginal-to-good" SfM tractability for Moulay Brahim was wrong. The correct verdict is "essentially zero from public-internet imagery alone". This brings Moulay Brahim, Imi N'Tala, and Tafza into the same SfM-suitability category, and means the site-selection axis on which Moulay Brahim won (it being the only one with any pre-quake Wikimedia coverage) does not actually translate into reconstruction tractability.

Moulay Brahim remains the right site once richer imagery arrives, because it has the post-quake StEER reconnaissance and journalistic ground photos that the other two do not.
