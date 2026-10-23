#!/usr/bin/env python3
"""
Read the handwriting on scan pages with the Claude API (procedure step 3, and
step 4 with --reading 2), so the pipeline can run without Claude Code.

Each page is one API request holding the page's 12 zoomed crops plus the full
page (from scripts/scan_crops.py). The model gets the same instructions Claude
Code readers got: scripts/READING_BRIEF.md and the entry rules in
L0_DATA_ENTRY_PROCEDURE.md, read from disk on every run so the rules stay in
one place. Each request is independent, so a second reading never sees the
first.

Output (never overwrites the Claude Code readings):
    data/L0/<SITE>/api/reading<N>/pNN.csv        one file per page
    data/L0/<SITE>/api/reading<N>/usage.csv      tokens, cost, model per page
    data/L0/<SITE>/api/<SITE>_api_reading<N>.csv all pages combined, in page
                                                 order; same columns as the
                                                 other reading CSVs, so
                                                 compare_readings.py and
                                                 build_l0.py take it unchanged

Pages already read are skipped, so a stopped run can be restarted with the
same command. Use --redo to read them again.

Needs an API key in the ANTHROPIC_API_KEY environment variable (never put
the key in a file in this repo).

Usage:
    read_with_api.py --site CA-CAR3 --dry-run         # check images + cost, no API call
    read_with_api.py --site CA-CAR3 --pages 6-10      # first reading of PDF pages 6-10
    read_with_api.py --site CA-CAR3 --reading 2       # independent second reading
"""

import argparse
import base64
import csv
import datetime as dt
import io
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]

# Same columns, same order as every other reading CSV (see add_reading_rows.py).
COLS = ("tag,prev_tag_sheet,sp_code,height1,height2,height_method,dbh1,dbh2,dbh_hom,dbh_method,cii,"
        "canopy_pos,survival_status,deathdam_status,deathdam_mode,living_length,living_length2,pct_crown,"
        "pct_leaves,degrees_leaning,leaf_damage,wounded_trunk,comment,row_date,crossed_out,source,"
        "unclear_flags,geotagged,geotag_ref,geotag_dist,geotag_dir").split(",")
# row_date comes from the page map, not from the model.
MODEL_FIELDS = [c for c in COLS if c != "row_date"]

GROUPS = {
    "A": "prev tag, species, height 1, height 2, height method, DBH 1, DBH 2, DBH HOM, DBH method, CII",
    "B": "canopy position, survival status, DeathDam status, DeathDam mode",
    "C": "living length, % crown remaining, % leaves remaining, degrees leaning, leaf damage, wounded trunk"
         " (new-trees sheet: also Geotag columns)",
    "D": "comment (new-trees sheet: also Geotag columns)",
}
BANDS = {1: "top", 2: "middle", 3: "bottom"}

# API image limits for current models: 2576 px long edge, about 3.75 megapixels,
# 5 MB per image (base64), 32 MB per request.
MAX_EDGE = 2576
MAX_PIXELS = 3_750_000
MAX_IMAGE_B64 = 5 * 1024 * 1024
MAX_REQUEST = 32 * 1024 * 1024
JPEG_QUALITY = 95

# USD per million tokens (input, output, cache read), for the cost estimate only.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-fable-5-1": (10.00, 50.00, 1.00),
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {f: {"type": "string"} for f in MODEL_FIELDS},
                "required": MODEL_FIELDS,
                "additionalProperties": False,
            },
        },
        "new_situations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rows", "new_situations"],
    "additionalProperties": False,
}

API_PREAMBLE = """You are transcribing one scanned tree-census datasheet page for a research project.
Accuracy matters more than speed: this is the raw research record.

This run uses the API instead of Claude Code, so two things in the brief below work differently:
- The images are attached to the message, each preceded by its file name. You do not open files.
- Instead of writing a CSV file, return the rows as JSON in the required format: one object per tree,
  with every column as a string ("" for an empty field). Leave out row_date; the script fills it in
  from the page map. Put every NEW SITUATION note in new_situations as well as in the row's
  unclear_flags.
Everything else in the brief and the procedure applies exactly as written.

"""


class PageError(Exception):
    pass


# ---------------------------------------------------------------- inputs

def parse_pages(spec):
    pages = set()
    for part in spec.split(","):
        a, _, b = part.strip().partition("-")
        pages.update(range(int(a), int(b or a) + 1))
    return sorted(pages)


def parse_page_map(path, site):
    """Read one site's table from page_maps.md -> {page: {sheet, row_date, note}}."""
    text = Path(path).read_text()
    m = re.search(rf"^## {re.escape(site)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"no '## {site}' section in {path}")
    pages = {}
    for line in m.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not re.fullmatch(r"\d+(-\d+)?", cells[0]):
            continue
        date = cells[2] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[2]) else ""
        for p in parse_pages(cells[0]):
            pages[p] = {"sheet": cells[1], "row_date": date,
                        "note": cells[3] if len(cells) > 3 else ""}
    if not pages:
        raise SystemExit(f"no page rows found for {site} in {path}")
    return pages


def page_images(images_dir, site, page):
    """The full page first (for the header), then every crop in band/group order."""
    names = [f"{site}-p{page:02d}_full.png"]
    names += [f"{site}-p{page:02d}_b{b}_{g}.png" for b in BANDS for g in GROUPS]
    paths = [Path(images_dir) / n for n in names]
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        raise PageError(f"missing images (run scan_crops.py first): {', '.join(missing)}")
    return paths


def image_label(path):
    m = re.search(r"-p(\d+)_(?:b(\d)_([A-D])|full)\.png$", path.name)
    if m.group(2) is None:
        return f"{path.name}: the whole page, for the header date and layout"
    return (f"{path.name}: band {m.group(2)} ({BANDS[int(m.group(2))]}), "
            f"group {m.group(3)}: {GROUPS[m.group(3)]}")


def encode_image(path):
    """JPEG inside the API's size limits. Returns (base64 text, (w, h))."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    scale = min(1.0, MAX_EDGE / max(w, h), (MAX_PIXELS / (w * h)) ** 0.5)
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    for q in (JPEG_QUALITY, 90, 85):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        if len(data) <= MAX_IMAGE_B64:
            return data, im.size
    raise PageError(f"{path.name} is too large even after compression")


def image_tokens(size):
    # About one token per 28x28 pixel patch, capped per image.
    w, h = size
    return min(4784, (w * h) // 784)


def build_system():
    brief = (REPO / "scripts/READING_BRIEF.md").read_text()
    proc = (REPO / "L0_DATA_ENTRY_PROCEDURE.md").read_text()
    start = proc.find("## Entry rules")
    if start < 0:
        raise SystemExit("L0_DATA_ENTRY_PROCEDURE.md has no '## Entry rules' section")
    return (API_PREAMBLE + "# READING BRIEF\n\n" + brief +
            "\n\n# FROM L0_DATA_ENTRY_PROCEDURE.md\n\n" + proc[start:])


def build_content(site, page, info, paths):
    assignment = (
        f"Assignment: site {site}, PDF page {page} (sheet {info['sheet']}). "
        f"Header date (row_date): {info['row_date'] or '(none written)'}. "
        f"Page note: {info['note'] or '(none)'}. "
        f"Read every tree row on this page. Use source values like p{page:02d}_b1.")
    content = [{"type": "text", "text": assignment}]
    sizes = []
    for p in paths:
        data, size = encode_image(p)
        sizes.append(size)
        content.append({"type": "text", "text": image_label(p)})
        content.append({"type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
    content.append({"type": "text", "text": "Return the JSON for every tree row on this page."})
    return content, sizes


# ---------------------------------------------------------------- API call

def request_params(args, system, content):
    params = dict(
        model=args.model,
        max_tokens=64000,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive"},
        output_config={"effort": args.effort,
                       "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    if not args.no_fallback:
        # If the model declines a request, the API retries it on a recommended fallback model.
        params["betas"] = ["server-side-fallback-2026-07-01"]
        params["fallbacks"] = "default"
    return params


def call_api(client, params):
    with client.beta.messages.stream(**params) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        det = getattr(msg, "stop_details", None)
        raise PageError(f"the model declined this page ({getattr(det, 'category', None)}); read it by hand")
    if msg.stop_reason == "max_tokens":
        raise PageError("response hit max_tokens before finishing; nothing written for this page")
    # Use the text after the last fallback switch, if there was one.
    blocks = list(msg.content)
    last_fb = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
    text = "".join(b.text for b in blocks[last_fb + 1:] if b.type == "text")
    try:
        return json.loads(text), msg
    except json.JSONDecodeError as e:
        raise PageError(f"response was not valid JSON ({e}); nothing written for this page")


def clean_rows(result, page, info):
    rows, warnings = [], []
    seen = {}
    for r in result["rows"]:
        row = {c: " ".join(str(r.get(c, "")).split()) for c in MODEL_FIELDS}
        row["row_date"] = info["row_date"]
        if not row["tag"]:
            warnings.append(f"a row with no tag (source {row['source']})")
        if not row["source"].startswith(f"p{page:02d}_b"):
            warnings.append(f"tag {row['tag']}: source '{row['source']}' is not on page {page}")
        if row["tag"] in seen:
            warnings.append(f"tag {row['tag']} listed twice on this page")
            note = "script: tag listed twice on this page by the API reading; check which row is right"
            row["unclear_flags"] = " | ".join(x for x in (row["unclear_flags"], note) if x)
        seen[row["tag"]] = True
        rows.append({c: row[c] for c in COLS})
    return rows, warnings


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def log_usage(path, page, msg, model):
    u = msg.usage
    inp, out, cread = u.input_tokens, u.output_tokens, (u.cache_read_input_tokens or 0)
    cwrite = u.cache_creation_input_tokens or 0
    pin, pout, pread = PRICES.get(msg.model, PRICES.get(model, (0, 0, 0)))
    cost = (inp * pin + cwrite * pin * 1.25 + cread * pread + out * pout) / 1e6
    new = not path.exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["page", "time", "model_used", "input_tokens", "cache_write_tokens",
                        "cache_read_tokens", "output_tokens", "cost_usd_est", "request_id"])
        w.writerow([page, dt.datetime.now().isoformat(timespec="seconds"), msg.model, inp, cwrite,
                    cread, out, f"{cost:.3f}", getattr(msg, "_request_id", "")])
    return cost


def combine(out_dir, combined, pages_in_map):
    rows, have = [], []
    for p in sorted(pages_in_map):
        f = out_dir / f"p{p:02d}.csv"
        if f.exists():
            have.append(p)
            with open(f, newline="") as fh:
                rows.extend(csv.DictReader(fh))
    write_csv(combined, rows)
    missing = sorted(set(pages_in_map) - set(have))
    return len(rows), missing


# ---------------------------------------------------------------- main

def main(argv=None, client=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", required=True)
    ap.add_argument("--pages", help="PDF pages, e.g. 1-11 or 3,5,7-9 (default: every page in the page map)")
    ap.add_argument("--reading", type=int, default=1, choices=[1, 2])
    ap.add_argument("--images", default=str(REPO / "data/work/images/run2026-10"))
    ap.add_argument("--page-map", default=str(REPO / "data/L0/page_maps.md"))
    ap.add_argument("--out-dir", help="default: data/L0/<SITE>/api")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--no-fallback", action="store_true", help="do not retry declined requests on another model")
    ap.add_argument("--redo", action="store_true", help="read pages again even if already done")
    ap.add_argument("--dry-run", action="store_true", help="check images and estimate cost; no API call")
    args = ap.parse_args(argv)

    page_map = parse_page_map(args.page_map, args.site)
    pages = parse_pages(args.pages) if args.pages else sorted(page_map)
    unknown = [p for p in pages if p not in page_map]
    if unknown:
        raise SystemExit(f"pages not in the {args.site} page map: {unknown}")

    base = Path(args.out_dir) if args.out_dir else REPO / f"data/L0/{args.site}/api"
    out_dir = base / f"reading{args.reading}"
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    system = build_system()

    if not args.dry_run and client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. In a Codespace, add it as a Codespaces "
                             "secret; elsewhere, `export ANTHROPIC_API_KEY=...` in the terminal.")
        import anthropic
        client = anthropic.Anthropic(max_retries=4, timeout=1800)

    total_cost, failed = 0.0, []
    for page in pages:
        out = out_dir / f"p{page:02d}.csv"
        if out.exists() and not args.redo and not args.dry_run:
            print(f"p{page:02d}: already read, skipping ({out.name}; --redo to read again)")
            continue
        try:
            paths = page_images(args.images, args.site, page)
            content, sizes = build_content(args.site, page, page_map[page], paths)
            params = request_params(args, system, content)
            if args.dry_run:
                size = len(json.dumps(params))
                img_tok = sum(image_tokens(s) for s in sizes)
                txt_tok = len(system) // 3
                pin, pout, _ = PRICES.get(args.model, (0, 0, 0))
                est = ((img_tok + txt_tok) * pin + 15000 * pout) / 1e6
                total_cost += est
                ok = "OK" if size < MAX_REQUEST else "TOO LARGE"
                print(f"p{page:02d}: {len(paths)} images, request {size / 1e6:.1f} MB ({ok}), "
                      f"~{img_tok + txt_tok:,} input tokens, est. ${est:.2f}")
                continue
            print(f"p{page:02d}: reading...", flush=True)
            result, msg = call_api(client, params)
            rows, warnings = clean_rows(result, page, page_map[page])
            write_csv(out, rows)
            cost = log_usage(out_dir / "usage.csv", page, msg, args.model)
            total_cost += cost
            tags = [r["tag"] for r in rows]
            used = "" if msg.model == args.model else f", answered by fallback model {msg.model}"
            print(f"p{page:02d}: {len(rows)} rows ({tags[0] if tags else '-'}..{tags[-1] if tags else '-'}), "
                  f"${cost:.2f}{used}")
            for w in warnings:
                print(f"   warning: {w}")
            for s in result["new_situations"]:
                print(f"   NEW SITUATION: {s}")
        except PageError as e:
            failed.append(page)
            print(f"p{page:02d}: FAILED: {e}")
        except Exception as e:  # API errors: stop on ones a retry will not fix
            import anthropic
            if isinstance(e, anthropic.AuthenticationError):
                raise SystemExit("The API key was rejected. Check ANTHROPIC_API_KEY.")
            if isinstance(e, anthropic.PermissionDeniedError):
                raise SystemExit(f"The API key cannot use {args.model}: {e.message}")
            if isinstance(e, anthropic.NotFoundError):
                raise SystemExit(f"Model {args.model} not found: {e.message}")
            if isinstance(e, anthropic.RateLimitError):
                raise SystemExit("Rate limit or spend limit reached. Re-run the same command later; "
                                 "pages already read are kept.")
            if isinstance(e, (anthropic.APIStatusError, anthropic.APIConnectionError)):
                failed.append(page)
                print(f"p{page:02d}: FAILED (API error, re-run to retry): {e}")
                continue
            raise

    if args.dry_run:
        print(f"\nEstimated total: ${total_cost:.2f} for {len(pages)} pages (rough; thinking length varies).")
        return 0
    combined = base / f"{args.site}_api_reading{args.reading}.csv"
    n, missing = combine(out_dir, combined, page_map)
    print(f"\nThis run: ${total_cost:.2f}. Combined {n} rows into {combined.relative_to(REPO) if combined.is_relative_to(REPO) else combined}")
    if missing:
        print(f"Pages not read yet: {missing}")
    if failed:
        print(f"Failed pages: {failed} (re-run the same command to retry them)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
