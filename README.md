# Tree Census Data Entry Helper

Turns scanned, handwritten tree census datasheets into digital L0 spreadsheets, following the Data Entry and Cleanup Protocol — so the data doesn't have to be typed in by hand.

## Where this fits in the lab protocol

This repo covers only the **L0 step** of the Data Entry and Cleanup Protocol: turning the paper datasheets into a cell-for-cell digital record of what the field crew wrote. Corrections and cleanup happen later, at L1 and L2, as the protocol describes.

- Copy of the Data Entry Protocol used here: [data/protocol/Data Entry Protocol.pdf](data/protocol/Data%20Entry%20Protocol.pdf)
- The L0 procedure this repo follows, step by step: [L0_DATA_ENTRY_PROCEDURE.md](L0_DATA_ENTRY_PROCEDURE.md)

## Status (October 2026)

All five plots from the 2026 census have L0 workbooks in `data/L0/<site>/`. All were made with the same procedure, and each is waiting for its human hand-check.

| Site | Trees | L0 workbook |
|---|---|---|---|
| CA-CAR3 | 297 | `CA-CAR3_inventory_data_2026_L0_26-10-21.xlsx` |
| CC-CVN2 | 534 | `CC-CVN2_inventory_data_2026_L0_26-10-21.xlsx` |
| CC-EMN1 | 312 | `CC-EMN1_inventory_data_2026_L0_26-10-23.xlsx` |
| SG-NES1 | 555 | `SG-NES1_inventory_data_2026_L0_26-10-23.xlsx` |
| SG-NES3 | 421 | `SG-NES3_inventory_data_2026_L0_26-10-23.xlsx` |

- **Accuracy:** on the messiest test pages (CA-CAR3 sheets 6-9, 126 trees, 2,520 handwritten cells), the AI reading matched the hand-checked answer key in 99.1% of cells, and most differences were already flagged for review. A second, independent reading catches about half of the remaining errors.
- **CC-EMN1:** its scan images were cut at half the resolution of the other sites, so check this site extra carefully.
- **Open rule questions** from the run are listed in [data/L0/RUN_LOG.md](data/L0/RUN_LOG.md).

## How it works

| Step | What happens | Done by | Needs AI? |
|---|---|---|---|
| 1. Map the scan | Match each PDF page to its sheet number and header date, in `data/L0/page_maps.md` | Person | No |
| 2. Crop | `scripts/scan_crops.py` straightens each page and cuts it into 12 zoomed strips | Script | No |
| 3. Read | Transcribe every handwritten mark into a CSV, one row per tree | AI (or a person typing) | Yes, to avoid typing |
| 4. Second reading (optional) | Read again independently; `scripts/compare_readings.py` flags every disagreement | AI + script | Yes |
| 5. Build | `scripts/build_l0.py` fills the lab template, checks every value against the sheet legends, highlights problems and writes the Issue Log | Script | No |
| 6. Hand-check | Compare flagged cells with the paper; correct a copy, which becomes L1 | Person | No |

Step 3 is the only step that uses AI, and the only step where handwriting is interpreted. There are two ways to run it:

- **Claude Code** (how the 2026 files were made): an AI assistant in this Codespace opens the strips and writes the CSV, following [scripts/READING_BRIEF.md](scripts/READING_BRIEF.md).
- **The Claude API**, for anyone without Claude Code: `scripts/read_with_api.py` reads each page with the same instructions. It needs a lab API key and costs about $0.50 per page. See [API_READING.md](API_READING.md) for setup, costs and the accuracy test. *Built and tested offline; not yet run with a real key.*

Without AI, a person can type the CSV by hand while viewing the strips from step 2 and still use every other step.

## The L0 rule in short

Enter **only what is handwritten, exactly as written**. Nothing pre-printed is entered, and nothing is corrected. Anything unclear or unusual is highlighted yellow and explained in the Issue Log, with a reference to the scan strip it came from. Corrections belong at L1 and L2. The full entry rules are in [L0_DATA_ENTRY_PROCEDURE.md](L0_DATA_ENTRY_PROCEDURE.md#entry-rules).

## Setup

Open the repo in GitHub Codespaces (the dev container installs the tools), or on your own machine:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The crop script also needs `pdftoppm` (from poppler-utils), which the dev container already has.

## Repo layout

```
L0_DATA_ENTRY_PROCEDURE.md   the L0 procedure and entry rules (start here)
API_READING.md               reading the scans with the Claude API, with costs
TREE_CENSUS_WORKING_FILE.md  working notes and history of the project
requirements.txt             Python packages
scripts/
  scan_crops.py              step 2: straighten and crop scan pages
  READING_BRIEF.md           step 3: instructions given to every reader
  read_with_api.py           step 3 via the Claude API
  add_reading_rows.py        helper for adding rows to a reading CSV
  compare_readings.py        step 4: merge two readings, flag disagreements
  build_l0.py                step 5: build the L0 workbook
  score_against_key.py       score an L0 file against a hand-checked answer key
tests/                       offline tests (.venv/bin/python -m unittest discover tests)
data/
  L0/<site>/                 L0 workbook, raw CSV and readings per site
  L0/page_maps.md            page-to-sheet maps and header dates (step 1)
  L0/RUN_LOG.md              log of the October 2026 run and open rule questions
  L1/                        hand-checked L1 workbooks
  test/                      CA-CAR3 test set with its hand-checked answer key
  template/                  the lab's data entry template
  last_inventory/            the 2021 L2 files, source of tag, species and tag date for continuing trees
  protocol/                  the Data Entry and Cleanup Protocol
  scans/                     raw scanned datasheets (local only, not in git)
  work/images/               cropped images (regenerable, not in git)
```

## More detail

[TREE_CENSUS_WORKING_FILE.md](TREE_CENSUS_WORKING_FILE.md) has the project history, per-site notes and the earlier rule decisions.
