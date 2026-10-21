# L0 run log: all 5 sites, October 2026

All five sites' 2026 scans go through one frozen procedure. Rules do not change
during the run. Anything the procedure doesn't cover is entered as written,
flagged, logged, and added to **Rule questions** below for after the run.

## Frozen versions (sha256, first 12 characters)

If any of these files change, the run is no longer on one procedure. Don't edit them until all five sites are built.

| File | Hash |
|---|---|
| L0_DATA_ENTRY_PROCEDURE.md | 28e27c37cd95 |
| scripts/READING_BRIEF.md | fde5feb0eb81 |
| scripts/build_l0.py | 5ff8e00ebeb6 |
| scripts/scan_crops.py | 565ed3e24d55 |
| scripts/compare_readings.py | d2c0bc308759 (was be65cf1d36f3; 2026-10-21 fixes before first use: rows whose tag the readers read differently are paired by page order, spacing-only and struck-row blank-vs-dash differences are not counted. No entry rule changed) |
| scripts/add_reading_rows.py | c9288f320a11 (was 7ca03d008f2e; 2026-10-21 bug fix: a malformed line no longer leaves a partial page. Saving only, no rule change) |

Check: `sha256sum L0_DATA_ENTRY_PROCEDURE.md scripts/*.py scripts/READING_BRIEF.md`

## Steps per site

1. **Crop** (one site at a time, low priority so the 2-core machine isn't overloaded):
   `nice -n 19 .venv/bin/python scripts/scan_crops.py data/scans/<scan>.pdf 1 <pages> data/work/images/run2026-10`
2. **Map** pages (sheet number, header date, duplicates) into `data/L0/page_maps.md`.
3. **First reading** (Claude, main session): `data/L0/<SITE>/parts/reading1.csv`, appended one page at a time.
4. **Second reading** (separate subagents that never see reading 1, given `scripts/READING_BRIEF.md` and a page assignment): `data/L0/<SITE>/parts/reading2_pNN-NN.csv`.
5. **Merge:** concatenate the reading2 parts into `<SITE>_reading2.csv`, copy reading1 to `<SITE>_reading1.csv`, then
   `.venv/bin/python scripts/compare_readings.py <SITE>_reading1.csv <SITE>_reading2.csv <SITE>_raw.csv`
6. **Build** with `scripts/build_l0.py` (procedure step 5) into `data/L0/<SITE>/<SITE>_inventory_data_2026_L0_<YY-MM-DD>.xlsx`.

## Status

| Site | Pages | Cropped | Mapped | Reading 1 | Reading 2 | Built |
|---|---|---|---|---|---|---|
| CA-CAR3 | 11 | yes | yes | done | done | **yes**: `CA-CAR3_inventory_data_2026_L0_26-10-21.xlsx` (297 trees, 27 disagreeing cells) |
| SG-NES3 | 14 | no | no | no | no | no |
| CC-CVN2 | 19 | no | no | no | no | no |
| SG-NES1 | 20 | no | no | no | no | no |
| CC-EMN1 | 11 | no | no | no | no | no |

Order: CA-CAR3, SG-NES3, CC-EMN1, CC-CVN2, SG-NES1.

**Resume note (2026-10-21):** the session was closed mid-site. The CA-CAR3
second reading was started as three subagents (pages 1-4, 5-7, 8-11). All three parts
finished before the session closed, so nothing needs rerunning. CA-CAR3 is built. Next: crop and map SG-NES3.

## Rule questions (for after the run)

- CA-CAR3 p02 tag 8342: living length 6.6 written inside a hand-drawn box (entered as 6.6, flagged).
- CA-CAR3 p02 tag 8360: handwritten arrow in the left margin pointing at the row (noted in the Issue Log).
- CA-CAR3 p05 tag 8452 (2nd reading): 'beetle' written above 'popcorn' as an insertion in DeathDam mode.
- CA-CAR3 p06 tag 8475 (2nd reading): one word ('sappy') struck through inside a comment; the procedure covers lines through whole cells only.
- CA-CAR3 p04 tag 8423 (2nd reading): '8422' written in the comment cell with an arrow from 8422's comment (handwriting linking two rows).
- CA-CAR3 p11 new-tree tags: zeros written over other marks make the tags look five-digit on the zoomed crop (86000 vs 8600); the second reader entered five digits. Entered 8600, 9903-9908 from the full page and flagged.
- CA-CAR3 p10 tag 8587: a faint '15.9' written in the Height Method cell (entered as written, flagged).
