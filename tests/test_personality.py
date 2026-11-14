import time
import unittest

from tests import helpers as h
from crumble.personality import canon, directives, dynamics, engine, profile, stimulus, voice


class ProfileTests(unittest.TestCase):
    def test_sheet_to_traits(self):
        t = profile.derive(h.SHY)["traits"]
        self.assertLess(t["extraversion"], 35)
        self.assertGreater(t["neuroticism"], 60)
        self.assertLess(t["trust"], 40)
        self.assertLess(t["formality"], 50)                  # lowercase texting
        b = profile.derive(h.BOLD)["traits"]
        self.assertGreater(b["assertiveness"], 65)
        self.assertGreater(b["pride"], 65)
        self.assertLess(b["agreeableness"], 45)
        self.assertGreater(b["extraversion"], 55)            # "loud" and "not shy"

    def test_negation_flips(self):
        self.assertGreater(profile.derive({"personality": "not shy at all"})["traits"]["extraversion"], 50)

    def test_blank_sheet_is_neutral(self):
        p = profile.derive(h.BLANK)
        self.assertTrue(all(v == 50 for v in p["traits"].values()))
        self.assertEqual(p["evidence"], {})
        self.assertEqual(p["summary"], "")
        self.assertEqual(p["temper"]["warm"], 1.0)

    def test_override_wins_and_leftover_text_scanned(self):
        p = profile.derive({"traits": "O 80 N 10, sarcastic and guarded", "personality": "shy"})
        self.assertEqual(p["traits"]["openness"], 80)
        self.assertEqual(p["traits"]["neuroticism"], 10)
        self.assertEqual(p["src"]["openness"], "set")
        self.assertLess(p["traits"]["trust"], 40)            # "guarded" from the leftover text
        ov, _ = profile.parse_override("warmth: high, very low pride, in a 5 minute drive")
        self.assertEqual(ov, {"warmth": 75, "pride": 10})    # lone lowercase "a 5" is not agreeableness

    def test_deterministic_and_cached(self):
        self.assertEqual(profile.derive(h.SHY), profile.derive(h.SHY))
        self.assertIs(profile.profile_for(h.SHY), profile.profile_for(dict(h.SHY)))
        edited = dict(h.SHY, personality="bold and loud")
        self.assertNotEqual(profile.profile_for(edited)["hash"], profile.profile_for(h.SHY)["hash"])

    def test_rules_split(self):
        r = profile.derive(h.SHY)["rules"]
        self.assertIn("Never swears", r["never"])
        self.assertIn("Always speaks in lowercase", r["always"])


class StimulusTests(unittest.TestCase):
    def setUp(self):
        self.p = profile.derive(h.SHY)

    def test_tone(self):
        self.assertGreaterEqual(stimulus.read("you're such an idiot, shut up", self.p)["hostile"], .6)
        self.assertGreaterEqual(stimulus.read("thank you so much, you're wonderful", self.p)["kind"], .6)
        self.assertGreaterEqual(stimulus.read("i'm so scared and lonely tonight", self.p)["vulnerable"], .6)
        self.assertGreaterEqual(stimulus.read("I'm so sorry about earlier", self.p)["apology"], .6)
        self.assertEqual(stimulus.read("what's for lunch?", self.p)["tags"], [])

    def test_triggers_and_comforts_match_inflections(self):
        s = stimulus.read("everyone was laughing at you", self.p)
        self.assertTrue(s["triggers"])
        self.assertTrue(stimulus.read("want some tea?", self.p)["comforts"])
        self.assertFalse(stimulus.read("nice weather", self.p)["triggers"])

    def test_actions_are_hostile_or_kind(self):
        self.assertGreaterEqual(stimulus.read("*slaps her across the face*", self.p)["hostile"], .5)
        self.assertGreater(stimulus.read("*hugs her gently*", self.p)["kind"], 0)


class DynamicsTests(unittest.TestCase):
    def stim(self, **k):
        s = {"hostile": 0, "kind": 0, "triggers": [], "boundary": [], "comforts": [], "apology": 0, "dismissive": 0}
        s.update(k)
        return s

    def test_stoic_moves_less_than_volatile(self):
        stoic = profile.derive({"traits": "N 10 E 20"})
        wild = profile.derive({"traits": "N 95 E 90"})
        a = dynamics.advance(stoic, {"mood": "neutral"}, "furious", 0, self.stim())
        b = dynamics.advance(wild, {"mood": "neutral"}, "furious", 0, self.stim())
        self.assertGreater(b["pers"]["va"][1], a["pers"]["va"][1])
        self.assertNotEqual(a["mood"], "furious")            # one exchange cannot take a stoic to fury

    def test_model_word_kept_when_reachable(self):
        p = profile.derive(h.BLANK)
        self.assertEqual(dynamics.advance(p, {"mood": "neutral"}, "curious", 1, self.stim())["mood"], "curious")

    def test_time_heals_and_grudge_fades(self):
        p = profile.derive(h.BLANK)
        st = {"mood": "angry", "pers": {"va": [-.75, .8], "mood": "angry", "grudge": .8}}
        soon = dynamics.advance(p, st, "neutral", 0, self.stim(), gap_s=60)
        later = dynamics.advance(p, st, "neutral", 0, self.stim(), gap_s=3 * 86400)
        self.assertLess(abs(later["pers"]["va"][1]), abs(soon["pers"]["va"][1]))
        self.assertLess(later["pers"]["grudge"], .1)
        self.assertGreater(soon["pers"]["grudge"], .5)

    def test_hostile_always_hurts_and_thin_skin_hurts_more(self):
        calm = profile.derive({"traits": "N 10 A 80"})
        thin = profile.derive({"traits": "N 90 P 90 A 10"})
        for p in (calm, thin):
            self.assertLess(dynamics.advance(p, {"mood": "neutral"}, "neutral", 2, self.stim(hostile=1.0))["delta"], 0)
        d1 = dynamics.advance(calm, {"mood": "neutral"}, "neutral", -2, self.stim())["delta"]
        d2 = dynamics.advance(thin, {"mood": "neutral"}, "neutral", -2, self.stim())["delta"]
        self.assertLessEqual(d2, d1)

    def test_fractions_accumulate_and_grudge_slows_repair(self):
        p = profile.derive({"traits": "A 20 E 20 trust low"})     # warm rate < 1
        st, total = {"mood": "neutral"}, 0
        for _ in range(6):
            r = dynamics.advance(p, st, "neutral", 1, self.stim())
            total += r["delta"]
            st = {"mood": r["mood"], "pers": r["pers"]}
        self.assertTrue(0 < total < 6)
        fresh = dynamics.advance(p, {"mood": "neutral"}, "neutral", 3, self.stim())["delta"]
        sore = dynamics.advance(p, {"mood": "neutral", "pers": {"grudge": 1.0}}, "neutral", 3, self.stim())["delta"]
        self.assertLessEqual(sore, fresh)

    def test_manual_mood_override_is_respected(self):
        p = profile.derive(h.BLANK)
        st = {"mood": "sad", "pers": {"va": [.7, .35], "mood": "happy"}}      # user picked "sad" by hand
        r = dynamics.advance(p, st, "sad", 0, self.stim())
        self.assertLess(r["pers"]["va"][0], 0)

    def test_neutral_profile_leaves_model_values_alone(self):
        p = profile.derive(h.BLANK)
        r = dynamics.advance(p, {"mood": "neutral"}, "happy", 2, self.stim())
        self.assertEqual((r["mood"], r["delta"]), ("happy", 2))


class CanonTests(unittest.TestCase):
    def test_extract_keeps_durable_facts_only(self):
        got = canon.extract("*smiles* I'm a nurse. I hate cilantro. I'm a bit tired today. My brother lives in Leeds. Nice weather.")
        joined = " | ".join(got)
        self.assertIn("nurse", joined)
        self.assertIn("cilantro", joined)
        self.assertIn("brother", joined)
        self.assertNotIn("tired", joined)

    def test_merge_dedupes_and_caps(self):
        m = canon.merge(["I hate cilantro"], ["I hate cilantro.", "I love tea"])
        self.assertEqual(len(m), 2)
        self.assertLessEqual(len(canon.merge([], [f"I always eat meal number {i} at noon" for i in range(60)])), 30)

    def test_contradictions(self):
        self.assertTrue(canon.contradictions("Honestly I love cilantro, put it on everything.", ["I hate cilantro"]))
        self.assertFalse(canon.contradictions("I used to love cilantro but I hate it now.", ["I hate cilantro"]))
        self.assertTrue(canon.contradictions("I'm 31 years old.", ["I'm 24 years old"]))
        self.assertFalse(canon.contradictions("I love tea.", ["I hate cilantro"]))


class GuardTests(unittest.TestCase):
    def check(self, c, text, **k):
        p = profile.derive(c)
        p["fp"] = voice.fingerprint(c)
        return voice.check(c, p, text, k.get("own"), k.get("mode", "story"), k.get("canon"), p["fp"])

    def test_assistant_speak_fails(self):
        r = self.check(h.BOLD, "As an AI language model, I'd be happy to help you with that!")
        self.assertTrue(r["retry"])
        self.assertTrue(r["note"])

    def test_in_voice_passes(self):
        self.assertFalse(self.check(h.BOLD, "Oh please. Like you could keep up with me.")["retry"])

    def test_rules_are_enforced(self):
        self.assertTrue(any("rule" in f for f in self.check(h.SHY, "well damn, that is a lot of people here")["flags"]))
        self.assertGreater(self.check(h.SHY, "well, that is a lot of people here")["score"],
                           self.check(h.SHY, "well damn, that is a lot of people here")["score"])

    def test_canon_contradiction_flagged(self):
        r = self.check(h.BOLD, "I love cilantro, honestly.", canon=["I hate cilantro"])
        self.assertTrue(any("contradict" in f for f in r["flags"]))

    def test_formatting_and_register(self):
        self.assertTrue(any("list" in f for f in self.check(h.BOLD, "- first\n- second")["flags"]))
        stiff = {"id": "x", "name": "X", "personality": "casual, laid-back, swears a lot"}
        r = self.check(stiff, "Indeed, I shall consider the matter further, and perhaps we may reconvene tomorrow evening.")
        self.assertTrue(any("formal" in f for f in r["flags"]))


class DirectiveTests(unittest.TestCase):
    def build(self, c, text, depth="standard", st=None):
        p = profile.derive(c)
        return directives.build(c, p, stimulus.read(text, p), st or {}, depth)

    def test_block_reflects_character(self):
        block, _ = self.build(h.SHY, "hello there")
        self.assertIn("Behaviour", block)
        self.assertIn("Says little", block)

    def test_reaction_depends_on_character(self):
        shy, _ = self.build(h.SHY, "you're an idiot, shut up")
        bold, _ = self.build(h.BOLD, "you're an idiot, shut up")
        self.assertNotEqual(shy, bold)
        self.assertIn("hostile", bold)
        self.assertIn("fires back", bold)           # a bold, proud character does not tear up
        self.assertNotIn("tear up", bold)

    def test_depth_changes_size_and_tail(self):
        st = {"pers": {"canon": ["I hate cilantro", "I'm a nurse"]}}
        light, lt = self.build(h.SHY, "hi", "light", st)
        deep, dt = self.build(h.SHY, "hi", "deep", st)
        self.assertLess(len(light), len(deep))
        self.assertFalse(lt)
        self.assertTrue(dt)
        self.assertNotIn("cilantro", light)
        self.assertIn("cilantro", deep)
        self.assertLess(len(deep), 2600)

    def test_blank_sheet_adds_nothing(self):
        self.assertEqual(self.build(h.BLANK, "hello"), ("", ""))


class EngineTests(unittest.TestCase):
    def test_settings_default_off(self):
        self.assertFalse(engine.settings(None)["on"])
        self.assertEqual(engine.settings({"on": True, "depth": "weird"})["depth"], "standard")

    def test_narrator_never_gets_a_personality(self):
        self.assertFalse(engine.active({"id": "__narrator__"}, engine.settings({"on": True})))

    def test_after_turn_logs_drift_and_canon(self):
        cfg = engine.settings({"on": True})
        hist = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "I'm a nurse. Hello."}]
        r = engine.after_turn(h.BOLD, {"mood": "neutral"}, {"self_facts": ["I collect old maps"]}, "happy", 1, hist, "Sam", cfg, now=time.time())
        self.assertTrue(r["pers"]["drift"])
        self.assertTrue(any("nurse" in x for x in r["pers"]["canon"]))
        self.assertIn("I collect old maps", r["pers"]["canon"])


if __name__ == "__main__":
    unittest.main()
