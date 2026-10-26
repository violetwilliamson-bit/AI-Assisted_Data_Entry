#!/usr/bin/env python3
"""
Score an L0 workbook against a hand-checked answer key, cell by cell, on the
20 columns that are read from handwriting. Only trees in the key are scored.

Usage:
    score_against_key.py <L0.xlsx> <key.xlsx> [--out differences.csv]

Example (the CA-CAR3 test set, sheets 6-9 = PDF pages 6-10):
    score_against_key.py data/L0/CA-CAR3/api/test/CA-CAR3_api_L0.xlsx \
        data/test/CA-CAR3_TEST_FIXED_sheets6-9_L0_26-10-19.xlsx

A cell counts as an error when its value differs from the key. Each error is
also marked as flagged (yellow in the L0 file, so a person would have checked
it) or not flagged (it would slip through without a full hand-check).
"""
import argparse
import csv
import datetime as dt
import sys

import openpyxl

READ_COLUMNS = [
    "Height_1_M", "Height_2_M", "Height_Method", "DBH_1_CM", "DBH_2_CM", "DBH_HOM", "DBH_Method",
    "CII", "Crown_Class", "Survival_Status", "Death_Damage_Status", "Death_Damage_Mode",
    "Living_Length_1_M", "Living_Length_2_M", "Pct_Crown_Remaining", "Pct_Leaves_Remaining",
    "Degrees_Leaning", "Leaf_Damage", "Wounded_Trunk", "Comments",
]


def norm(v):
    if v is None:
        return ""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = " ".join(str(v).split())
    try:
        f = float(s)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return s


def load(path):
    ws = openpyxl.load_workbook(path)["Data Entry"]
    header = [c.value for c in ws[1]]
    col = {h: i for i, h in enumerate(header)}
    rows = {}
    for r in ws.iter_rows(min_row=2):
        tag = norm(r[col["Tag_Number"]].value)
        if not tag:
            continue
        cells = {}
        for name in READ_COLUMNS:
            c = r[col[name]]
            fill = c.fill.fgColor.rgb if c.fill and c.fill.fill_type == "solid" else None
            cells[name] = (norm(c.value), bool(fill) and str(fill).upper().endswith("FFFF00"))
        rows.setdefault(tag, cells)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("l0")
    ap.add_argument("key")
    ap.add_argument("--out", help="write every differing cell to this CSV")
    a = ap.parse_args()

    got, key = load(a.l0), load(a.key)
    missing = [t for t in key if t not in got]
    diffs = []
    cells = 0
    for tag, kcells in key.items():
        if tag not in got:
            continue
        for name in READ_COLUMNS:
            cells += 1
            want = kcells[name][0]
            have, flagged = got[tag][name]
            if have != want:
                diffs.append({"tag": tag, "column": name, "l0_value": have, "key_value": want,
                              "flagged": "yes" if flagged else "no"})

    flagged = sum(d["flagged"] == "yes" for d in diffs)
    acc = 100 * (1 - len(diffs) / cells) if cells else 0
    print(f"Trees in key: {len(key)}; found in L0: {len(key) - len(missing)}")
    if missing:
        print(f"Trees in the key but not in the L0 file: {', '.join(missing)}")
    print(f"Cells scored: {cells}")
    print(f"Differences from key: {len(diffs)} ({acc:.1f}% match)")
    print(f"  flagged for review: {flagged}; not flagged: {len(diffs) - flagged}")
    by_col = {}
    for d in diffs:
        by_col[d["column"]] = by_col.get(d["column"], 0) + 1
    for name, n in sorted(by_col.items(), key=lambda x: -x[1]):
        print(f"  {name}: {n}")
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["tag", "column", "l0_value", "key_value", "flagged"])
            w.writeheader()
            w.writerows(diffs)
        print(f"Wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
