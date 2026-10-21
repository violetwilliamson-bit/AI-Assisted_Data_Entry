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
| scripts/compare_readings.py | be65cf1d36f3 |
| scripts/add_reading_rows.py | 7ca03d008f2e |

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
| CA-CAR3 | 11 | yes | yes | pages 1-2 of 11 done | pages 5-11 done; 1-4 pending | no |
| SG-NES3 | 14 | no | no | no | no | no |
| CC-CVN2 | 19 | no | no | no | no | no |
| SG-NES1 | 20 | no | no | no | no | no |
| CC-EMN1 | 11 | no | no | no | no | no |

Order: CA-CAR3, SG-NES3, CC-EMN1, CC-CVN2, SG-NES1.

**Resume note (2026-10-21):** the session was closed mid-site. The CA-CAR3
second reading was started as three subagents (pages 1-4, 5-7, 8-11). Pages 5-7 and 8-11 finished
(`reading2_p05-07.csv`, `reading2_p08-11.csv`). A part file exists only if its subagent finished before the session closed. Check
`data/L0/CA-CAR3/parts/` and rerun any missing `reading2_*` part with the same
assignment (pages, row_date, output path; see page_maps.md). Reading 1 resumes
at CA-CAR3 page 3.

## Rule questions (for after the run)

- CA-CAR3 p02 tag 8342: living length 6.6 written inside a hand-drawn box (entered as 6.6, flagged).
- CA-CAR3 p02 tag 8360: handwritten arrow in the left margin pointing at the row (noted in the Issue Log).
- CA-CAR3 p05 tag 8452 (2nd reading): 'beetle' written above 'popcorn' as an insertion in DeathDam mode.
- CA-CAR3 p06 tag 8475 (2nd reading): one word ('sappy') struck through inside a comment; the procedure covers lines through whole cells only.
