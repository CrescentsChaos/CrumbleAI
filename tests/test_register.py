import unittest

from tests import helpers as h
from crumble.llm import generate_reply
from crumble.personality import profile, register as rg, voice
from crumble.prompt import build_messages

ON = {"on": True, "depth": "standard", "guard": True, "dyn": True, "canon": True}

MESSMER = {
    "id": "msm", "name": "Messmer",
    "description": "A demigod and fearsome commander.",
    "personality": "composed, aristocratic, disciplined and intimidatingly authoritative",
    "speech": "Messmer speaks with refined aristocratic elegance and measured pacing, with a distinctly ancient and formal quality.",
    "dialect": "Messmer speaks English with a refined, theatrical Shakespearean, with an archaic aristocratic quality.",
    "vocab": "His vocabulary is ceremonial. He favours words such as grace, heresy, flame, serpent, and crusade. He almost never uses modern slang.",
    "catchphrases": "His most recognizable declaration is, \"Those stripped of the Grace of Gold shall all meet death, in the embrace of Messmer's flame.\"",
    "texting": "In a modern interpretation, Messmer writes with impeccable grammar, proper capitalization. His messages are concise, formal, and authoritative.",
}
MELINA = {"id": "mel", "name": "Melina", "speech": "Melina speaks in a gentle, calm, formal, and somewhat poetic manner.",
          "vocab": "Melina uses refined, formal, and occasionally archaic vocabulary, such as \"accord,\" \"grace,\" and \"destiny.\""}

# the three real replies from Messmer's chat logs, plus archaic ones
REAL_BAD = [
    "*Messmer turns slowly, his golden eye glinting in the torchlight.* Speak quickly, trespasser. Identify yourself before my patience wears thin like the edge of my blade.",
    "*Messmer's eyes narrow.* You dare speak of patience when you enter my domain uninvited? State your purpose swiftly. The consequences would be... severe.",
    "*Messmer's eyes narrow, his voice sharpens.* \"Pardon me? I am not accustomed to such insolence. Explain yourself at once.\" He takes a step closer, his hand moving towards the hilt of his sword.",
]
GOOD = ("*He lowers his head.* Thou standest within my keep uninvited. Speak thy purpose, ere my patience is spent, "
        "for those stripped of grace shall meet the flame.")


class DetectTests(unittest.TestCase):
    def test_shakespearean_dialect_is_archaic(self):
        self.assertEqual(rg.detect(MESSMER)["kind"], "archaic")

    def test_favoured_words_and_signature_line_are_lifted_from_the_sheet(self):
        r = rg.detect(MESSMER)
        self.assertIn("heresy", r["lex"])
        self.assertTrue(any(x.startswith("Those stripped of the Grace of Gold") for x in r["lines"]))

    def test_occasionally_archaic_vocabulary_is_only_formal(self):
        self.assertEqual(rg.detect(MELINA)["kind"], "formal")        # not forced into thou and thee

    def test_negated_cue_is_ignored(self):
        c = {"name": "Al", "speech": "Al does not use archaic language and never speaks like a Shakespearean actor. He talks like a trucker."}
        self.assertIsNone(rg.detect(c))

    def test_casual_and_blank_sheets_untouched(self):
        self.assertIsNone(rg.detect(h.BOLD))
        self.assertIsNone(rg.detect(h.SHY))
        self.assertIsNone(rg.detect(h.BLANK))

    def test_texting_mode_follows_the_texting_field(self):
        self.assertEqual(rg.detect(MESSMER, "text")["kind"], "formal")   # his texting field says modern + formal, so no thou on a phone
        self.assertEqual(rg.detect(MESSMER, "call")["kind"], "archaic")

    def test_authors_can_demand_it_in_the_consistency_field(self):
        self.assertEqual(rg.detect({"name": "Bob", "consistency": "Always speak in Early Modern English"})["kind"], "archaic")


class FormalityReadTests(unittest.TestCase):
    def test_rarely_uses_slang_is_not_casual(self):
        t = profile.derive({"texting": "She rarely uses emojis, slang or abbreviations.", "vocab": "She avoids slang and vulgar words."})["traits"]
        self.assertGreaterEqual(t["formality"], 50)


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.reg = rg.detect(MESSMER)

    def test_real_modern_replies_are_hard_failures(self):
        for t in REAL_BAD:
            found, hard = rg.audit(self.reg, t)
            self.assertTrue(hard, t)
            self.assertGreaterEqual(sum(p for p, _, _ in found), 50)

    def test_archaic_reply_passes(self):
        self.assertEqual(rg.audit(self.reg, GOOD), ([], False))

    def test_possessive_s_is_not_a_contraction(self):
        found, _ = rg.audit(self.reg, "Thou shalt meet death in the embrace of Messmer's flame, trespasser.")
        self.assertEqual(found, [])

    def test_mixed_reply_flags_you_and_contraction(self):
        found, hard = rg.audit(self.reg, "Thou darest speak so to me? I don't know what you want, but thy life hangeth upon it.")
        self.assertFalse(hard)
        self.assertEqual({f for _, f, _ in found}, {"slips into modern 'you' instead of thou", "uses contractions"})

    def test_actions_are_not_judged(self):
        self.assertEqual(rg.audit(self.reg, "*You can't see him smile. He doesn't blink.* Thou art bold, stranger, and thy boldness shall cost thee.")[0], [])

    def test_formal_register_flags_contractions_and_slang(self):
        found, hard = rg.audit(rg.detect(MELINA), "I don't think so, yeah, that's not what the accord was about at all.")
        self.assertFalse(hard)
        self.assertEqual({f for _, f, _ in found}, {"uses contractions", "slang or fillers in a formal voice"})

    def test_guard_retries_modern_reply_at_every_depth_and_old_guard_did_not(self):
        c = MESSMER
        prof = profile.profile_for(c)
        for thr in (55, 65, 75):
            r = voice.check(c, prof, REAL_BAD[0], [], "story", None, None, thr)
            self.assertTrue(r["retry"] and r["hard"], thr)
            self.assertIn("thou", r["note"])
        ok = voice.check(c, prof, GOOD, [], "story", None, None, 75)
        self.assertFalse(ok["retry"])
        self.assertGreaterEqual(ok["score"], 90)


class RepairTests(unittest.TestCase):
    reg = {"kind": "archaic"}

    def test_expands_contractions_in_speech_only(self):
        out = rg.repair("*he can't breathe* I don't know. We're done, and I won't yield. They've gone. Dost thou think I'm jesting?", self.reg)
        self.assertEqual(out, "*he can't breathe* I do not know. We are done, and I will not yield. They have gone. Dost thou think I am jesting?")

    def test_questions_invert(self):
        self.assertEqual(rg.repair("Isn't it so? Can't thou see? Won't thou yield?", self.reg), "Is it not so? Can thou not see? Will thou not yield?")

    def test_ambiguous_s_and_d_left_alone(self):
        self.assertEqual(rg.repair("He's gone and I'd stay.", self.reg), "He's gone and I'd stay.")

    def test_no_register_no_change(self):
        self.assertEqual(rg.repair("I don't know.", None), "I don't know.")


class PromptTests(unittest.TestCase):
    HIST = [{"role": "user", "content": "sup"}]

    def msgs(self, c, pers=ON, mode="story"):
        return build_messages(c, "Crescent", self.HIST, {"pers": pers, "mode": mode, "state": {}, "words": (20, 60)})

    def test_speech_block_rules_and_reminder_reach_the_model(self):
        m = self.msgs(MESSMER)
        s = m[0]["content"]
        self.assertIn("Speech pattern (mandatory)", s)
        self.assertIn("thou (subject), thee (object)", s)
        self.assertIn("Favoured words", s)
        self.assertIn("never \"you\" or \"your\"", m[-1]["content"])
        self.assertLess(s.index("[Realism]"), s.index("Speech pattern (mandatory)"))      # late in the prompt on purpose

    def test_generic_rules_no_longer_contradict_the_register(self):
        s = self.msgs(MESSMER)[0]["content"]
        self.assertNotIn("contractions, natural rhythm", s)
        self.assertNotIn('"uh", "well", "I mean"', s)

    def test_applies_even_with_engine_off(self):
        m = self.msgs(MESSMER, pers=None)
        self.assertIn("Speech pattern (mandatory)", m[0]["content"])
        self.assertIn("Early Modern English", m[-1]["content"])

    def test_ordinary_characters_keep_the_generic_rules_and_get_no_block(self):
        s = self.msgs(h.BOLD)[0]["content"]
        self.assertIn("contractions, natural rhythm", s)
        self.assertNotIn("Speech pattern", s)

    def test_texting_mode_does_not_force_thou(self):
        self.assertNotIn("Early Modern English", self.msgs(MESSMER, mode="text")[0]["content"])


class GenerateTests(unittest.TestCase):
    def req(self, c, quick=False, pers=ON):
        return {"char": c, "user": "Sam", "history": [{"role": "user", "content": "sup"}], "state": {},
                "params": {"mode": "story", "think": False, "pers": pers, "max_tokens": 200, "quick": quick}}

    def test_modern_reply_is_rerolled_with_specific_feedback(self):
        fake = h.install(h.FakeLLM([REAL_BAD[0], GOOD]))
        r = generate_reply(self.req(MESSMER), None)
        self.assertEqual(r["text"], GOOD)
        self.assertEqual(len(fake.calls), 2)
        retry_prompt = fake.calls[1][0]["content"] + fake.calls[1][-1]["content"]
        self.assertIn("thou / thee / thy", retry_prompt)
        self.assertIn("'yourself'", retry_prompt)                  # names the offending words

    def test_quick_mode_still_rerolls_a_plainly_modern_reply(self):
        fake = h.install(h.FakeLLM([REAL_BAD[1], GOOD]))
        r = generate_reply(self.req(MESSMER, quick=True), None)
        self.assertEqual(r["text"], GOOD)
        self.assertEqual(len(fake.calls), 2)

    def test_contractions_are_expanded_when_nothing_better_comes(self):
        h.install(h.FakeLLM(["Thou art bold, stranger, and I don't doubt thy courage. Speak, ere I weary."]))
        r = generate_reply(self.req(MESSMER, quick=True), None)
        self.assertIn("I do not doubt", r["text"])
        self.assertNotIn("don't", r["text"])

    def test_archaic_register_lowers_repeat_penalty(self):
        seen = []

        class Spy(h.FakeLLM):
            def create_chat_completion(self, messages, stream=False, **kw):
                if stream:
                    seen.append(kw.get("repeat_penalty"))
                return super().create_chat_completion(messages, stream=stream, **kw)

        h.install(Spy([GOOD]))
        generate_reply(self.req(MESSMER), None)
        self.assertEqual(seen, [1.05])                               # default is 1.1, which taxes repeated thou / thy
        seen.clear()
        h.install(Spy(["Fine."]))
        generate_reply(self.req(h.BOLD), None)
        self.assertEqual(seen, [1.1])                                # ordinary characters keep the user's setting

    def test_ordinary_character_never_rerolled_for_register(self):
        fake = h.install(h.FakeLLM(["Yeah, I don't know what you want."]))
        generate_reply(self.req(h.BOLD), None)
        self.assertEqual(len(fake.calls), 1)


if __name__ == "__main__":
    unittest.main()
