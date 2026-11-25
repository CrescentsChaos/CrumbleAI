import base64
import tempfile
import unittest
from pathlib import Path

from crumble import places as pl

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\0" * 40).decode()
CHARS = {"mira": {"id": "mira", "name": "Mira Voss", "scenario": "Mira runs the lighthouse."}, "tom": {"id": "tom", "name": "Tom", "scenario": ""},
         "ana": {"id": "ana", "name": "Ana Lee", "scenario": ""}, "kai": {"id": "kai", "name": "Kai", "scenario": ""}}
get_char = CHARS.get


def card(**kw):
    b = {"name": "Harbour Café", "biome": "Shore", "description": "A salt-stained café above the water.", "atmosphere": "Gulls, coffee, creaking boards.",
         "objects": ["the brass telescope", "an old jukebox"], "activities": ["watch the boats"], "exits": ["The Pier", "Lighthouse Road"],
         "events": ["A fog horn sounds far out."], "history": "Built by smugglers.", "secrets": ["There is a trapdoor under the jukebox."],
         "characters": ["tom", "ana", "kai"]}
    b.update(kw)
    return pl.clean(b)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = pl.ROOT
        pl.ROOT = Path(self.tmp.name)

    def tearDown(self):
        pl.ROOT = self.old
        self.tmp.cleanup()


class StorageTests(Base):
    def test_clean_normalises_lists_and_keeps_only_what_fits(self):
        c = pl.clean({"name": "  X  ", "objects": "a\n\n  b  \nA\n" + "\n".join(f"item {i}" for i in range(80)), "characters": ["ok", "bad id!", "ok"]})
        self.assertEqual(c["name"], "X")
        self.assertEqual(c["objects"][:2], ["a", "b"])
        self.assertEqual(len(c["objects"]), 30)
        self.assertEqual(c["characters"], ["ok", "badid"])
        self.assertEqual(pl.clean({})["name"], "Unnamed place")

    def test_save_load_remove(self):
        c = pl.save(card())
        self.assertEqual(pl.get(c["id"])["name"], "Harbour Café")
        self.assertEqual([p["id"] for p in pl.load_all()], [c["id"]])
        self.assertTrue(pl.remove(c["id"]))
        self.assertIsNone(pl.get(c["id"]))
        self.assertEqual(pl.load_all(), [])

    def test_editing_keeps_what_was_not_sent(self):
        c = pl.save(card())
        e = pl.clean({"id": c["id"], "name": "Harbour Bar"}, c)
        self.assertEqual(e["name"], "Harbour Bar")
        self.assertEqual(e["objects"], c["objects"])
        self.assertEqual(e["characters"], c["characters"])

    def test_guests_never_see_secrets_events_or_history(self):
        v = pl.view(card(), admin=False)
        self.assertEqual((v["secrets"], v["events"], v["history"]), ([], [], ""))
        self.assertTrue(v["objects"] and v["description"])
        a = pl.view(card(), admin=True)
        self.assertTrue(a["secrets"] and a["events"] and a["history"])

    def test_pictures(self):
        c = pl.save(card())
        c = pl.save_image(c, "data:image/png;base64," + PNG)
        self.assertEqual(c["bg"], c["id"] + ".png")
        self.assertTrue(pl.image_file(c["bg"]).is_file())
        self.assertIn("/places/img/", pl.view(c)["bg_url"])
        with self.assertRaises(ValueError):
            pl.save_image(c, "data:image/png;base64," + base64.b64encode(b"not an image at all").decode())
        with self.assertRaises(ValueError):
            pl.save_image(c, "data:text/html;base64,PGI+")
        c2 = pl.clear_image(c)
        self.assertEqual(c2["bg"], "")
        self.assertIsNone(pl.image_file(c["bg"]))
        pl.save_image(c, "data:image/png;base64," + PNG)
        pl.remove(c["id"])
        self.assertEqual(list(pl.imgdir().glob("*")), [])

    def test_image_names_cannot_escape(self):
        for n in ("../x.png", "a/b.png", "x.php", "", "..\\x.png"):
            self.assertIsNone(pl.image_file(n))


class StoryTests(Base):
    def loc(self, **kw):
        c = pl.save(card(**kw))
        return pl.context({"id": c["id"], "since": 4}, 10, getter=get_char)

    def test_context_needs_a_real_card(self):
        self.assertIsNone(pl.context(None))
        self.assertIsNone(pl.context({"id": "nope"}, getter=get_char))

    def test_the_block_carries_the_card(self):
        loc = self.loc()
        p = pl.parts(loc, "{{char}}", "{{user}}", 10)
        t = "\n".join(p["lines"])
        for x in ("Harbour Café", "Shore", "salt-stained", "Gulls", "brass telescope", "watch the boats", "The Pier", "smugglers", "trapdoor", "Tom, Ana Lee, Kai"):
            self.assertIn(x, t)
        self.assertIn("Never state, hint at or hand over", t)
        self.assertNotIn("trapdoor", "\n".join(p["compact"]))
        self.assertNotIn("only just arrived", t)

    def test_arrival_is_noticed_for_one_turn(self):
        loc = self.loc()
        self.assertIn("only just arrived", "\n".join(pl.parts(loc, "C", "U", 5)["lines"]))
        self.assertNotIn("only just arrived", "\n".join(pl.parts(loc, "C", "U", 8)["lines"]))

    def test_an_empty_card_still_makes_a_sane_block(self):
        c = pl.save(pl.clean({"name": "Nowhere"}))
        loc = pl.context({"id": c["id"]}, 3, getter=get_char)
        t = "\n".join(pl.parts(loc, "C", "U", 3)["lines"])
        self.assertIn("Nowhere", t)
        self.assertNotIn("Hidden things", t)
        self.assertNotIn("Ways out", t)

    def test_events_come_from_the_card_last_two_turns_and_repeat_exactly(self):
        loc = self.loc(events=["A fog horn sounds.", "The lights flicker.", "A stranger waves."])
        hits = [t for t in range(2, 60) if pl.event(loc, t, "normal")]
        self.assertTrue(hits)
        for t in hits:
            self.assertEqual(pl.event(loc, t, "normal"), pl.event(loc, t, "normal"))
        self.assertEqual(pl.event(loc, 18, "normal"), pl.event(loc, 19, "normal"))
        self.assertEqual(pl.event(loc, 20, "normal"), "")
        self.assertEqual(pl.event(loc, 18, "off"), "")
        self.assertEqual(pl.event(loc, 18, "normal", skip=True), "")
        self.assertIn("Something happens here", pl.parts(loc, "C", "U", 18)["event"])

    def test_no_events_means_none(self):
        loc = self.loc(events=[])
        self.assertTrue(all(pl.event(loc, t, "lively") == "" for t in range(80)))

    def test_climate_text_names_the_place_for_the_scene_readers(self):
        loc = self.loc(biome="Jungle")
        self.assertIn("Jungle", pl.climate_text(loc))
        self.assertEqual(pl.note(loc)["kind"], "setting")
        self.assertEqual(pl.climate_text(None), "")

    def test_standalone_keeps_the_place_when_the_story_engine_is_off(self):
        out = pl.standalone(self.loc(), "C", "U", 6)
        self.assertIn("Harbour Café", out["block"])
        self.assertEqual(pl.standalone(None, "C", "U", 6), {})

    def test_narrator_lines(self):
        t = "\n".join(pl.narrator_lines(self.loc(), 6))
        self.assertIn("brass telescope", t)
        self.assertNotIn("trapdoor", t)


class CalledTests(unittest.TestCase):
    def test_speaking_to_someone_counts(self):
        names = ["Mira Voss", "Tom"]
        for t in ("Mira, are you there?", "hey Mira", "*waves* Hi Tom!", "@Tom come over", "Can you help me, Mira?", "ask Tom", "Tom: what now?"):
            self.assertTrue(pl.called(t, names), t)

    def test_talking_about_someone_does_not(self):
        names = ["Mira Voss", "Tom"]
        for t in ("Did you see Mira today?", "I think Tom is mean", "Mirage over the sea", "Tomorrow we leave", "Her name is Mira Voss and she lives here"):
            self.assertFalse(pl.called(t, names), t)

    def test_full_names_work(self):
        self.assertEqual(pl.called("Hello Mira Voss, good evening", ["Mira Voss"]), ["Mira Voss"])


class VisitTests(Base):
    def setUp(self):
        super().setUp()
        self.c = card()
        self.chars = {k: v for k, v in CHARS.items() if k in self.c["characters"]}

    def v(self, turn=12, text="the tea is good", setting="lively", hist=(), **kw):
        kw.setdefault("routines", False)
        return pl.visit(self.c, "mira", self.chars, list(hist), turn, text, setting, "chat1", **kw)

    def test_off_and_empty(self):
        self.assertIsNone(self.v(setting="off"))
        self.assertIsNone(pl.visit(dict(self.c, characters=[]), "mira", {}, [], 12, "", "lively", "s"))

    def test_calling_by_name_always_works(self):
        r = self.v(turn=1, text="Ana, could you come over?", setting="rare")
        self.assertEqual((r["id"], r["why"]), ("ana", "called"))

    def test_called_even_in_a_sad_moment(self):
        self.assertEqual(self.v(turn=7, text="Ana, please. I'm crying", setting="rare")["why"], "called")

    def test_force_from_the_panel(self):
        self.assertEqual(self.v(turn=1, text="*waves*", force="kai")["id"], "kai")
        self.assertIsNone(self.v(turn=1, force="nobody"))
        self.assertIsNone(self.v(turn=1, force="kai", dead=["kai"]))

    def test_arrivals_follow_the_setting_and_never_repeat_the_slot_wrongly(self):
        counts = {}
        for s in ("rare", "normal", "lively"):
            counts[s] = sum(1 for t in range(3, 400) if self.v(turn=t, setting=s) )
        self.assertLess(counts["rare"], counts["normal"])
        self.assertLess(counts["normal"], counts["lively"])
        self.assertGreater(counts["rare"], 5)
        for t in range(3, 400):
            r = self.v(turn=t, setting="lively")
            if r:
                self.assertEqual((r["why"], t % 6), ("arrive", 0))

    def test_same_position_same_visitor(self):
        for t in range(3, 100):
            self.assertEqual(self.v(turn=t), self.v(turn=t))

    def test_nobody_arrives_in_a_grieving_or_leaving_moment(self):
        for t in range(3, 120):
            self.assertIsNone(self.v(turn=t, text="goodbye, I have to go"))

    def test_the_main_character_and_the_dead_never_visit(self):
        for t in range(3, 300):
            r = self.v(turn=t, dead=["tom", "ana"])
            if r:
                self.assertEqual(r["id"], "kai")
        c = dict(self.c, characters=["mira"])
        self.assertIsNone(pl.visit(c, "mira", {"mira": CHARS["mira"]}, [], 12, "", "lively", "s"))

    def test_someone_in_the_scene_chimes_in_now_and_then_then_drifts_off(self):
        h = [{"role": "assistant", "content": "hi", "cid": "tom", "pl": self.c["id"]}, {"role": "user", "content": "hello"}]
        r = [self.v(turn=t, hist=h, text="and then?") for t in range(3, 80)]
        self.assertTrue(any(x and x["why"] == "chime" and x["id"] == "tom" for x in r))
        self.assertTrue(any(x is None for x in r))
        old = h + [{"role": "user", "content": "x"}] * 8
        self.assertTrue(all(x is None or x["why"] != "chime" for x in (self.v(turn=t, hist=old) for t in range(3, 80))))

    def test_someone_from_another_place_is_not_in_this_scene(self):
        h = [{"role": "assistant", "content": "hi", "cid": "tom", "pl": "elsewhere"}]
        self.assertTrue(all(x is None or x["why"] != "chime" for x in (self.v(turn=t, hist=h) for t in range(3, 80))))

    def test_the_clock_never_keeps_a_resident_out(self):     # a vigilante is up at 3 AM: only the scene and the model decide, never a timetable
        got = {r["id"] for r in (self.v(turn=t, routines=True, sim={"hour": 3}) for t in range(3, 300)) if r}
        self.assertEqual(got, {"tom", "ana", "kai"})

    def test_not_right_after_arriving_at_the_place(self):
        self.assertIsNone(self.v(turn=12, since=11))


class StageTests(unittest.TestCase):
    def base(self, **kw):
        b = {"char": CHARS["mira"], "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}], "place": {"id": "x"}}
        b.update(kw)
        return b

    def test_an_ordinary_chat_is_left_alone(self):
        b = self.base()
        pl.stage(b, get_char)
        self.assertNotIn("grp", b)
        self.assertNotIn("cid", b["history"][1])

    def test_groups_are_left_alone(self):
        b = self.base(group="g1")
        pl.stage(b, get_char)
        self.assertNotIn("grp", b)

    def test_a_chat_with_visitors_becomes_a_small_group_for_the_main_character(self):
        b = self.base()
        b["history"].append({"role": "assistant", "content": "oh, hey", "cid": "tom", "name": "Tom"})
        pl.stage(b, get_char)
        self.assertEqual([m["id"] for m in b["grp"]["members"]], ["mira", "tom"])
        self.assertEqual((b["history"][1]["cid"], b["history"][1]["name"]), ("mira", "Mira Voss"))
        self.assertEqual(b["history"][2]["cid"], "tom")
        self.assertEqual(b["grp"]["scenario"], "Mira runs the lighthouse.")
        self.assertEqual(b["cue"], {})
        self.assertNotIn("visit", b)

    def test_a_visitors_turn(self):
        b = self.base(char=CHARS["ana"], visit={"main": "mira", "why": "arrive"})
        pl.stage(b, get_char)
        self.assertEqual([m["id"] for m in b["grp"]["members"]], ["mira", "ana"])
        self.assertEqual(b["grp"]["scenario"], "Mira runs the lighthouse.")
        self.assertEqual(b["visit"]["main"], "Mira Voss")
        self.assertEqual(b["visit"]["why"], "arrive")
        self.assertEqual(b["history"][1]["cid"], "mira")

    def test_a_bad_visit_is_ignored(self):
        for v in ({"main": "nobody", "why": "arrive"}, {"main": "ana", "why": "arrive"}, {"main": "", "why": "x"}):
            b = self.base(char=CHARS["ana"], visit=v)
            pl.stage(b, get_char)
            self.assertNotIn("visit", b)
            self.assertNotIn("grp", b)

    def test_unknown_visitors_in_old_history_are_skipped(self):
        b = self.base()
        b["history"].append({"role": "assistant", "content": "...", "cid": "ghost"})
        pl.stage(b, get_char)
        self.assertNotIn("grp", b)

    def test_tails(self):
        mk = lambda why: pl.visit_tail({"visit": {"why": why, "main": "Mira Voss", "place": "Harbour Café"}}, "{{char}}", "{{user}}")
        self.assertIn("called", mk("called"))
        self.assertIn("has just turned up", mk("arrive"))
        self.assertIn("already part of this scene", mk("chime"))
        for why in ("called", "arrive", "chime"):
            self.assertIn("Mira Voss", mk(why))
            self.assertIn("Harbour Café", mk(why))
            self.assertIn("Write only {{char}}'s next message", mk(why))
            self.assertIn("not staff and not a helper", mk(why))      # nobody who lives there greets a visitor like an assistant


if __name__ == "__main__":
    unittest.main()


class PlacesPageWiring(unittest.TestCase):
    """The Places page, its full-page editor, the people picker and the chat background are wired into the bundled page."""

    @classmethod
    def setUpClass(cls):
        from crumble import web
        cls.html = web.page_bytes().decode("utf-8")

    def test_page_sections_and_nav(self):
        for needle in ("data-t=places", "<section id=places", "<section id=pedit", 'id=pview class=modal', 'id=ps2', 'id=pesave'):
            self.assertIn(needle, self.html)

    def test_tab_knows_the_new_pages(self):
        self.assertIn("'places','pedit'", self.html)
        self.assertIn("placesPage()", self.html)

    def test_picker_is_used_for_places_and_groups(self):
        self.assertIn("mpMount('#pe-mem','pm'", self.html)
        self.assertIn("mpMount('#gmem','ge'", self.html)
        self.assertNotIn("data-gm=", self.html)         # the group editor no longer lists every character as a checkbox
        self.assertIn("MP_SHOW=6", self.html)           # only a few matches are ever shown

    def test_background_covers_the_whole_chat(self):
        self.assertIn("#chat[data-pbg]::before", self.html)
        self.assertIn("ch.dataset.pbg='1'", self.html)
        self.assertNotIn("L.style.backgroundImage=v", self.html)   # no longer painted on the message log only

    def test_old_modal_editor_is_gone(self):
        self.assertNotIn("plmodal", self.html)
