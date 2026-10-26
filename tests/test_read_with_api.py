"""Offline tests for scripts/read_with_api.py. No API key or network needed:
a stand-in client returns canned responses.

Run: .venv/bin/python -m unittest discover tests
"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import read_with_api as R  # noqa: E402


def make_images(d, site, page, full_size=(3025, 2348)):
    Image.new("RGB", full_size, "white").save(d / f"{site}-p{page:02d}_full.png")
    for b in (1, 2, 3):
        for g in "ABCD":
            Image.new("RGB", (400, 300), "white").save(d / f"{site}-p{page:02d}_b{b}_{g}.png")


def row(tag, source="p01_b1", **kw):
    r = {f: "" for f in R.MODEL_FIELDS}
    r.update(tag=tag, source=source, **kw)
    return r


class FakeClient:
    """Mimics client.beta.messages.stream(...).get_final_message()."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **params):
        self.calls.append(params)
        reply = self.replies.pop(0)
        fake = self

        class Ctx:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: reply)

            def __exit__(self, *a):
                return False
        return Ctx()


def reply(rows, new=(), stop="end_turn", model="claude-opus-5-5", blocks=None):
    text = json.dumps({"rows": rows, "new_situations": list(new)})
    content = blocks if blocks is not None else [
        SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
    usage = SimpleNamespace(input_tokens=50000, output_tokens=8000,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0)
    return SimpleNamespace(stop_reason=stop, content=content, usage=usage, model=model,
                           stop_details=None, _request_id="req_test")


PAGE_MAP = """# maps
## TEST-1 (2 pages)

| PDF page | Sheet | Header date (row_date) | Note |
|---|---|---|---|
| 1 | 1/2 | 2026-08-08 | |
| 2 | "2/2" new trees | (none) | new-trees sheet (Geotag columns) |

## OTHER (1 page)
| 1 | 1/1 | 2026-01-01 | |
"""


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        (self.d / "img").mkdir()
        for p in (1, 2):
            make_images(self.d / "img", "TEST-1", p)
        (self.d / "maps.md").write_text(PAGE_MAP)
        self.args = ["--site", "TEST-1", "--images", str(self.d / "img"),
                     "--page-map", str(self.d / "maps.md"), "--out-dir", str(self.d / "api")]

    def tearDown(self):
        self.tmp.cleanup()

    def read_csv(self, path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))


class TestPageMap(unittest.TestCase):
    def test_real_page_maps_parse_for_every_site(self):
        expected = {"CA-CAR3": 11, "CC-CVN2": 19, "CC-EMN1": 11, "SG-NES3": 14, "SG-NES1": 20}
        for site, n in expected.items():
            m = R.parse_page_map(REPO / "data/L0/page_maps.md", site)
            self.assertEqual(sorted(m), list(range(1, n + 1)), site)
        m = R.parse_page_map(REPO / "data/L0/page_maps.md", "CA-CAR3")
        self.assertEqual(m[5]["row_date"], "")          # "(none)"
        self.assertEqual(m[9]["row_date"], "2026-08-08")  # inside the 8-10 range
        self.assertIn("new-trees", m[11]["note"])

    def test_sections_do_not_leak(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(PAGE_MAP)
        m = R.parse_page_map(f.name, "TEST-1")
        self.assertEqual(sorted(m), [1, 2])

    def test_parse_pages(self):
        self.assertEqual(R.parse_pages("3,5,7-9"), [3, 5, 7, 8, 9])


class TestRequest(Base):
    def test_request_contents(self):
        fake = FakeClient([reply([row("8301")])])
        R.main(self.args + ["--pages", "1"], client=fake)
        p = fake.calls[0]
        self.assertEqual(p["model"], "claude-opus-5-5")
        self.assertEqual(p["thinking"], {"type": "adaptive"})
        self.assertEqual(p["output_config"]["effort"], "high")
        self.assertEqual(p["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(p["fallbacks"], "default")
        self.assertEqual(p["betas"], ["server-side-fallback-2026-07-01"])
        sys_text = p["system"][0]["text"]
        self.assertEqual(p["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertIn("Keep the readings independent", sys_text)   # reading brief
        self.assertIn("## Entry rules", sys_text)                  # procedure rules
        content = p["messages"][0]["content"]
        images = [c for c in content if c["type"] == "image"]
        self.assertEqual(len(images), 13)
        labels = [c["text"] for c in content if c["type"] == "text"]
        self.assertIn("Header date (row_date): 2026-08-08", labels[0])
        self.assertTrue(labels[1].startswith("TEST-1-p01_full.png"))
        self.assertIn("group A", labels[2])

    def test_no_fallback_flag(self):
        fake = FakeClient([reply([row("8301")])])
        R.main(self.args + ["--pages", "1", "--no-fallback"], client=fake)
        self.assertNotIn("fallbacks", fake.calls[0])
        self.assertNotIn("betas", fake.calls[0])

    def test_large_full_page_is_shrunk_to_api_limits(self):
        data, (w, h) = R.encode_image(self.d / "img" / "TEST-1-p01_full.png")
        self.assertLessEqual(max(w, h), R.MAX_EDGE)
        self.assertLessEqual(w * h, R.MAX_PIXELS)
        self.assertLessEqual(len(data), R.MAX_IMAGE_B64)

    def test_missing_crop_fails_that_page_only(self):
        (self.d / "img" / "TEST-1-p01_b2_C.png").unlink()
        fake = FakeClient([reply([row("9901", source="p02_b1")])])
        rc = R.main(self.args, client=fake)
        self.assertEqual(rc, 1)
        self.assertEqual(len(fake.calls), 1)  # page 2 still read
        self.assertFalse((self.d / "api/reading1/p01.csv").exists())


class TestOutput(Base):
    def test_csv_columns_dates_and_combined_file(self):
        fake = FakeClient([
            reply([row("8301", height1="17.3", comment="3 leaders, beetle"), row("8302", crossed_out="Y")]),
            reply([row("9901", source="p02_b1", geotagged="F", geotag_dir="140")]),
        ])
        self.assertEqual(R.main(self.args, client=fake), 0)
        p1 = self.read_csv(self.d / "api/reading1/p01.csv")
        self.assertEqual(list(p1[0].keys()), R.COLS)
        self.assertEqual(p1[0]["row_date"], "2026-08-08")
        self.assertEqual(p1[0]["comment"], "3 leaders, beetle")
        both = self.read_csv(self.d / "api/TEST-1_api_reading1.csv")
        self.assertEqual([r["tag"] for r in both], ["8301", "8302", "9901"])
        self.assertEqual(both[2]["row_date"], "")  # no header date
        usage = self.read_csv(self.d / "api/reading1/usage.csv")
        self.assertEqual(len(usage), 2)
        self.assertAlmostEqual(float(usage[0]["cost_usd_est"]), (50000 * 4 + 8000 * 20) / 1e6, places=3)

    def test_matches_existing_reading_csv_header(self):
        with open(REPO / "data/L0/CA-CAR3/CA-CAR3_reading1.csv", newline="") as f:
            self.assertEqual(next(csv.reader(f)), R.COLS)

    def test_resume_skips_done_pages_and_redo_rereads(self):
        fake = FakeClient([reply([row("8301")]), reply([row("9901", source="p02_b1")])])
        R.main(self.args, client=fake)
        fake2 = FakeClient([])
        R.main(self.args, client=fake2)
        self.assertEqual(fake2.calls, [])
        fake3 = FakeClient([reply([row("8301", height1="5")])])
        R.main(self.args + ["--pages", "1", "--redo"], client=fake3)
        self.assertEqual(self.read_csv(self.d / "api/reading1/p01.csv")[0]["height1"], "5")

    def test_reading2_goes_to_its_own_folder(self):
        fake = FakeClient([reply([row("8301")])])
        R.main(self.args + ["--pages", "1", "--reading", "2"], client=fake)
        self.assertTrue((self.d / "api/reading2/p01.csv").exists())
        self.assertTrue((self.d / "api/TEST-1_api_reading2.csv").exists())

    def test_duplicate_tag_is_flagged_not_dropped(self):
        fake = FakeClient([reply([row("8301"), row("8301", source="p01_b2")])])
        R.main(self.args + ["--pages", "1"], client=fake)
        rows = self.read_csv(self.d / "api/reading1/p01.csv")
        self.assertEqual(len(rows), 2)
        self.assertIn("listed twice", rows[1]["unclear_flags"])

    def test_refusal_and_truncation_write_nothing(self):
        for stop in ("refusal", "max_tokens"):
            fake = FakeClient([reply([row("8301")], stop=stop)])
            rc = R.main(self.args + ["--pages", "1", "--redo"], client=fake)
            self.assertEqual(rc, 1, stop)
            self.assertFalse((self.d / "api/reading1/p01.csv").exists(), stop)

    def test_text_after_fallback_switch_is_used(self):
        good = json.dumps({"rows": [row("8301")], "new_situations": []})
        blocks = [SimpleNamespace(type="text", text='{"rows": [ partial'),
                  SimpleNamespace(type="fallback"),
                  SimpleNamespace(type="text", text=good)]
        fake = FakeClient([reply([], blocks=blocks, model="claude-opus-4-8")])
        self.assertEqual(R.main(self.args + ["--pages", "1"], client=fake), 0)
        self.assertEqual(self.read_csv(self.d / "api/reading1/p01.csv")[0]["tag"], "8301")

    def test_output_feeds_compare_readings(self):
        import subprocess
        fake = FakeClient([reply([row("8301", height1="17.3")]), reply([row("9901", source="p02_b1")]),
                           reply([row("8301", height1="17.8")]), reply([row("9901", source="p02_b1")])])
        R.main(self.args, client=fake)
        R.main(self.args + ["--reading", "2"], client=fake)
        out = self.d / "raw.csv"
        subprocess.run([sys.executable, str(REPO / "scripts/compare_readings.py"),
                        str(self.d / "api/TEST-1_api_reading1.csv"),
                        str(self.d / "api/TEST-1_api_reading2.csv"), str(out)],
                       check=True, capture_output=True)
        merged = self.read_csv(out)
        self.assertIn("height1", merged[0]["unclear_flags"])  # disagreement flagged


if __name__ == "__main__":
    unittest.main()
