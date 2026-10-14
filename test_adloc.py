"""python -m unittest test_adloc  - the guards that keep competitor numbers and copy changes out."""
import json, tempfile, unittest
from argparse import Namespace
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image

import adloc, hf

BRIEF = {"code": "T-1", "lang": "", "market": "", "product": "Glow", "competitor": "Rival",
         "product_image": "product.png", "currency": "€", "price": "€29,95", "offer": "2+1",
         "guarantee": "30 days", "engine": "flow"}


def ad(*texts, **kw):
    e = {"has_text": True, "has_product": True, "scene": "A woman holds a white tub.", "swaps": [],
         "texts": [dict(zip(("source", "target", "kind"), t), where="top, white bold") for t in texts]}
    return {**e, **kw}


class Guards(unittest.TestCase):
    def errs(self, e, **brief):
        return adloc.ad_problems("01_x.jpg", e, {**BRIEF, **brief})

    def test_clean_replica_passes(self):
        self.assertEqual(self.errs(ad(("Soft skin in 7 days", "Soft skin in 7 days", "copy"),
                                      ("Rival", "Glow", "brand"), ("€39,99", "€29,95", "price"))), [])

    def test_replica_refuses_changed_copy(self):
        self.assertTrue(self.errs(ad(("Soft skin", "Smooth skin", "copy"))))

    def test_localized_allows_translated_copy(self):
        self.assertEqual(self.errs(ad(("Soft skin", "Zachte huid", "copy")), lang="Dutch"), [])

    def test_competitor_price_refused(self):
        self.assertTrue(self.errs(ad(("€39,99", "€39,99", "price"))))

    def test_offer_filed_as_copy_refused(self):
        self.assertTrue(self.errs(ad(("Buy 2 get 1 free", "Buy 2 get 1 free", "copy"))))

    def test_competitor_name_left_refused(self):
        self.assertTrue(self.errs(ad(("Rival works", "Rival works", "copy"))))


class Aspects(unittest.TestCase):
    def test_4x5_native_on_higgsfield_padded_on_flow(self):
        self.assertEqual(adloc.pick_aspect(480, 600, "higgsfield"), ("4:5", False))
        self.assertEqual(adloc.pick_aspect(480, 600, "flow"), ("3:4", True))


class Build(unittest.TestCase):
    def test_replica_build_end_to_end(self):
        with tempfile.TemporaryDirectory() as d, redirect_stdout(StringIO()):
            job = Path(d) / "T-1"
            prod = Path(d) / "prod.png"
            Image.new("RGB", (300, 300), "blue").save(prod)
            adloc.cmd_init(Namespace(job=str(job), code="t-1", product="Glow", lang=None, market=None,
                                     engine="higgsfield", hf_login="team", hf_workspace="ws1",
                                     product_image=str(prod), competitor="Rival", currency="€",
                                     price="€29,95", offer="", guarantee="", profile=None))
            Image.new("RGB", (480, 600), "white").save(job / "01_originals" / "01_123.jpg")
            json.dump({"01_123": {"url": "u", "origin": "provided"}},
                      open(job / "sources.json", "w"))
            adloc.cmd_scan(Namespace(job=str(job)))
            ads = adloc.load(job / "ads.json")
            ads["01_123.jpg"].update(ad(("Rival", "Glow", "brand")))
            adloc.save(job / "ads.json", ads)
            adloc.cmd_build(Namespace(job=str(job), spell=[], allow_short=False))
            P = adloc.load(job / "prompts.json")
        self.assertEqual(P["engine"], "higgsfield")
        line = P["lines"][0]
        self.assertEqual(line["aspect"], "4:5")
        self.assertIn("same language as the original", line["prompt"])
        self.assertEqual(len(line["refs"]), 2)


class HfNames(unittest.TestCase):
    def test_next_name_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            s = Path(d)
            self.assertEqual(hf.next_name(s, "t-1", "03").name, "claude_t-1_line03.png")
            (s / "claude_t-1_line03.png").touch()
            self.assertEqual(hf.next_name(s, "t-1", "03").name, "claude_t-1_line03_alt2.png")


if __name__ == "__main__":
    unittest.main()
