"""The place card is the truth about where the chat stands (scene reader, activities, summary), a character can start in a place,
and who you are is kept on the host."""
import unittest

from crumble import ambience, context, memory, places as pl, profile
from crumble.story import doing

from . import helpers as h

SCENARIO = "Miquella waits alone in the apartment."
GATE = {"name": "Gate of Divinity", "biome": "Ruins", "description": "A vast stone gate wrapped in grey mist.", "atmosphere": "Weathered carvings, drifting mist, a hush."}


def loc(since=0, **kw):
    return {"card": pl.clean(dict(GATE, **kw)), "since": since, "people": [], "ids": []}


def msg(role, text):
    return {"role": role, "content": text}


class SceneReader(unittest.TestCase):
    def test_apartment_in_the_scenario_does_not_override_the_place_card(self):
        a = ambience.derive([msg("assistant", "Mist rolls in.")], SCENARIO, [pl.note(loc())])
        self.assertEqual(a["place"]["name"], "Gate of Divinity")
        self.assertNotIn("apartment", a["place"]["name"])

    def test_without_a_card_the_words_still_decide(self):
        self.assertEqual(ambience.derive([], SCENARIO)["place"]["name"], "the apartment")

    def test_words_in_the_chat_cannot_rename_a_card_place(self):
        a = ambience.derive([msg("user", "We sit on a bench by the park.")], "", [pl.note(loc())])
        self.assertEqual(a["place"]["name"], "Gate of Divinity")

    def test_messages_before_the_move_belong_to_the_old_place(self):
        hist = [msg("assistant", "We are in the kitchen."), msg("user", "Let's go."), msg("assistant", "On our way.")]
        self.assertEqual(ambience.derive(hist, "", [pl.note(loc(since=2))])["place"]["name"], "Gate of Divinity")
        self.assertEqual(ambience.derive(hist[:2], "")["place"]["name"], "the kitchen")     # no card (the page drops the entry when the chat is rewound past the move)
        self.assertEqual(ambience.derive(hist + [msg("user", "Back in the kitchen again.")], "", [pl.note(loc(since=2))])["place"]["name"], "Gate of Divinity")

    def test_indoors_comes_from_the_card_and_unknown_is_not_claimed(self):
        self.assertIs(ambience.derive([], "", [pl.note(loc(biome="Forest", description="Tall pines."))])["indoors"], False)
        self.assertIs(ambience.derive([], "", [pl.note(loc(biome="Tavern", description="Warm and loud."))])["indoors"], True)
        a = ambience.derive([], "", [pl.note(loc(biome="", description="A gate."))])
        self.assertIsNone(a["indoors"])
        self.assertNotIn("(outdoors)", ambience.block(a))
        self.assertNotIn("(indoors)", ambience.block(a))

    def test_note_is_still_a_setting_note(self):
        self.assertEqual(pl.note(loc())["kind"], "setting")


class Activities(unittest.TestCase):
    def test_the_question_ties_everyone_to_the_place(self):
        q = doing.ask([{"id": "m", "name": "Miquella"}], pl.clean(GATE))
        self.assertIn("THERE", q)
        self.assertIn("here=false", q)

    def test_a_story_place_without_a_card_is_given_too(self):
        q = doing.ask([{"id": "m", "name": "Miquella"}], None, setting="the kitchen")
        self.assertIn("PLACE: the kitchen.", q)
        self.assertIn("THERE", q)

    def test_nothing_is_said_about_a_place_when_there_is_none(self):
        self.assertNotIn("THERE", doing.ask([{"id": "m", "name": "Miquella"}], None))


class Summary(unittest.TestCase):
    def test_location_is_pinned_over_a_stale_one(self):
        t = "SETTING & STATE\nLocation: the apartment\nCurrent State: talking\n\nPIVOTAL MOMENTS\n- a promise"
        out = memory.pin_location(t, "Gate of Divinity")
        self.assertIn("Location: Gate of Divinity", out)
        self.assertNotIn("apartment", out)
        self.assertIn("Current State: talking", out)

    def test_location_is_added_when_the_model_left_it_out(self):
        self.assertTrue(memory.pin_location("Just some prose.", "Gate of Divinity").startswith("SETTING & STATE\nLocation: Gate of Divinity\n"))
        self.assertIn("Location: Gate of Divinity", memory.pin_location("SETTING & STATE\nCurrent State: x", "Gate of Divinity"))

    def test_no_place_changes_nothing(self):
        self.assertEqual(memory.pin_location("Location: the pier", ""), "Location: the pier")

    def test_summarize_asks_for_and_keeps_the_place(self):
        fake = h.install(h.FakeLLM())
        out = memory.summarize({"char": {"name": "Miquella"}, "user": "Crescent", "place_name": "Gate of Divinity",
                                "history": [msg("user", "Where is he?"), msg("assistant", "I do not know.")], "summary": "Location: the apartment"})
        self.assertIn("Gate of Divinity", h.ptxt(fake.calls[-1]))
        self.assertIn("Location: Gate of Divinity", out)

    def test_recap_says_where_the_story_is_now(self):
        s = "SETTING & STATE\nLocation: the apartment\nCurrent State: talking"
        self.assertIn("Right now the story is at Gate of Divinity.", context.recap(s, "M", "C", place="Gate of Divinity"))
        self.assertNotIn("apartment", context.recap(s, "M", "C", place="Gate of Divinity"))
        self.assertIn("takes place at the apartment", context.recap(s, "M", "C"))


class Profile(unittest.TestCase):
    HOST, G1, G2 = {"role": "admin", "uid": ""}, {"role": "guest", "uid": "aa11"}, {"role": "guest", "uid": "bb22"}

    def test_saved_and_read_back(self):
        profile.save(self.HOST, {"uname": "Crescent", "persona": "A wanderer with a lute."})
        self.assertEqual(profile.load(self.HOST)["uname"], "Crescent")
        self.assertEqual(profile.load(self.HOST)["persona"], "A wanderer with a lute.")

    def test_a_missing_field_never_wipes_a_saved_one(self):
        profile.save(self.HOST, {"uname": "Crescent", "ugear": "lute"})
        profile.save(self.HOST, {"persona": "Hi"})
        self.assertEqual(profile.load(self.HOST)["ugear"], "lute")
        profile.save(self.HOST, {"ugear": ""})      # an emptied field is a real change
        self.assertEqual(profile.load(self.HOST)["ugear"], "")

    def test_guests_are_kept_apart_from_the_host_and_each_other(self):
        profile.save(self.G1, {"uname": "Ana"})
        profile.save(self.G2, {"uname": "Bo"})
        profile.save(self.HOST, {"uname": "Host"})
        self.assertEqual((profile.load(self.G1)["uname"], profile.load(self.G2)["uname"], profile.load(self.HOST)["uname"]), ("Ana", "Bo", "Host"))

    def test_only_known_short_text_is_kept(self):
        r = profile.save(self.HOST, {"uname": "x" * 500, "evil": "1", "persona": None, "ustats": 12})
        self.assertEqual(len(r["uname"]), 60)
        self.assertNotIn("evil", r)
        self.assertEqual(r["ustats"], "12")

    def test_a_guest_without_an_id_has_nowhere_to_save(self):
        self.assertEqual(profile.save({"role": "guest", "uid": ""}, {"uname": "x"}), {})


class Settings(unittest.TestCase):
    HOST, G1 = {"role": "admin", "uid": ""}, {"role": "guest", "uid": "cc33"}

    def test_options_are_saved_and_read_back(self):
        profile.save_settings(self.HOST, {"U": {"theme": "dark", "fs": 17, "story": True, "defTheme": {"a": [1, 2]}}, "P": {"temperature": 0.7}})
        r = profile.load_settings(self.HOST)
        self.assertEqual((r["U"]["fs"], r["U"]["theme"], r["P"]["temperature"], r["U"]["defTheme"]["a"]), (17, "dark", 0.7, [1, 2]))

    def test_guests_have_their_own_options(self):
        profile.save_settings(self.G1, {"U": {"fs": 12}, "P": {}})
        self.assertEqual(profile.load_settings(self.G1)["U"]["fs"], 12)
        self.assertNotEqual(profile.load_settings(self.HOST)["U"].get("fs"), 12)

    def test_junk_is_dropped_and_size_is_bounded(self):
        r = profile.save_settings(self.HOST, {"U": {"ok": 1, "bad": object()}, "P": "nope"})
        self.assertEqual(r["U"]["ok"], 1)
        self.assertIsNone(r["U"]["bad"])
        self.assertEqual(r["P"], {})
        big = {"U": {f"k{i}": "x" * 20000 for i in range(20)}, "P": {}}
        self.assertEqual(profile.save_settings(self.HOST, big)["U"].get("ok"), 1)      # too big: the saved copy stays


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = h.serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_profile_over_http(self):
        st, r = h.call(self.srv, "POST", "/api/profile", {"uname": "Crescent", "persona": "Tall."})
        self.assertEqual(st, 200)
        self.assertEqual(h.call(self.srv, "GET", "/api/profile")[1]["profile"]["uname"], "Crescent")

    def test_settings_over_http(self):
        self.assertEqual(h.call(self.srv, "POST", "/api/settings", {"U": {"fs": 19}, "P": {"top_k": 30}})[0], 200)
        r = h.call(self.srv, "GET", "/api/settings")[1]
        self.assertEqual((r["U"]["fs"], r["P"]["top_k"]), (19, 30))

    def test_start_place_is_saved_only_for_a_real_place(self):
        st, p = h.call(self.srv, "POST", "/api/places", dict(GATE))
        self.assertEqual(st, 200)
        c = h.call(self.srv, "POST", "/api/chars", {"name": "Miquella", "start_place": p["id"]})[1]
        self.assertEqual(c["start_place"], p["id"])
        c2 = h.call(self.srv, "POST", "/api/chars", {"id": c["id"], "name": "Miquella", "start_place": "gone123"})[1]
        self.assertEqual(c2["start_place"], "")
        self.assertEqual(h.call(self.srv, "POST", "/api/chars", {"name": "Plain"})[1]["start_place"], "")

    def test_guests_can_see_where_a_character_starts(self):
        from crumble.storage import pub
        self.assertEqual(pub({"id": "x", "name": "X", "start_place": "abc"})["start_place"], "abc")

    def test_summarize_endpoint_resolves_the_place_from_its_id(self):
        h.install(h.FakeLLM())
        p = h.call(self.srv, "POST", "/api/places", dict(GATE))[1]
        r = h.call(self.srv, "POST", "/api/summarize", {"char": {"name": "Miquella"}, "user": "C", "place": {"id": p["id"], "since": 0},
                                                         "history": [msg("user", "hi"), msg("assistant", "hello")], "summary": ""})[1]
        self.assertIn("Location: Gate of Divinity", r["summary"])

    def test_page_carries_the_new_wiring(self):
        page = h.call(self.srv, "GET", "/")[1]
        for needle in ("profileLoad", "'/api/profile'", "placeSpecAt(upto)", "start_place", "settingsLoad", "doingAnywhere", "id=cstart", "pid:p?p.id:''"):
            self.assertIn(needle, page)


if __name__ == "__main__":
    unittest.main()
