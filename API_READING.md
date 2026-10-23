# Reading the scans with the Claude API

`scripts/read_with_api.py` does the handwriting-reading step (procedure steps 3 and 4) through the Claude API, so the pipeline can run without Claude Code. It uses the same instructions Claude Code readers used: `scripts/READING_BRIEF.md` and the entry rules in `L0_DATA_ENTRY_PROCEDURE.md`, loaded fresh on every run. If you change a rule there, the API reader follows it too.

Status (2026-10-23): built and tested offline (15 tests, no API calls). It has **not yet been run against the real API**. Run the accuracy test below before using it on a whole site.

## What you need

- An Anthropic API key, from the lab's Anthropic Console account. Use is billed per request; see the costs below.
- The key in the `ANTHROPIC_API_KEY` environment variable. In GitHub Codespaces, add it as a Codespaces secret named `ANTHROPIC_API_KEY` (repository Settings → Secrets and variables → Codespaces). **Never put the key in a file in this repo.**
- The Python packages: `.venv/bin/pip install -r requirements.txt`
- The crop images for the pages you want to read (`scripts/scan_crops.py`, procedure step 2), and that site's table in `data/L0/page_maps.md` (procedure step 1).

## Running it

```
# 1. Check the images and estimate the cost (no API call, free)
.venv/bin/python scripts/read_with_api.py --site CA-CAR3 --dry-run

# 2. First reading of the whole site
.venv/bin/python scripts/read_with_api.py --site CA-CAR3

# 3. Optional independent second reading, then merge (disagreements are flagged)
.venv/bin/python scripts/read_with_api.py --site CA-CAR3 --reading 2
.venv/bin/python scripts/compare_readings.py data/L0/CA-CAR3/api/CA-CAR3_api_reading1.csv \
    data/L0/CA-CAR3/api/CA-CAR3_api_reading2.csv data/L0/CA-CAR3/api/CA-CAR3_api_raw.csv

# 4. Build the workbook as usual (procedure step 5), with --raw pointing at the API file
```

- Output goes to `data/L0/<SITE>/api/` and never overwrites the existing readings.
- Each page is saved as soon as it is read. If a run stops (network, spend limit), run the same command again: finished pages are skipped. `--redo` reads them again.
- `usage.csv` in the reading folder records the tokens, cost and model for every page.
- Options: `--pages 6-10` reads only some pages; `--model` and `--effort` change the model (default `claude-opus-5-5`) and how hard it thinks (default `high`).
- If the model declines a page, the API retries it on a fallback model automatically (`--no-fallback` turns this off). The model that actually answered is printed and logged. A page that still fails is listed at the end and must be read by hand.

## Accuracy test (run this first)

The CA-CAR3 test set (sheets 6-9 = PDF pages 6-10, 126 trees, 2,520 handwritten cells) has a hand-checked answer key in `data/test/`. The Claude Code reading scored **99.1%** on it (23 differences, 21 of them flagged for review). The API reading should be held to the same standard.

```
.venv/bin/python scripts/read_with_api.py --site CA-CAR3 --pages 6-10 --out-dir data/L0/CA-CAR3/api_test
.venv/bin/python scripts/build_l0.py --site CA-CAR3 --census 2 \
    --template "data/template/Forest_Inventory+Mortality_Data_Entry_Template_2024-09-18.xlsx" \
    --prior data/last_inventory/CA-CAR3_inventory_data_2021_L2_25-04-16.xlsx \
    --raw data/L0/CA-CAR3/api_test/CA-CAR3_api_reading1.csv \
    --census-start 2026-08-08 --census-end 2026-08-08 \
    --out data/L0/CA-CAR3/api_test/CA-CAR3_api_test_L0.xlsx
.venv/bin/python scripts/score_against_key.py data/L0/CA-CAR3/api_test/CA-CAR3_api_test_L0.xlsx \
    data/test/CA-CAR3_TEST_FIXED_sheets6-9_L0_26-10-19.xlsx --out data/L0/CA-CAR3/api_test/differences.csv
```

Estimated cost of the test: about $2.60 (range $1.60-$5).

## Costs

Prices: Claude Opus 5.5 is $4 per million input tokens and $20 per million output tokens (Anthropic API list price, October 2026). Each page sends 13 images (12 zoomed strips and the full page), about 55,000 input tokens, or about $0.22 per page. Output (the model's reasoning plus the rows) is the uncertain part: about 5,000-40,000 tokens, or $0.10-$0.80 per page. The estimates below assume 15,000 output tokens, for about $0.52 per page. `usage.csv` gives the real numbers after the test run.

| Site | Pages | One reading (estimate) | Range |
|---|---|---|---|
| CA-CAR3 | 11 | $5.70 | $3.50-$11 |
| CC-CVN2 | 19 | $10.00 | $6-$19 |
| CC-EMN1 | 11 | $5.70* | $3.50-$11 |
| SG-NES1 | 20 | $10.50 | $6.50-$20 |
| SG-NES3 | 14 | $7.40 | $4.50-$14 |
| **All 5 sites** | **75** | **about $39** | **$24-$77** |

A second, independent reading (recommended: it caught about half the errors in the CA-CAR3 test) doubles these numbers, so a full double reading of all five sites is about $80 (range $50-$155). A new site of about 15 pages is about $8 per reading.

\* CC-EMN1's current crops were made at half resolution (100 dpi instead of 200). This estimate assumes it is re-cropped at 200 dpi first; the current crops would cost about $3.75.

## How it works

- One API request per page. The page's header date and note from `page_maps.md` go into the request; the script fills `row_date` itself.
- The response is required to be JSON with exactly the reading CSV's columns, so every page's output has the same shape as the Claude Code readings.
- Images are sent as high-quality JPEG (quality 95), shrunk only if they exceed the API's size limit (2576 px long edge). In practice only the full-page image is shrunk; the zoomed strips go at full size.
- Each request is separate, so a second reading never sees the first.
- Checks on every page: rows without a tag, rows citing a different page, and tags listed twice (flagged for review, not dropped).
