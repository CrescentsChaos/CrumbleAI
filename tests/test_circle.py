"""Group dynamics: bonds between characters, jealousy, interruptions, side conversations, auto-talk wiring."""
import random
import re
import unittest

from crumble import web
from crumble.prompt import build_messages
from crumble.rp import circle as c
from crumble.rp.director import plan_next

MIRA = {"id": "mira", "name": "Mira", "personality": "shy", "relationships": "Rex: rival. Faith - best friend", "age": "24"}
REX = {"id": "rex", "name": "Rex", "personality": "loud", "relationships": "Mira is my rival", "age": "27"}
FAITH = {"id": "faith", "name": "Faith", "personality": "kind", "age": "25"}
KID = {"id": "kid", "name": "Kit", "age": "15", "relationships": "Rex is my boyfriend"}
M = [MIRA, REX, FAITH]
G = {"pace": "natural"}


class Bonds(unittest.TestCase):
    def test_sheets_seed_the_bonds(self):
        p = c.seed(M, None)["pairs"]
        self.assertEqual(p["mira|rex"]["k"], "rival")
        self.assertEqual(p["faith|mira"]["k"], "friend")
        self.assertEqual(p["faith|rex"]["k"], "auto")

    def test_romance_never_applies_to_a_minor(self):
        p = c.seed([REX, KID], None)["pairs"]["kid|rex"]
        self.assertNotEqual(p["k"], "romance")
        cir = c.seed([REX, KID], None)
        cir["pairs"]["kid|rex"]["k"] = "romance"
        self.assertNotEqual(c.kind_of(cir, "kid", "rex", {"kid": KID, "rex": REX}), "romance")

    def test_cruelty_raises_tension_and_kindness_warms(self):
        cir = c.seed(M, None)
        x0, f0 = cir["pairs"]["faith|rex"]["x"], cir["pairs"]["faith|rex"]["f"]
        for _ in range(3):
            cir, _ = c.observe(cir, M, "rex", "Faith, shut up, you are useless and stupid.", "Sam", prev="user")
        self.assertGreater(cir["pairs"]["faith|rex"]["x"], x0)
        cir2 = c.seed(M, None)
        for _ in range(3):
            cir2, _ = c.observe(cir2, M, "faith", "Rex, thank you, that was really kind of you, I love it.", "Sam", prev="user")
        self.assertGreater(cir2["pairs"]["faith|rex"]["f"], f0)

    def test_flirting_with_someones_partner_makes_them_jealous(self):
        cir = c.seed(M, None)
        cir["pairs"]["faith|mira"]["k"] = "romance"
        for _ in range(4):
            cir, notes = c.observe(cir, M, "rex", "Faith, you look gorgeous, darling, I adore you.", "Sam", prev="user")
        self.assertGreaterEqual(cir["pairs"]["mira|rex"]["j"]["mira"], 20)

    def test_clean_bounds_and_drops_strangers(self):
        cir = c.clean({"pairs": {"mira|rex": {"k": "bogus", "f": 999, "t": -5, "x": "x"}, "mira|ghost": {"k": "friend"}}}, ["mira", "rex"])
        self.assertEqual(list(cir["pairs"]), ["mira|rex"])
        p = cir["pairs"]["mira|rex"]
        self.assertEqual((p["k"], p["f"], p["t"]), ("auto", 100, 0))

    def test_block_is_per_speaker_and_has_no_numbers(self):
        cir = c.seed(M, None)
        b = c.block(MIRA, M, cir, "Sam", {"mira": 50, "rex": 15, "faith": 85})
        self.assertIn("Rex", b)
        self.assertIn("Faith", b)
        self.assertIn("openly distrusts Sam", b)
        self.assertFalse(re.search(r"\d", b))
        self.assertEqual(c.block(MIRA, [MIRA], cir, "Sam"), "")

    def test_the_block_reaches_the_prompt_and_new_cues_exist(self):
        grp = dict(name="Crew", scenario="", members=M, narrator=False)
        cir = c.seed(M, None)
        m = build_messages(MIRA, "Sam", [{"role": "user", "content": "hi"}], {"mode": "story", "state": {}, "words": (10, 30), "group": grp,
                                                                           "circle": cir, "affs": {"rex": 10}, "tail": "x", "private": []})
        self.assertIn("How Mira feels about the others", m[-1]["content"])
        from crumble.prompt import cue_text
        for why in ("interrupt", "jealous", "disagree", "back", "thread", "branch"):
            self.assertIn("{{char}}", cue_text({"cue": {"why": why, "by": "Rex"}}, MIRA))


class Director(unittest.TestCase):
    def setUp(self):
        random.seed(3)
        self.cir = c.seed(M, None)
        self.cir["pairs"]["mira|rex"].update(x=85, k="enemy")

    def test_an_enemy_interrupts_and_disagrees(self):
        hist = [{"role": "user", "content": "so?"}, {"role": "assistant", "cid": "rex", "name": "Rex", "content": "I think we should leave."}]
        seen = {plan_next(G, M, hist, [], 0, 0, "Sam", {"circle": self.cir, "keep": True}).get("why") for _ in range(200)}
        self.assertTrue(seen & {"interrupt", "disagree"})

    def test_a_side_conversation_continues_between_two(self):
        hist = [{"role": "user", "content": "so?"}, {"role": "assistant", "cid": "rex", "name": "Rex", "content": "Faith, remember the lake?"},
                {"role": "assistant", "cid": "faith", "name": "Faith", "content": "Rex, how could I forget?"}]
        cir = c.seed(M, None)
        why = [plan_next(G, M, hist, ["rex", "faith"], 3, 2, "Sam", {"circle": cir, "keep": True}) for _ in range(100)]
        self.assertGreater(sum(1 for r in why if r.get("why") == "thread" and r["next"] == "rex"), 30)

    def test_not_everyone_answers_a_plain_message(self):
        hist = [{"role": "user", "content": "nice weather today"}]
        counts = []
        for _ in range(300):
            spoke = []
            for n in range(6):
                r = plan_next(G, M, hist, spoke, 0 if n == 0 else 3, n, "Sam", {"circle": c.seed(M, None)})
                if not r.get("next"):
                    break
                spoke.append(r["next"])
                hist = hist + [{"role": "assistant", "cid": r["next"], "name": r["next"], "content": "hm"}]
            counts.append(len(spoke))
            hist = hist[:1]
        self.assertLess(sum(1 for n in counts if n == 3) / len(counts), .35)

    def test_mentions_still_force_a_reply(self):
        hist = [{"role": "user", "content": "@Faith are you ok?"}]
        self.assertEqual(plan_next(G, M, hist, [], 0, 0, "Sam", {})["next"], "faith")


class Page(unittest.TestCase):
    def test_the_let_them_talk_and_auto_buttons_are_wired(self):
        html = web._build_page()
        self.assertIn("id=keep hidden", html)
        self.assertIn("id=auto", html)
        self.assertRegex(html, r"\$\('#greet'\)\.hidden=!!G;\$\('#keep'\)\.hidden=!G")     # the button appears as soon as a group is open
        self.assertIn("id=gauto", html)


if __name__ == "__main__":
    unittest.main()


class Api(unittest.TestCase):
    def test_circle_endpoints_and_group_auto_flag(self):
        import os, tempfile
        from tests import helpers as h
        srv = h.serve()
        ids = []
        for ch in (MIRA, REX, FAITH):
            st, d = h.call(srv, "POST", "/api/chars", dict(ch, id="t_" + ch["id"]))
            ids.append(d.get("id", "t_" + ch["id"]))
        st, g = h.call(srv, "POST", "/api/groups", {"name": "Crew", "members": ids, "auto": True, "auto_max": 4})
        try:
            self.assertTrue(g["auto"])
            self.assertEqual(g["auto_max"], 4)
            st, v = h.call(srv, "POST", "/api/circle", {"group": g["id"], "user": "Sam", "aff": {}})
            self.assertEqual(len(v["pairs"]), 3)
            st, v2 = h.call(srv, "POST", "/api/circle/observe", {"group": g["id"], "circle": v["circle"], "user": "Sam", "speaker": ids[1],
                                                                  "text": "Faith, you are useless.", "prev": "user"})
            self.assertIn("pairs", v2)
            st, v3 = h.call(srv, "POST", "/api/circle", {"group": "nope"})
            self.assertIn("err", v3)
        finally:
            h.call(srv, "DELETE", "/api/groups/" + g["id"])
            for i in ids:
                h.call(srv, "DELETE", "/api/chars/" + i)
