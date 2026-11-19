"""Relationship paths, the instant mood reaction, and the romance fix (adult() used to be undefined)."""
import unittest

from crumble import feel
from crumble.rp import relations as R
from crumble.rp.resolve import rp_resolve


def body(act, rp=None, c=None, aff=80):
    c = c or {"id": "c1", "name": "Mira", "age": "25"}
    return {"members": [c], "user": "Sam", "text": "*tries something*", "rp": rp or {}, "aff": {c["id"]: aff}, "mood": {c["id"]: "happy"},
            "cfg": {"romance": True}, "forced": act, "ustats": "CHA 14"}


class Paths(unittest.TestCase):
    def test_ladder_is_shared(self):
        for k, v in R.RELS.items():
            self.assertEqual(len(v["stages"]), 6, k)
            self.assertEqual(len(v["phrases"]), 6, k)
        self.assertEqual((R.stage_idx(0), R.stage_idx(9.9), R.stage_idx(10), R.stage_idx(45), R.stage_idx(85), R.stage_idx(100)), (0, 0, 1, 3, 5, 5))

    def test_adult(self):
        for age, want in (("25", True), ("17", False), ("18", True), ("", True), ("twenty-one", True), ("sixteen", False), ("a teenager", False), ("900 years", True)):
            self.assertEqual(R.adult({"age": age}), want, age)

    def test_minor_never_gets_romance(self):
        kid = {"id": "k", "age": "15"}
        self.assertEqual(R.effective(kid, {"type": "romance"}), "friend")
        self.assertEqual(R.effective(kid, {}), "friend")
        self.assertEqual(R.effective({"id": "a", "age": "30"}, {"type": "romance"}), "romance")
        self.assertEqual(R.effective({"id": "a"}, {"type": "nonsense"}), "auto")

    def test_blocks(self):
        c = {"id": "c1", "age": "30"}
        self.assertEqual(R.rel_block(c, {}, "Mira", "Sam"), "")
        self.assertEqual(R.rel_block(c, {"type": "romance"}, "Mira", "Sam"), "")
        b = R.rel_block(c, {"type": "mentor", "role": "master", "v": 50}, "Mira", "Sam")
        self.assertIn("Mira is Sam's master", b)
        self.assertIn("not romantic", b)
        self.assertIn("Mira is Sam's master", b)
        d = R.rel_block(c, {"type": "mentor", "role": "disciple"}, "Mira", "Sam")
        self.assertIn("Mira is Sam's disciple", d)
        self.assertIn("close friends", R.rel_block(c, {"type": "friend", "v": 50}, "Mira", "Sam"))

    def test_public_has_everything_the_page_draws(self):
        p = R.public()
        self.assertEqual(set(p), set(R.RELS))
        self.assertEqual(len(p["mentor"]["roles"]), 2)
        self.assertTrue(all(len(v["stages"]) == 6 and v["icon"] and v["color"] for v in p.values()))


class Resolve(unittest.TestCase):
    def test_romantic_beat_no_longer_crashes(self):
        r = rp_resolve(body("kiss", {"rom": {"c1": {"v": 40, "ms": []}}}))
        self.assertTrue(r["card"]["rows"])

    def test_non_romantic_path_declines_kindly(self):
        r = rp_resolve(body("kiss", {"rel": {"c1": {"type": "friend", "v": 50}}}))
        self.assertEqual(r["card"]["rows"][0]["res"], "Not that kind of bond")
        self.assertIn("friendship", r["brief"].lower())
        self.assertEqual(r["rp"].get("rom", {}).get("c1", {}).get("v", 0), 0)

    def test_minor_declines_even_on_auto(self):
        r = rp_resolve(body("kiss", {}, {"id": "c1", "name": "Mira", "age": "16"}))
        self.assertEqual(r["card"]["rows"][0]["res"], "Not that kind of bond")


class Feel(unittest.TestCase):
    C = {"id": "c1", "name": "Rex", "personality": "bold, loud, proud"}

    def test_quiet_when_nothing_lands(self):
        self.assertEqual(feel.peek(self.C, {}, "what's for dinner"), {"quiet": True})

    def test_insult_and_kindness_move_in_opposite_directions(self):
        bad = feel.peek(self.C, {"mood": "neutral"}, "You are an idiot, shut up.")
        good = feel.peek(self.C, {"mood": "neutral"}, "Thank you, that was really kind of you.")
        self.assertLessEqual(bad["delta"], 0)
        self.assertGreaterEqual(good["delta"], 0)
        self.assertNotEqual(bad["mood"], good["mood"])
        self.assertTrue(bad["emoji"] and bad["why"])


if __name__ == "__main__":
    unittest.main()
