import unittest

from crumble import simtime, story, ambience
from crumble.llm import generate_reply
from crumble.rp.actions import classify
from crumble.story import beats, endings, humor, moment, routine, world
from tests import helpers as h

BAKER = {"id": "b", "name": "Mira", "occupation": "Baker", "humor": "dry sarcasm", "likes": "loves rain", "personality": "wry, warm"}


def M(*texts):
    return [{"role": "assistant" if i % 2 == 0 else "user", "content": t} for i, t in enumerate(texts)]


class RoutineTests(unittest.TestCase):
    def test_every_hour_is_covered_and_sleep_is_at_night(self):
        for c in ({"occupation": "student"}, {"occupation": "nurse"}, {"occupation": "bartender"}, {}, BAKER):
            for we in (False, True):
                sl, *_ = routine.schedule(c, we)
                self.assertEqual(len(sl), 48)
        self.assertEqual(routine.now({"occupation": "student"}, {"hour": 3.0, "dayn": 1})["state"], "asleep")
        self.assertEqual(routine.now({"occupation": "student"}, {"hour": 10.5, "dayn": 1})["state"], "busy")
        self.assertEqual(routine.now({"occupation": "student"}, {"hour": 14.0, "dayn": 5})["state"], "free")   # weekend

    def test_night_workers_and_owls_live_at_night(self):
        self.assertEqual(routine.now({"occupation": "bartender"}, {"hour": 22.0, "dayn": 1})["state"], "busy")
        self.assertEqual(routine.now({"occupation": "bartender"}, {"hour": 9.0, "dayn": 1})["state"], "asleep")
        owl = {"occupation": "clerk", "personality": "a night owl"}
        self.assertNotEqual(routine.now(owl, {"hour": 23.5, "dayn": 1})["state"], "asleep")

    def test_the_authors_own_routine_wins(self):
        c = {"occupation": "Barista", "routine": "Weekdays: up 6:30, bakery 7-3, gym 5pm, in bed by 11. Weekends: sleeps in till 10, farmers market 11-1"}
        r = routine.now(c, {"hour": 9.0, "dayn": 1})
        self.assertEqual((r["key"], r["own"]), ("work", True))
        self.assertIn("bakery", r["label"])
        self.assertEqual(routine.now(c, {"hour": 17.5, "dayn": 1})["key"], "exercise")
        self.assertEqual(routine.now(c, {"hour": 8.0, "dayn": 5})["state"], "asleep")      # sleeps in on the weekend
        self.assertEqual(routine.now(c, {"hour": 11.5, "dayn": 5})["key"], "errands")

    def test_no_clock_no_routine(self):
        self.assertIsNone(routine.now(BAKER, None))


class WorldTests(unittest.TestCase):
    def test_the_days_weather_is_stable_and_builds(self):
        a = world.forecast({"hour": 10.0, "dayn": 3}, "spring", "seed")
        self.assertEqual(a, world.forecast({"hour": 10.0, "dayn": 3}, "spring", "seed"))
        self.assertIn(a["now"], world.EFFECT)

    def test_story_weather_beats_the_days_weather(self):
        sim = simtime.derive(M("It is Monday 9 AM. Heavy rain lashes the windows.", "ok"))
        amb = ambience.derive(M("It is Monday 9 AM. Heavy rain lashes the windows.", "ok"), "", (), sim)
        wx = story.sky(sim, amb, [], "s", story.settings({}))
        self.assertEqual((wx["weather"], wx["src"]), ("rain", "story"))

    def test_character_taste_for_weather(self):
        self.assertTrue(world.feel(BAKER, "rain")["love"])
        self.assertTrue(world.feel({"fears": "terrified of thunderstorms"}, "storm")["hate"])


class EndingTests(unittest.TestCase):
    def test_question_endings_are_seen_and_cut(self):
        self.assertTrue(endings.ends_on_question("*smiles* Where were you?"))
        self.assertFalse(endings.ends_on_question("Fine. Whatever."))
        pl = {"ban": True}
        self.assertEqual(endings.repair("I waited an hour. Where were you? *crosses her arms*", pl), "I waited an hour. *crosses her arms*")
        self.assertEqual(endings.repair("Where were you?", pl), "Where were you?")        # never leaves an empty reply

    def test_two_questions_in_a_row_are_not_allowed(self):
        for t in range(12):
            pl = endings.plan(["Hi. How are you?"], {"kinds": []}, t, "x")
            self.assertTrue(pl["ban"])

    def test_most_turns_do_not_invite_a_question(self):
        n = sum(not endings.plan([], {"kinds": []}, t, "x")["ban"] for t in range(60))
        self.assertLess(n, 30)


class HumorAndMoment(unittest.TestCase):
    def test_no_jokes_for_grief_but_a_joke_gets_met(self):
        hp = humor.profile({"humor": "dry sarcasm and teasing"})
        sad = moment.read("my dad died last week and i can't sleep")
        for t in range(40):
            self.assertEqual(humor.cue(hp, "M", "S", t, "x", sad, "sad"), "")
        self.assertIn("joking", humor.cue(hp, "M", "S", 3, "x", moment.read("lol that was funny")))

    def test_a_cadence_exists(self):
        hp = humor.profile({"humor": "goofy, always joking"})
        n = sum(bool(humor.cue(hp, "M", "S", t, "x", {"kinds": []}, "happy")) for t in range(60))
        self.assertTrue(8 < n < 40)

    def test_beats_are_stable_rare_and_hushed_for_sad_moments(self):
        a = [beats.beat(t, "x", "the café", True, "morning", "rain") for t in range(80)]
        self.assertEqual(a, [beats.beat(t, "x", "the café", True, "morning", "rain") for t in range(80)])
        self.assertTrue(5 < sum(bool(x) for x in a) < 20)
        self.assertEqual([beats.beat(t, "x", "the café", True, "morning", "rain", 0, "off") for t in range(40)], [""] * 40)


class NoRandomFights(unittest.TestCase):
    def test_ordinary_words_start_nothing(self):
        for t in ("I hit the snooze button and fire up the stove", "*throws a smile and cuts the cake*", "he convinced me to stay", "She nursed a coffee", "let's fight about it"):
            self.assertIsNone(classify(t), t)

    def test_a_real_action_is_still_read(self):
        self.assertEqual(classify("*I try to persuade her to come along*"), "persuade")
        self.assertEqual(classify("I convince him to wait"), "persuade")


class PipelineTests(unittest.TestCase):
    def run_reply(self, replies, hist, **p):
        fake = h.install(h.FakeLLM(replies))
        r = generate_reply({"char": BAKER, "user": "Sam", "history": hist, "state": {"mood": "calm", "energy": "medium"},
                            "params": dict({"mode": "story", "think": False, "max_tokens": 200}, **p)}, None)
        return fake, r

    def test_the_prompt_carries_the_day_and_the_reply_reports_the_world(self):
        hist = M("Monday morning, 7:30 AM. Mira flips the sign on the bakery door.", "lol morning. is it always this cold?")
        fake, r = self.run_reply(["*rubs her hands.* Only before the ovens warm up. Sit anywhere."], hist)
        sysm = fake.calls[0][0]["content"]
        self.assertIn("[Daily life, time and world", sysm)
        self.assertIn("usual rhythm", sysm)
        self.assertEqual(r["world"]["day"], "Monday")
        self.assertTrue(r["world"]["who"])
        self.assertIn("Do not end this reply with a question", fake.calls[0][-1]["content"])

    def test_a_closing_question_is_retried_then_cut(self):
        hist = M("Monday morning, 7:30 AM. Mira flips the sign.", "morning", "Morning. Coffee?", "yes please")
        fake, r = self.run_reply(["Fine. Anything else? Really?", "I have a lot of bread to bake. What do you want?", "Take a seat. How was your night?"], hist)
        self.assertFalse(endings.ends_on_question(r["text"]))
        self.assertGreaterEqual(len(fake.calls), 2)

    def test_switch_it_off(self):
        hist = M("Monday morning, 7:30 AM. Mira flips the sign.", "hi")
        fake, r = self.run_reply(["Hello. Want something?"], hist, story={"on": False})
        self.assertNotIn("[Daily life", fake.calls[0][0]["content"])
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(r["text"], "Hello. Want something?")


class ApiTests(unittest.TestCase):
    def test_world_endpoint(self):
        srv = h.serve()
        st, d = h.call(srv, "POST", "/api/world", {"cid": "nope"})
        self.assertIn("err", d)
        st, d = h.call(srv, "POST", "/api/chars", dict(BAKER, id="bakerx"))
        st, d = h.call(srv, "POST", "/api/world", {"cid": "bakerx", "history": M("Tuesday, 3 AM. Mira is awake.", "hey"), "story": {}})
        self.assertEqual(d["world"]["who"][0]["state"], "asleep")
        self.assertEqual(d["world"]["clock_set"], True)
        h.call(srv, "DELETE", "/api/chars/bakerx")
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
