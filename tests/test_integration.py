import unittest

from tests import helpers as h
from crumble.llm import generate_reply
from crumble.memory import summarize, track
from crumble.prompt import build_messages

ON = {"on": True, "depth": "standard", "guard": True, "dyn": True, "canon": True}
HIST = [{"role": "user", "content": "you're an idiot, shut up"}]


def req(c, replies=None, pers=ON, hist=None, state=None):
    return {"char": c, "user": "Sam", "history": hist or HIST, "state": state or {},
            "params": {"mode": "story", "think": False, "pers": pers, "max_tokens": 200}}


def bm(c, pers, hist=None):
    return build_messages(c, "Sam", hist or HIST, {"pers": pers, "mode": "story", "state": {}, "words": (20, 60)})


class PromptTests(unittest.TestCase):
    def sysmsg(self, pers, c=h.SHY, hist=None):
        return bm(c, pers, hist)[0]["content"]

    def test_block_present_only_when_on(self):
        self.assertIn("Mira - Behaviour", self.sysmsg(ON))
        self.assertNotIn("Behaviour", self.sysmsg(None))

    def test_engine_fields_not_pasted_raw(self):
        c = dict(h.SHY, reactions="Hides behind a book when teased", traits="O 20")
        on, off = self.sysmsg(ON, c), self.sysmsg(None, c)
        self.assertNotIn("Hides behind a book", on.split("Behaviour")[0])   # consumed by the engine, not the sheet dump
        self.assertIn("Hides behind a book", on)
        self.assertIn("Hides behind a book", off)                              # engine off: the author's text still reaches the model

    def test_reaction_follows_what_user_did(self):
        self.assertIn("hostile", self.sysmsg(ON, h.BOLD))
        self.assertNotIn("hostile", self.sysmsg(ON, h.BOLD, [{"role": "user", "content": "nice day"}]))

    def test_tail_reminder_only_deep_and_not_in_history(self):
        deep = dict(ON, depth="deep")
        m = bm(h.SHY, deep)
        self.assertIn("Voice", m[-1]["content"])
        self.assertEqual(HIST[0]["content"], "you're an idiot, shut up")
        m = bm(h.SHY, ON)
        self.assertNotIn("Voice", m[-1]["content"])


class GenerateTests(unittest.TestCase):
    def test_guard_rerolls_off_voice_reply(self):
        fake = h.install(h.FakeLLM(["As an AI language model, I'd be happy to help!", "Oh please. Try harder."]))
        r = generate_reply(req(h.BOLD), None)
        self.assertEqual(r["text"], "Oh please. Try harder.")
        self.assertGreaterEqual(r["pers"]["score"], 65)
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("off-voice", fake.calls[1][0]["content"])           # the retry note reached the model

    def test_keeps_best_when_all_attempts_bad(self):
        h.install(h.FakeLLM(["As an AI language model, hello.", "As an AI, I'd be happy to help! Feel free to ask.", "As an AI language model hi"]))
        r = generate_reply(req(h.BOLD), None)
        self.assertEqual(r["retries"], 2)
        self.assertEqual(r["pers"]["score"], max(r["pers"]["score"], 0))

    def test_engine_off_is_untouched(self):
        fake = h.install(h.FakeLLM(["As an AI language model, I'd be happy to help!"]))
        r = generate_reply(req(h.BOLD, pers=None), None)
        self.assertNotIn("pers", r)
        self.assertEqual(len(fake.calls), 1)

    def test_guard_off_means_no_rerolls(self):
        fake = h.install(h.FakeLLM(["As an AI language model, hi."]))
        generate_reply(req(h.BOLD, pers=dict(ON, guard=False)), None)
        self.assertEqual(len(fake.calls), 1)


class TrackTests(unittest.TestCase):
    def body(self, c, track_json, st=None, pers=ON):
        h.install(h.FakeLLM(track=track_json))
        hist = [{"role": "user", "content": "you're an idiot, shut up"},
                {"role": "assistant", "content": "I'm a baker. Say that again."}]
        return {"char": c, "user": "Sam", "history": hist, "state": st or {}, "pers": pers}

    def test_hostile_message_hurts_even_if_model_says_neutral(self):
        r = track(self.body(h.BOLD, {"mood": "neutral", "affection_delta": 1, "thought": "hm", "facts": []}))
        self.assertLess(r["state"]["affection"], 50)
        self.assertTrue(r["state"]["pers"]["drift"])
        self.assertTrue(any("baker" in x for x in r["state"]["pers"]["canon"]))
        self.assertIn("score", r["state"]["log"][-1])

    def test_off_matches_model_output(self):
        r = track(self.body(h.BOLD, {"mood": "happy", "affection_delta": 3, "thought": "hm", "facts": []}, pers=None))
        self.assertEqual((r["state"]["mood"], r["state"]["affection"]), ("happy", 53))
        self.assertNotIn("pers", r["state"])


class SummarizeTests(unittest.TestCase):
    def test_summary_prompt_uses_structured_format_and_includes_new_events(self):
        fake = h.install(h.FakeLLM(["CHARACTERS\nEva: ..."]))
        history = [{"role": "user", "content": "We are at the station."},
                   {"role": "assistant", "name": "Eva", "content": "I promised to stay."}]
        result = summarize({"char": {"name": "Eva"}, "user": "Crescent", "history": history,
                            "summary": "They met yesterday."})
        ask = fake.calls[-1][0]["content"]
        self.assertEqual(result, "A short summary.")
        for field in ("SETTING & STATE", "Location:", "Current State:", "RELATIONSHIP DYNAMIC", "Primary Dynamic:", "Tone:",
                      "PIVOTAL MOMENTS", "Who's who:", "Eva (the character)", "Crescent (the user)"):
            self.assertIn(field, ask)
        self.assertNotIn("CHARACTERS\n", ask)      # per-person facts come from the cast ledger now, not from the summary
        self.assertIn("They met yesterday.", ask)
        self.assertIn("We are at the station.", ask)
        self.assertIn("I promised to stay.", ask)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = h.serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_page_is_served_with_assets(self):
        st, page = h.call(self.srv, "GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("<script>", page)
        self.assertNotIn("<!--SCRIPTS-->", page)
        self.assertNotIn("<!--STYLES-->", page)

    def test_personality_endpoint_host_only(self):
        st, r = h.call(self.srv, "POST", "/api/personality", {"char": h.SHY})
        self.assertEqual(st, 200)
        self.assertEqual(len(r["traits"]), 14)
        self.assertTrue(r["summary"])
        st, r = h.call(self.srv, "POST", "/api/personality", {"char": h.SHY}, host="192.168.1.50")
        self.assertIn(st, (401, 403))

    def test_unknown_character(self):
        self.assertIn("err", h.call(self.srv, "POST", "/api/personality", {"cid": "nope"})[1])


if __name__ == "__main__":
    unittest.main()
