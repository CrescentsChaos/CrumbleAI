import json
import tempfile
import unittest
from pathlib import Path

from crumble import ambience
from crumble.llm import generate_reply
from crumble.story import wildlife as wl
from tests import helpers as h

REAL = Path(__file__).resolve().parent.parent / "data" / "animals" / "Animals.json"


def setUpModule():
    wl.DATA = REAL          # the test helpers move CRUMBLE_HOME to a temp folder; the animals come from the project's own database


FOREST = ["A camping trip deep in the northern Canadian forest. Night falls.", "We follow the forest trail past the campfire, deep in the woods at night."]


def starts(texts, place, indoors, period, n=600, setting="lively", scare="some", seed="s"):
    out = []
    for step in range(n):
        e = wl.encounter(step, seed, texts, place, indoors, period, setting, scare)
        if e and e["stage"] == 0:
            out.append(e)
    return out


class DataTests(unittest.TestCase):
    def test_the_database_loads_and_every_animal_has_what_an_encounter_needs(self):
        recs = wl.load()
        self.assertGreater(len(recs), 3000)
        for r in recs[:400]:
            self.assertTrue(r["habs"] and r["name"] and 1 <= r["tier"] <= 4)

    def test_sprite_names_follow_the_naming_rule(self):
        self.assertEqual(wl.sprite_name("American Black Bear"), "american_black_bear.png")
        self.assertEqual(wl.sprite_name("White's Bat"), "white_s_bat.png")
        self.assertEqual(wl.sprite_name("Long-tailed Cat"), "long_tailed_cat.png")

    def test_danger_is_judged_from_the_animal_not_the_name(self):
        t = {r["name"]: r["tier"] for r in wl.load()}
        self.assertEqual(t["Great White Shark"], 4)
        self.assertEqual(t["Nile Crocodile"], 4)
        self.assertEqual(t["Grizzly Bear"], 4)
        self.assertGreaterEqual(t["Indian Cobra"], 3)
        self.assertEqual(t["Tabby Cat"], 1)
        self.assertEqual(t["Orca"], 1)                 # whales and dolphins are awe, not terror
        self.assertEqual(t["Bottlenose Dolphin"], 1)


class PlaceTests(unittest.TestCase):
    def test_a_scene_is_read_into_habitats(self):
        self.assertIn("Jungle", wl.habitats(["x", "The jungle canopy drips."]))
        self.assertIn("Desert", wl.habitats(["x", "Dunes stretch to the horizon."]))
        self.assertIn("Cave", wl.habitats(["x", "They crawl deeper into the cave."]))
        self.assertEqual(wl.habitats(["x", "hi, how are you"]), {})

    def test_no_place_no_animal_and_texting_is_left_alone(self):
        self.assertEqual(starts(["x", "just chatting"], "", None, "afternoon"), [])

    def test_animals_live_where_they_live(self):
        for e in starts(FOREST, "the forest", False, "night"):
            a = e["animal"]
            self.assertTrue(set(a["habs"]) & {"Taiga", "Redwoods", "Mountain", "Jungle"}, a["name"])
            self.assertFalse(a["aq"], a["name"])       # nothing from the sea or a river on dry land
        sea = starts(["x", "The boat rocks on the open ocean as they dive."], "", False, "afternoon")
        self.assertTrue(sea)
        for e in sea:
            self.assertTrue(set(e["animal"]["habs"]) & {"Ocean", "Coastal", "Coral Reef", "Deep Sea", "Kelp Forest", "Frozen Ocean"})

    def test_day_animals_sleep_at_night_and_night_animals_not_at_noon(self):
        for e in starts(FOREST, "the forest", False, "night"):
            self.assertNotEqual(e["animal"]["active"], "day")
        for e in starts(FOREST, "the forest", False, "midday"):
            self.assertNotEqual(e["animal"]["active"], "night")

    def test_prehistoric_animals_need_a_prehistoric_story(self):
        for e in starts(FOREST, "the forest", False, "night"):
            self.assertFalse(e["animal"]["prehistoric"])
        seen = starts(["A prehistoric tale of dinosaurs", "We cross the plains and the grassland."], "", False, "afternoon", n=3000)
        self.assertTrue(any(e["animal"]["prehistoric"] for e in seen))

    def test_indoors_only_small_intruders_come(self):
        seen = starts(["x", "In the kitchen"], "the kitchen", True, "night")
        self.assertTrue(seen)
        for e in seen:
            self.assertLessEqual(e["animal"]["weight"], 12)
            self.assertTrue(e["indoors"])

    def test_a_named_region_keeps_foreign_animals_away(self):
        wl.load()
        items = wl.pool({"Savanna": 4}, "afternoon", False, "", False, False, "Our safari in Kenya, Africa")
        by = {r["name"]: w for r, w in items}
        foreign = [w for r, w in items if r["region"] and "africa" not in r["region"]]
        home = [w for r, w in items if "africa" in r["region"]]
        self.assertTrue(foreign and home)
        self.assertLess(max(foreign), max(home))


class EncounterTests(unittest.TestCase):
    def test_same_chat_position_same_encounter(self):
        a = [wl.encounter(s, "x", FOREST, "the forest", False, "night", "lively", "lots") for s in range(60)]
        b = [wl.encounter(s, "x", FOREST, "the forest", False, "night", "lively", "lots") for s in range(60)]
        self.assertEqual([e and (e["animal"]["name"], e["stage"]) for e in a], [e and (e["animal"]["name"], e["stage"]) for e in b])

    def test_an_encounter_holds_still_over_its_stages(self):
        seen = {}
        for s in range(200):
            e = wl.encounter(s, "y", FOREST, "the forest", False, "night", "lively", "some")
            if e:
                seen.setdefault(e["slot"], []).append((e["stage"], e["animal"]["name"], e["mood"]))
        self.assertTrue(seen)
        for slot, st in seen.items():
            self.assertEqual([x[0] for x in st], list(range(len(st))))      # stages run in order, one after another
            self.assertEqual(len({x[1] for x in st}), 1)                    # the same animal throughout
            self.assertEqual(len({x[2] for x in st}), 1)                    # and the same tone

    def test_moods_cover_wonder_fun_scares_and_terror(self):
        moods = {e["mood"] for e in starts(FOREST, "the forest", False, "night", n=1500, scare="lots")}
        self.assertEqual(moods, {"awe", "fun", "tense", "terror"})

    def test_gentle_never_terrifies_and_terror_is_a_real_danger(self):
        self.assertNotIn("terror", {e["mood"] for e in starts(FOREST, "the forest", False, "night", n=1500, scare="gentle")})
        for e in starts(FOREST, "the forest", False, "night", n=1500, scare="lots"):
            if e["mood"] == "terror":
                self.assertGreaterEqual(e["animal"]["tier"], 3)
            if e["mood"] in ("awe", "fun"):
                self.assertLessEqual(e["animal"]["tier"], 2)

    def test_off_means_off(self):
        self.assertEqual(starts(FOREST, "the forest", False, "night", setting="off"), [])

    def test_words_name_the_animal_and_keep_it_the_same(self):
        e = next(x for x in starts(FOREST, "the forest", False, "night", n=1500, scare="lots") if x["mood"] == "terror")
        head, line, note = wl.words(e, "{{char}}", "{{user}}")
        self.assertIn(e["animal"]["name"], head)
        self.assertIn("same", note)
        self.assertIn(e["animal"]["scientific_name"] if "scientific_name" in e["animal"] else e["animal"]["sci"], head)
        info = wl.info(e)
        self.assertEqual((info["name"], info["mood"]), (e["animal"]["name"], "terror"))
        self.assertTrue(info["sprite"] == "" or info["sprite"].startswith("/animals/sprites/"))

    def test_sprite_url_only_when_the_file_exists(self):
        old = wl.SPRITES
        with tempfile.TemporaryDirectory() as d:
            wl.SPRITES = Path(d)
            self.assertEqual(wl.sprite_url("White's Bat"), "")
            (Path(d) / "white_s_bat.png").write_bytes(b"png")
            self.assertEqual(wl.sprite_url("White's Bat"), "/animals/sprites/white_s_bat.png")
        wl.SPRITES = old


class PromptTests(unittest.TestCase):
    def run_turns(self, mode="story", wild="lively"):
        got = []
        char = {"id": "m1", "name": "Mira", "scenario": FOREST[0]}
        for n in range(1, 40):
            hist = []
            for i in range(n):
                hist.append({"role": "assistant", "content": FOREST[1], "name": "Mira"})
                hist.append({"role": "user", "content": FOREST[1]})
            fake = h.FakeLLM(["*steps closer.* Quiet."] * 4)
            h.install(fake)
            r = generate_reply({"char": char, "user": "Sam", "history": hist, "turn": len(hist),
                                "params": {"mode": mode, "think": False, "max_tokens": 200, "story": {"wildlife": wild, "scare": "lots"}}}, None)
            w = (r.get("world") or {}).get("wild")
            if w:
                got.append((w, " ".join(m["content"] for m in fake.calls[0])))
        return got

    def test_the_encounter_reaches_the_model_and_the_page(self):
        got = self.run_turns()
        self.assertTrue(got)
        for w, prompt in got:
            self.assertIn(w["name"], prompt)                       # the animal and its real facts are in the prompt
            self.assertIn("stage", prompt)
            self.assertTrue(w["mood"] in ("awe", "fun", "tense", "terror") and 1 <= w["stage"] <= w["of"])

    def test_texting_and_off_get_no_animals(self):
        self.assertEqual(self.run_turns(mode="text"), [])
        self.assertEqual(self.run_turns(wild="off"), [])

    def test_the_overview_for_the_page_never_spoils_the_next_encounter(self):
        from crumble import story
        hist = [{"role": "assistant" if i % 2 == 0 else "user", "content": FOREST[1]} for i in range(30)]
        for n in range(2, 30):
            self.assertNotIn("wild", story.overview([{"id": "m1", "name": "Mira", "scenario": FOREST[0]}], hist[:n], FOREST[0], {"wildlife": "lively"}))


class ServerTests(unittest.TestCase):
    def test_sprite_route_serves_files_and_refuses_everything_else(self):
        import crumble.server as srv
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        import threading
        with tempfile.TemporaryDirectory() as d:
            sp = Path(d) / "data" / "animals" / "sprites"
            sp.mkdir(parents=True)
            (sp / "red_fox.png").write_bytes(b"\x89PNG-fake")
            old = srv.ROOT
            srv.ROOT = Path(d)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.H)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            try:
                c = HTTPConnection("127.0.0.1", httpd.server_address[1])
                c.request("GET", "/animals/sprites/red_fox.png")
                r = c.getresponse()
                self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/png"))
                r.read()
                c.request("GET", "/animals/sprites/missing.png")
                r = c.getresponse()
                self.assertEqual(r.status, 404)
                r.read()
                c.request("GET", "/animals/sprites/..%2f..%2fAnimals.json")
                r = c.getresponse()
                self.assertNotEqual(r.status, 200)
                r.read()
                c.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                srv.ROOT = old


if __name__ == "__main__":
    unittest.main()
