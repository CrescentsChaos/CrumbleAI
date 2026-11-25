import unittest

from tests import helpers as h
from crumble import simtime
from crumble.llm import generate_reply
from crumble.prompt import build_messages
from crumble.sanitize import enclose_narration, strip_directives

FAITH = {"id": "faith", "name": "Faith", "personality": "Calm. Introverted.", "scenario": "Monday morning. Faith and Crescent are getting ready for university."}


def req(replies, hist, c=FAITH, user="Crescent", **extra):
    fake = h.install(h.FakeLLM(replies))
    b = {"char": c, "user": user, "history": hist, "state": {}, "params": {"mode": "story", "think": False, "max_tokens": 200}}
    b.update(extra)
    return fake, generate_reply(b, None)


class LeakTests(unittest.TestCase):
    def test_echoed_directive_is_removed(self):
        t, i = strip_directives("[Reply as Crescent. Be casual and friendly in this conversation.] Oh, hi.", "Faith", ["Crescent"])
        self.assertEqual(t, "Oh, hi.")
        self.assertTrue(i["leaked"] and i["flipped"])

    def test_as_faith_label_removed(self):
        t, i = strip_directives("*looks up* [As Faith] Who are you?", "Faith", ["Crescent"])
        self.assertEqual(t, "*looks up* Who are you?")
        self.assertFalse(i["flipped"])

    def test_cut_off_and_private_note(self):
        self.assertEqual(strip_directives("Fine. <<PRIVATE NOTE FOR THE WRITER. Write only", "Faith", "Crescent")[0], "Fine.")
        self.assertEqual(strip_directives("Fine. [Reply as Cres", "Faith", "Crescent")[0], "Fine.")

    def test_aside_becomes_narration(self):
        t, _ = strip_directives("Sure. [sighs] Whatever.", "Faith", "Crescent")
        self.assertEqual(t, "Sure. *sighs* Whatever.")

    def test_narration_enclosed_dialogue_untouched(self):
        out = enclose_narration('Faith looks away and clutches her bag. "I\'m fine." Crescent, wait. (quietly) Please go.', "Faith", ["Crescent"])
        self.assertEqual(out, '*Faith looks away and clutches her bag.* "I\'m fine." Crescent, wait. *quietly* Please go.')

    def test_pipeline_retries_flipped_reply_and_never_shows_leak(self):
        hist = [{"role": "assistant", "content": "*Bullies took my book away and you approach me.* Who are you?"},
                {"role": "user", "content": "I'm Crescent. Are you okay?"}]
        fake, r = req(["[Reply as Crescent. Be casual and friendly in this conversation.]", "*wipes her eyes* I'm fine. Leave me alone."], hist)
        self.assertNotIn("Reply as", r["text"])
        self.assertIn("I'm fine", r["text"])
        self.assertEqual(len(fake.calls), 2)

    def test_prompt_has_no_reply_as_instruction(self):
        m = build_messages(FAITH, "Crescent", [{"role": "user", "content": "hi"}], {"mode": "story", "state": {}, "words": (10, 30)})
        self.assertNotIn("[Reply as", m[-1]["content"])
        self.assertIn("never write Crescent's words", m[-1]["content"])
        self.assertIn("WHO IS WHO", h.ptxt(m))


class TimeTests(unittest.TestCase):
    H = [{"role": "assistant", "content": "*It is Monday morning. We are both getting ready for university.* Ready?"},
         {"role": "user", "content": "Yeah, let's go."},
         {"role": "assistant", "content": "*Three hours later, in the library, Faith finds a seat.*"},
         {"role": "user", "content": "I sit beside you."}]

    def test_three_hours_after_monday_morning_is_noon(self):
        s = simtime.derive(self.H)
        self.assertEqual(s["day"], "Monday")
        self.assertEqual(s["period"], "midday")
        self.assertTrue(s["daytime"] and not s["night"])

    def test_no_anchor_falls_back_to_real_clock(self):
        self.assertIsNone(simtime.derive([{"role": "user", "content": "hello"}]))

    def test_edits_and_rewinds_are_safe(self):
        self.assertEqual(simtime.derive(self.H[:2])["period"], "morning")

    def test_next_morning_and_time_skip(self):
        s = simtime.derive([{"role": "user", "content": "It's Monday evening."}, {"role": "assistant", "content": "The next morning, she wakes."}])
        self.assertEqual((s["day"], s["period"]), ("Tuesday", "morning"))

    def test_night_talk_at_noon_is_flagged_not_retried(self):    # H8: no repair exists for it, and it is not a hard failure
        fake, r = req(["*yawns* It's so late, I should go to bed.", "*opens her laptop* The library is packed at lunch."], self.H,
                      clock="Wednesday, 2:10 AM (late at night)")
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("time", r["flags"])
        sysmsg = h.ptxt(fake.calls[0])
        self.assertIn("In the story it is Monday, around 12:", sysmsg)
        self.assertNotIn("2:10 AM", sysmsg)       # the real clock never reaches the character once the story set the time


class IdentityTests(unittest.TestCase):
    def test_user_action_written_by_character_is_cut(self):
        hist = [{"role": "user", "content": "Hi, I'm Crescent."}]
        fake, r = req(["Oh. Hi. *Crescent sits down and smiles at her.*", "Oh. Hi."], hist)
        self.assertNotIn("Crescent sits", r["text"])

    def test_puppeting_note(self):
        m = build_messages(FAITH, "Crescent", [{"role": "user", "content": "*Faith hugs me and cries*"}], {"mode": "story", "state": {}, "words": (10, 30)})
        self.assertIn("attempt only", m[-1]["content"])


if __name__ == "__main__":
    unittest.main()
