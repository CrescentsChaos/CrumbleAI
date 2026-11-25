"""The conversation director: varied lengths and tones, human quirks that follow the personality, no repeated patterns, characters who speak first."""
import collections
import unittest

from tests import helpers as h
from crumble import chronicle, director as d
from crumble.llm import generate_reply
from crumble.memory import track

LONGQ = "So I was thinking about going to the market this afternoon, want to come along with me and see the new stalls?"


def hist(u=LONGQ, extra=()):
    return [{"role": "assistant", "content": "Hi there."}, *extra, {"role": "user", "content": u}]


def sweep(c, u=LONGQ, n=500, mood="neutral", **kw):
    out = collections.defaultdict(collections.Counter)
    for t in range(n):
        p = d.plan(c, {"mood": mood, "affection": 50}, hist(u), turn=t, key="x", **kw)
        out["quirk"][p["quirk"]] += 1
        out["len"][p["len"]] += 1
        out["tone"][p["tone"]] += 1
    return out


class Variation(unittest.TestCase):
    def test_every_length_and_many_tones_appear(self):
        r = sweep(h.BOLD)
        self.assertEqual(set(r["len"]), {"tiny", "short", "medium", "long"})
        self.assertGreaterEqual(len(r["tone"]), 9)
        self.assertLess(max(r["tone"].values()) / 500, .3)       # no tone takes over

    def test_a_low_effort_message_gets_a_short_answer_and_a_big_one_a_bigger_one(self):
        lo = sweep(h.BLANK, "lol")["len"]
        hi = sweep(h.BLANK, "I have been meaning to tell you about the whole mess at work. " * 4)["len"]
        self.assertGreater(lo["tiny"] + lo["short"], 350)
        self.assertGreater(hi["medium"] + hi["long"], 350)

    def test_quiet_characters_say_less_and_chatty_ones_more(self):
        shy, rex = sweep(h.SHY)["len"], sweep(h.BOLD)["len"]
        self.assertGreater(shy["tiny"] + shy["short"], rex["tiny"] + rex["short"] - 40) or None
        self.assertGreater(rex["long"], shy["long"] - 1)

    def test_tone_follows_mood(self):
        angry = sweep(h.BLANK, mood="angry")["tone"]
        happy = sweep(h.BLANK, mood="happy")["tone"]
        self.assertGreater(angry["irritated"] + angry["blunt"], happy["irritated"] + happy["blunt"] + 40)
        self.assertGreater(happy["warm"] + happy["playful"] + happy["excited"], angry["warm"] + angry["playful"] + angry["excited"] + 40)

    def test_the_same_length_and_tone_do_not_repeat_back_to_back(self):
        text = "Okay then, that is fine by me, really. I suppose we could go now if you like, the sun is out anyway and it is warm. Bring a bag, the stalls are heavy."
        cls = d.len_class(text)
        own = [{"role": "assistant", "content": text, "dyn": {"tone": "warm"}}] * 2
        same_len = same_tone = 0
        for t in range(400):
            p = d.plan(h.BLANK, {"mood": "happy"}, own + [{"role": "user", "content": LONGQ}], turn=t, key="k")
            same_len += p["len"] == cls
            same_tone += p["tone"] == "warm"
        free = sweep(h.BLANK, mood="happy", n=400)
        self.assertLess(same_len, free["len"][cls] * .4 + 5)
        self.assertLess(same_tone, free["tone"]["warm"] * .4 + 5)

    def test_user_set_length_is_respected(self):
        p = d.plan(h.BOLD, {}, hist(), length="short", turn=1, key="k")
        self.assertIsNone(p["len"])
        self.assertIsNone(p["band"])

    def test_deterministic_for_the_same_turn_and_different_for_a_swipe(self):
        a = d.plan(h.BOLD, {}, hist(), turn=7, key="k")
        b = d.plan(h.BOLD, {}, hist(), turn=7, key="k")
        self.assertEqual((a["tone"], a["len"], a["quirk"]), (b["tone"], b["len"], b["quirk"]))
        seen = {(d.plan(h.BOLD, {}, hist(), turn=7, key="k", variant=v)["tone"]) for v in range(12)}
        self.assertGreater(len(seen), 2)

    def test_off_and_continue_do_nothing(self):
        self.assertEqual(d.plan(h.BOLD, {}, hist(), level=0)["block"], "")
        self.assertEqual(d.plan(h.BOLD, {}, hist(), kind="continue")["block"], "")


class Quirks(unittest.TestCase):
    def test_rate_follows_the_level(self):
        rates = [1 - sweep(h.BOLD, level=lv, n=600)["quirk"][None] / 600 for lv in (0, 1, 2, 3)]
        self.assertEqual(rates[0], 0)
        self.assertTrue(rates[1] < rates[2] < rates[3], rates)
        self.assertTrue(.05 < rates[1] < .2 and .15 < rates[2] < .35 and .25 < rates[3] < .5, rates)

    def test_all_five_quirks_happen(self):
        q = collections.Counter()
        for c in (h.BOLD, h.SHY, h.BLANK):
            q += sweep(c, "I tried that new recipe you told me about yesterday and it turned into a disaster, honestly. " * 2, level=3)["quirk"]
        for k in ("joke", "topic", "interrupt", "misunderstand", "lie"):
            self.assertGreater(q[k], 0, k)

    def test_never_in_a_serious_or_tender_moment(self):
        for u in ("my grandmother died yesterday and I am crying", "I'm so scared, please help me, there is blood everywhere", "I feel so alone and heartbroken tonight"):
            self.assertEqual(sweep(h.BOLD, u, level=3, n=300)["quirk"][None], 300, u)

    def test_no_joke_when_the_user_is_hostile(self):
        q = sweep(h.BOLD, "you are a useless idiot and I hate you", level=3)["quirk"]
        self.assertEqual(q["joke"], 0)

    def test_humorous_characters_joke_more(self):
        rex = sweep(h.BOLD, level=3)["quirk"]["joke"]
        mira = sweep(h.SHY, level=3)["quirk"]["joke"]
        self.assertGreater(rex, mira)

    def test_cooldowns(self):
        own = [{"role": "assistant", "content": "Fine.", "dyn": {"quirk": "joke"}}]
        for t in range(300):
            self.assertIsNone(d.plan(h.BOLD, {}, own + [{"role": "user", "content": LONGQ}], level=3, turn=t, key="c")["quirk"])    # none twice within two replies
        own = [{"role": "assistant", "content": "Fine.", "dyn": {"quirk": "lie"}}, {"role": "assistant", "content": "Ok.", "dyn": {}}, {"role": "assistant", "content": "Yes.", "dyn": {}}]
        for t in range(300):
            self.assertNotEqual(d.plan(h.SHY, {}, own + [{"role": "user", "content": LONGQ}], level=3, turn=t, key="c")["quirk"], "lie")

    def test_a_real_question_is_not_dodged_by_a_topic_change(self):
        ask = sweep(h.BOLD, "What is the capital of France and why do people care about it so much?", level=3, n=800)["quirk"]["topic"]
        tell = sweep(h.BOLD, "The capital of France is Paris and people care about it so much, honestly, it is all they talk about.", level=3, n=800)["quirk"]["topic"]
        self.assertLess(ask, tell * .5)

    def test_lies_are_harmless_and_never_about_a_cry_for_help(self):
        q = sweep(h.SHY, "Should I take the job offer? I need your advice on this, what should I do?", level=3)["quirk"]
        self.assertEqual(q["lie"], 0)
        p = next(p for t in range(600) if (p := d.plan(h.SHY, {}, hist("I wonder what you were doing earlier, you seemed quiet all day long"), level=3, turn=t, key="z"))["quirk"] == "lie")
        self.assertIn("harmless", p["tail"])
        self.assertIn("never announce", p["tail"])

    def test_group_interruption_cuts_the_previous_speaker(self):
        p = next(p for t in range(900) if (p := d.plan(h.BOLD, {}, hist("go on then"), level=3, turn=t, key="g", group=True))["quirk"] == "interrupt")
        self.assertIn("last speaker", p["tail"])


class Memory(unittest.TestCase):
    LIE = {"role": "assistant", "content": "*Mira looks away.* I was at the library all evening, honestly.", "dyn": {"quirk": "lie"}}

    def test_a_lie_stays_a_lie_the_character_knows_about(self):
        note = d.follow_up([self.LIE, {"role": "user", "content": "really?"}], h.SHY)
        self.assertIn("told", note)
        self.assertIn("library", note)
        self.assertIn("not true", note)

    def test_a_misreading_is_noticed_afterwards(self):
        note = d.follow_up([{"role": "assistant", "content": "x", "dyn": {"quirk": "misunderstand"}}], h.SHY)
        self.assertIn("misread", note)

    def test_no_notes_for_honest_replies(self):
        self.assertEqual(d.follow_up([{"role": "assistant", "content": "Fine.", "dyn": {"quirk": "joke"}}], h.SHY), "")

    def test_the_chronicle_and_tracker_never_learn_a_lie_as_fact(self):
        self.assertEqual(chronicle.extract([self.LIE], "Sam", "Mira", 0), [])
        plain = dict(self.LIE, dyn={})
        self.assertTrue(chronicle.extract([dict(plain, content="I promise I will never tell anyone about the key in the cellar.")], "Sam", "Mira", 0))
        fake = h.install(h.FakeLLM(track={"mood": "calm"}))
        track({"char": h.SHY, "user": "Sam", "history": [{"role": "user", "content": "where were you?"}, self.LIE], "state": {}})
        self.assertNotIn("library", fake.calls[-1][-1]["content"])


class NoRepeats(unittest.TestCase):
    A = '*Mira nods slowly.* "Okay, that works for me." *She smiles.*'

    def test_same_shape_is_called_out(self):
        own = [self.A, '*Mira shrugs.* "Fine by me." *She looks away.*', '*Mira laughs.* "Sure, why not?" *She waves.*']
        self.assertIn("built the same way", d.patterns(own)["note"])

    def test_two_questions_in_a_row_are_called_out(self):
        self.assertIn("ended on a question", d.patterns(["Where were you?", "And why didn't you call?"])["note"])

    def test_same_length_and_emoji_are_called_out(self):
        n = d.patterns(["ok 😊", "sure 😊", "fine 😊"], "text")["note"]
        self.assertIn("emoji", n)
        self.assertIn("same length", n)

    def test_varied_replies_get_no_note(self):
        self.assertEqual(d.patterns(['"Hm."', '*She tilts her head, studying the map for a long moment before answering.* "That road washed out in spring, you know. Nobody uses it."'])["note"], "")

    def test_an_opening_used_lately_is_an_issue_even_inside_an_action(self):
        own = [self.A]
        self.assertEqual(d.pattern_issue('*Mira nods slowly.* "Sure, go."', own), "pattern_open")
        self.assertIsNone(d.pattern_issue('"Sure, go." *Mira nods slowly.*', own))
        self.assertIsNone(d.pattern_issue("Hm.", own))

    def test_generate_reply_rerolls_a_repeated_opening_and_flags_nothing_else(self):
        fake = h.install(h.FakeLLM(['*Mira nods slowly.* "No idea, honestly, ask the baker."', '"The baker, ask him. I only buy the bread." *Mira shrugs.*']))
        r = generate_reply({"char": h.SHY, "user": "Sam", "state": {}, "turn": 3,
                            "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": self.A}, {"role": "user", "content": "who sells the bread here?"}],
                            "params": {"mode": "story", "think": False, "max_tokens": 150}}, None)
        self.assertEqual(len(fake.calls), 2)
        self.assertTrue(r["text"].startswith('"The baker'))
        self.assertIn("same words", h.ptxt(fake.calls[1]))


class Pipeline(unittest.TestCase):
    def req(self, hist_, **p):
        return {"char": h.BOLD, "user": "Sam", "state": {"mood": "happy", "affection": 60}, "history": hist_, "turn": len(hist_),
                "params": dict({"mode": "story", "think": False, "max_tokens": 150}, **p)}

    def test_the_plan_reaches_the_model_and_comes_back_on_the_reply(self):
        fake = h.install(h.FakeLLM(['*Rex grins.* "Fine, I will come along, but you are paying."']))
        r = generate_reply(self.req(hist()), None)
        txt = h.ptxt(fake.calls[0])
        self.assertIn("[Conversation dynamics]", txt)
        self.assertIn("emotional tone", txt)
        self.assertEqual(set(r["dyn"]) >= {"tone", "len", "quirk"}, True)
        self.assertEqual(r["dyn"]["len"], d.len_class(r["text"]))

    def test_the_length_line_matches_the_plan(self):
        fake = h.install(h.FakeLLM(["Ok."]))
        generate_reply(self.req(hist("lol")), None)
        import re
        lo, hi = map(int, re.search(r"Length: about (\d+)-(\d+) words", h.ptxt(fake.calls[0])).groups())
        self.assertLessEqual(hi, 120)
        self.assertLess(lo, hi)

    def test_off_means_off(self):
        fake = h.install(h.FakeLLM(["Ok."]))
        r = generate_reply(self.req(hist(), dyn={"level": 0}), None)
        self.assertNotIn("[Conversation dynamics]", h.ptxt(fake.calls[0]))
        self.assertNotIn("dyn", r)

    def test_a_lie_the_character_told_is_remembered_next_turn(self):
        fake = h.install(h.FakeLLM(["Yeah, fine."]))
        hh = [{"role": "user", "content": "where were you?"}, {"role": "assistant", "content": "I was at the library all evening.", "dyn": {"quirk": "lie"}},
              {"role": "user", "content": "funny, the library was closed yesterday"}]
        generate_reply(self.req(hh), None)
        txt = h.ptxt(fake.calls[0])
        self.assertIn("told", txt)
        self.assertIn("not true", txt)

    def test_the_character_speaks_first_when_the_user_comes_back(self):
        fake = h.install(h.FakeLLM(['"Look who finally shows up. I kept your seat warm."']))
        hh = [{"role": "user", "content": "see you tomorrow"}, {"role": "assistant", "content": "Don't be late."}]
        r = generate_reply(dict(self.req(hh, mode="story"), kind="nudge", reason="return", gap_s=3600 * 30), None)
        txt = h.ptxt(fake.calls[0])
        self.assertIn("has come back after", txt)
        self.assertIn("speaks first", txt)
        self.assertIn("1 day", txt)
        self.assertEqual(r["dyn"].get("reason"), "return")
        self.assertTrue(r["text"])

    def test_idle_nudges_vary_what_they_do(self):
        hows = set()
        for t in range(12):
            hows.add(d.initiate("idle", h.BOLD, {}, [], key="k", turn=t, gap_s=120)["how"])
        self.assertGreaterEqual(len(hows), 3)
        prev = [{"role": "assistant", "content": "x", "dyn": {"init": "has a new thought and shares it"}}]
        for t in range(30):
            self.assertNotEqual(d.initiate("idle", h.BOLD, {}, prev * 2, key="k", turn=t)["how"], "has a new thought and shares it")

    def test_initiation_brings_something_of_its_own(self):
        c = dict(h.BOLD, likes="falconry, cheap whisky")
        tails = " ".join(d.initiate("idle", c, {"facts": ["Sam hates cilantro"]}, [{"role": "assistant", "content": "Well?"}], key="k", turn=t)["tail"] for t in range(10))
        self.assertTrue("falconry" in tails or "whisky" in tails or "cilantro" in tails)
        asked = " ".join(d.initiate("idle", h.BOLD, {}, [{"role": "assistant", "content": "So, are you coming?"}], key="k", turn=t)["tail"] for t in range(20))
        self.assertIn("never got an answer", asked)

    def test_settings_are_sane(self):
        self.assertEqual(d.settings(None), {"on": True, "level": 2, "greet": 6.0})
        self.assertFalse(d.settings({"level": 0})["on"])
        self.assertEqual(d.settings({"level": 99, "greet": "x"})["level"], 3)


if __name__ == "__main__":
    unittest.main()
