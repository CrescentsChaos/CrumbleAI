"""What people are doing right now is made up by the model for the moment (never a timetable); places are visited as scenes of their own."""
import json
import tempfile
import unittest
from pathlib import Path

import crumble.server      # noqa: F401  (imported first: it binds storage.get_char by name, and these tests swap that function)
from crumble import places as pl, presence, story
from crumble.llm import generate_reply
from crumble.story import doing
from tests import helpers as h

BAT = {"id": "bat", "name": "Batman", "occupation": "vigilante", "description": "The Dark Knight of Gotham. Works at night.", "personality": "grim, terse, suspicious"}
ALF = {"id": "alf", "name": "Alfred", "occupation": "butler", "description": "Loyal butler.", "personality": "dry, patient"}
CHARS = {"bat": BAT, "alf": ALF, "kid": {"id": "kid", "name": "Robin", "occupation": "student"}}


def card(**kw):
    b = {"name": "The Cave", "biome": "Cave", "description": "A vast cave under the manor.", "atmosphere": "Bats, damp stone, humming screens.",
         "characters": ["bat", "alf", "kid"]}
    b.update(kw)
    return pl.clean(b)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old, pl.ROOT = pl.ROOT, Path(self.tmp.name)
        import crumble.storage as st, crumble.presence as pr
        self.get_old, self.st_old = pr.get_char, st.get_char
        pr.get_char = st.get_char = CHARS.get
        self.c = pl.save(card())

    def tearDown(self):
        import crumble.storage as st, crumble.presence as pr
        pr.get_char, st.get_char = self.get_old, self.st_old
        pl.ROOT = self.old


class ParseTests(unittest.TestCase):
    def test_a_clean_answer_is_read(self):
        t = json.dumps({"people": [{"id": "bat", "here": True, "doing": "cleaning a grapnel gun by the monitors", "state": "busy", "stance": "Does not look up."}]})
        r = doing.parse(t, ["bat", "alf"])
        self.assertEqual(list(r), ["bat"])
        self.assertEqual((r["bat"]["state"], r["bat"]["free"]), ("busy", doing.STATES["busy"]))
        self.assertTrue(r["bat"]["here"])

    def test_junk_is_bounded_and_unknown_ids_dropped(self):
        t = json.dumps({"people": [{"id": "zzz", "doing": "x"}, {"id": "bat", "doing": "y" * 900, "state": "dancing", "stance": "z" * 900, "here": "false", "away": "on the roof"}]})
        r = doing.parse(t, ["bat"])
        self.assertEqual(list(r), ["bat"])
        self.assertLessEqual(len(r["bat"]["doing"]), 200)
        self.assertLessEqual(len(r["bat"]["stance"]), 220)
        self.assertFalse(r["bat"]["here"])
        self.assertEqual(r["bat"]["free"], 0.0)
        self.assertEqual(r["bat"]["away"], "on the roof")

    def test_names_work_instead_of_ids_and_garbage_gives_nothing(self):
        self.assertEqual(list(doing.parse('{"people":[{"name":"bat","doing":"x"}]}', ["bat"])), ["bat"])
        self.assertEqual(doing.parse("I cannot do that.", ["bat"]), {})
        self.assertEqual(doing.parse("", ["bat"]), {})

    def test_the_page_is_trusted_with_short_plain_text_only(self):
        r = doing.clean_map({"bat": {"doing": "a" * 5000, "state": "free", "x": "<script>"}, "n" * 99: "nope"})
        self.assertLessEqual(len(r["bat"]["doing"]), 200)
        self.assertNotIn("x", r["bat"])
        self.assertEqual(doing.clean_map("nonsense"), {})


class QuestionTests(unittest.TestCase):
    def test_the_question_forbids_a_timetable_and_an_assistant(self):
        q = doing.ask([BAT, ALF], card(), {"clock": "Tuesday, around 3:00 AM (night)"}, "rain", ["You: hello"], "", None, "Sam")
        for need in ("no timetable", "nobody sleeps because it is night", "NOT service staff", "Tuesday, around 3:00 AM", "vigilante", "WEATHER: rain", "JSON"):
            self.assertIn(need, q)
        self.assertIn("away", q)       # people can be out of the place

    def test_no_place_no_presence_question(self):
        q = doing.ask([BAT], None, {"clock": "noon"}, "", [], "", None, "Sam")
        self.assertNotIn("not always", q)
        self.assertNotIn("PLACE:", q)

    def test_the_cache_follows_story_time_place_and_turns(self):
        sim = {"hour": 3.0, "dayn": 1}
        e = {"key": doing.key("p", sim, 5), "turn": 5}
        self.assertFalse(doing.stale(e, "p", sim, 6))
        self.assertTrue(doing.stale(e, "p", {"hour": 6.0, "dayn": 1}, 6))       # time moved on
        self.assertTrue(doing.stale(e, "q", sim, 6))                             # another place
        self.assertTrue(doing.stale(e, "p", sim, 5 + doing.HELD))                # a long time in turns
        self.assertTrue(doing.stale(None, "p", sim, 1))


class PromptTests(Base):
    def reply(self, speaker, grp_members, items, replies=("Hm.",), hist=None, present_scene=True):
        fake = h.install(h.FakeLLM(list(replies)))
        grp = dict(name="The Cave", scenario=self.c["description"], members=grp_members, narrator=True)
        b = {"char": speaker, "grp": grp, "user": "Sam", "history": hist or [{"role": "user", "content": "*I step inside.*"}], "state": {"mood": "calm"},
             "place": {"id": self.c["id"], "since": 1}, "doing": items, "cue": {"why": "named", "by": "Sam"},
             "params": {"mode": "story", "think": False, "max_tokens": 200, "story": {}}}
        r = generate_reply(b, None)
        return fake, r

    def test_batman_is_not_put_to_bed_at_night(self):
        items = {"bat": {"here": True, "doing": "rebuilding a grapnel gun at the monitors, awake and alert", "state": "busy", "stance": "Notices you at once and says nothing."}}
        hist = [{"role": "assistant", "content": "Tuesday, 3 AM. Rain hammers the manor.", "cid": "__narrator__", "name": "Narrator"}, {"role": "user", "content": "*I step inside.*"}]
        fake, r = self.reply(BAT, [BAT], items, hist=hist)
        sysm = h.ptxt(fake.calls[0])
        self.assertIn("rebuilding a grapnel gun", sysm)
        self.assertIn("Notices you at once", sysm)
        self.assertNotIn("when they sleep", sysm)
        self.assertNotIn("wants to get back to sleep", sysm)
        self.assertNotIn("usual rhythm", sysm)

    def test_a_resident_is_not_staff(self):
        items = {"alf": {"here": True, "doing": "polishing silver", "state": "busy", "stance": "Dry. Gives nothing away."}}
        fake, r = self.reply(ALF, [ALF], items)
        sysm = h.ptxt(fake.calls[0])
        self.assertIn("does not greet", sysm)
        self.assertIn("being friendly is not the default", sysm)

    def test_who_is_in_and_who_is_out_reaches_the_scene(self):
        items = {"bat": {"here": True, "doing": "at the monitors", "state": "busy"}, "alf": {"here": False, "away": "upstairs asleep"}, "kid": {"here": False, "away": "at school"}}
        fake, r = self.reply(BAT, [BAT], items)
        sysm = h.ptxt(fake.calls[0])
        self.assertIn("Here right now", sysm)
        self.assertIn("Batman: at the monitors", sysm)
        self.assertIn("Not here at the moment", sysm)
        self.assertIn("Alfred (upstairs asleep)", sysm)

    def test_nobody_in_means_the_visitor_is_alone(self):
        items = {i: {"here": False, "away": "out"} for i in ("bat", "alf", "kid")}
        fake = h.install(h.FakeLLM(["The cave hums."]))
        from crumble.rp.narrator import NARRATOR
        b = {"char": NARRATOR, "grp": dict(name="The Cave", scenario="x", members=[], narrator=True), "user": "Sam", "history": [{"role": "user", "content": "*I step inside.*"}],
             "state": {}, "place": {"id": self.c["id"], "since": 1}, "doing": items, "cue": {"why": "narrate"}, "params": {"mode": "story", "think": False, "max_tokens": 200}}
        generate_reply(b, None)
        self.assertIn("Nobody who belongs here is around", h.ptxt(fake.calls[0]))

    def test_no_answer_means_no_claim_at_all(self):
        fake, r = self.reply(BAT, [BAT], {})
        sysm = h.ptxt(fake.calls[0])
        self.assertNotIn("Right now Batman is", sysm)
        self.assertNotIn("when they sleep", sysm)
        self.assertNotIn("The hour in the body", sysm.split("[Daily life")[0])
        self.assertIn("not always in", sysm)

    def test_the_authors_own_routine_is_a_hint_never_a_command(self):
        c = dict(BAT, routine="Weekdays: up 6:30, bakery 7-3, in bed by 11.")
        fake = h.install(h.FakeLLM(["Hm."]))
        generate_reply({"char": c, "user": "Sam", "history": [{"role": "assistant", "content": "Monday, 3 AM."}, {"role": "user", "content": "hey"}], "state": {},
                        "params": {"mode": "story", "think": False, "max_tokens": 200}}, None)
        sysm = h.ptxt(fake.calls[0])
        self.assertIn("the author wrote", sysm)
        self.assertIn("up to the scene", sysm)


class SceneTests(Base):
    def test_a_visit_is_a_group_made_from_the_place(self):
        g = pl.scene_group(pl.scene_id(self.c["id"]))
        self.assertTrue(g["narrator"])
        self.assertEqual(g["members"], ["bat", "alf", "kid"])
        self.assertEqual(g["name"], "The Cave")
        self.assertTrue(pl.is_scene(g["id"]))
        self.assertIsNone(pl.scene_group("pl_missing"))
        self.assertIsNone(pl.scene_group("grp_abc"))
        self.assertFalse(pl.is_scene("pl_"))

    def test_only_those_present_can_speak(self):
        mem = [BAT, ALF, CHARS["kid"]]
        self.assertEqual([m["id"] for m in pl.only_present(mem, ["alf"])], ["alf"])
        self.assertEqual(pl.only_present(mem, []), [])
        self.assertEqual(pl.only_present(mem, None), mem)

    def test_the_cast_is_who_lives_there_and_does_not_open_a_chat(self):
        # adding characters to a card changes who may be around; it never starts a conversation with them
        self.assertEqual(pl.visit(self.c, "bat", {}, [], 12, "hi", "lively", "s"), None)


class PresenceTests(Base):
    def test_the_model_decides_who_is_in(self):
        asked = []

        def call(prompt):
            asked.append(prompt)
            return json.dumps({"people": [{"id": "bat", "here": True, "doing": "oiling the batmobile", "state": "busy", "stance": "Wary."},
                                          {"id": "alf", "here": False, "away": "in the kitchen upstairs"},
                                          {"id": "kid", "here": False, "away": "at school"}]})
        r = presence.run({"place": {"id": self.c["id"]}, "history": [{"role": "assistant", "content": "Tuesday, 3 AM."}], "turn": 1, "arriving": True, "user": "Sam"}, call)
        self.assertTrue(r["ai"])
        self.assertTrue(r["people"]["bat"]["here"])
        self.assertEqual(r["people"]["alf"]["away"], "in the kitchen upstairs")
        self.assertEqual(len(asked), 1)
        self.assertIn("Tuesday", asked[0])
        self.assertIn("has just arrived", asked[0])

    def test_a_still_good_answer_is_not_asked_again(self):
        calls = []
        call = lambda p: calls.append(p) or json.dumps({"people": [{"id": "bat", "here": True, "doing": "x"}]})
        b = {"place": {"id": self.c["id"]}, "history": [{"role": "assistant", "content": "Tuesday, 3 AM."}], "turn": 2}
        r1 = presence.run(b, call)
        r2 = presence.run(dict(b, turn=3, have={"key": r1["key"], "turn": r1["turn"], "ids": r1["ids"]}), call)
        self.assertTrue(r2.get("fresh"))
        self.assertEqual(len(calls), 1)
        r3 = presence.run(dict(b, turn=3, have={"key": r1["key"], "turn": r1["turn"], "ids": r1["ids"]}, force=True), call)
        self.assertNotIn("fresh", r3)
        self.assertEqual(len(calls), 2)
        r4 = presence.run(dict(b, history=[{"role": "assistant", "content": "Tuesday, 3 AM."}, {"role": "user", "content": "*waits until 7 AM*"}] , turn=4,
                               have={"key": r1["key"], "turn": r1["turn"], "ids": r1["ids"]}), call)
        self.assertNotIn("fresh", r4)

    def test_without_a_usable_answer_nothing_is_invented_and_someone_is_in(self):
        for call in (lambda p: "I cannot do that.", lambda p: (_ for _ in ()).throw(RuntimeError("boom"))):
            r = presence.run({"place": {"id": self.c["id"]}, "history": [], "turn": 0, "seed": "s"}, call)
            self.assertFalse(r["ai"])
            here = [i for i, it in r["people"].items() if it["here"]]
            self.assertTrue(1 <= len(here) < 3 or len(here) == 2)
            self.assertTrue(all(it["doing"] == "" and it["stance"] == "" for it in r["people"].values()))
            again = presence.run({"place": {"id": self.c["id"]}, "history": [], "turn": 0, "seed": "s"}, call)
            self.assertEqual(r["people"], again["people"])      # the same visit gives the same answer

    def test_a_big_cast_rotates_and_the_rest_keep_their_last_answer(self):
        many = {f"p{i}": {"id": f"p{i}", "name": f"P{i}"} for i in range(12)}
        old = presence.get_char
        presence.get_char = lambda i: many.get(i) or CHARS.get(i)
        try:
            c = pl.save(card(name="Hall", characters=list(many)))
            asked_ids = []

            def call(prompt):
                ids = [x for x in many if f"id {x}," in prompt]
                asked_ids.append(ids)
                return json.dumps({"people": [{"id": i, "here": True, "doing": "x"} for i in ids]})
            r = presence.run({"place": {"id": c["id"]}, "history": [], "turn": 0, "prev": {"p11": {"here": True, "doing": "kept"}}}, call)
            self.assertEqual(len(asked_ids[0]), presence.MAX_ASK)
            self.assertEqual(len(r["people"]), 12)
            for i in many:
                if i not in asked_ids[0]:
                    self.assertTrue(r["people"][i]["here"] is (i == "p11"))
        finally:
            presence.get_char = old


class ServerTests(Base):
    def test_the_visit_api(self):
        srv = h.serve()
        try:
            h.install(h.FakeLLM(track={"people": [{"id": "bat", "here": True, "doing": "watching the screens", "state": "busy", "stance": "Cold."},
                                                  {"id": "alf", "here": False, "away": "upstairs"}, {"id": "kid", "here": False, "away": "out"}]}))
            for cid, c in CHARS.items():
                h.call(srv, "POST", "/api/chars", dict(c, id=cid))
            try:
                st, d = h.call(srv, "POST", "/api/doing", {"place": {"id": self.c["id"]}, "history": [{"role": "assistant", "content": "Tuesday, 3 AM."}], "turn": 1, "user": "Sam"})
                self.assertEqual(st, 200)
                self.assertEqual(d["people"]["bat"]["doing"], "watching the screens")
                self.assertFalse(d["people"]["alf"]["here"])
                gid = pl.scene_id(self.c["id"])
                # only the one who is in can be picked to speak
                st, d = h.call(srv, "POST", "/api/group_next", {"group": gid, "user": "Sam", "history": [{"role": "user", "content": "*looks around*"}],
                                                               "spoke": [], "cap": 2, "n": 0, "keep": True, "present": ["bat"]})
                self.assertIn(d.get("next"), ("bat", None))
                st, d = h.call(srv, "POST", "/api/group_next", {"group": gid, "user": "Sam", "history": [{"role": "user", "content": "*looks around*"}],
                                                               "spoke": [], "cap": 2, "n": 0, "keep": True, "present": []})
                self.assertIsNone(d.get("next"))
                # a saved group can never take a place's id
                st, d = h.call(srv, "POST", "/api/groups", {"id": "pl_hijack", "name": "x", "members": ["bat", "alf"]})
                self.assertFalse(d["id"].startswith("pl_"))
                h.call(srv, "DELETE", "/api/groups/" + d["id"])
            finally:
                for cid in CHARS:
                    h.call(srv, "DELETE", "/api/chars/" + cid)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
