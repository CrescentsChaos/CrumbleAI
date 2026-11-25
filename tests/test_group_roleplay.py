"""Regression tests for group roleplay: prompt separation, repeated lines between speakers, swipes, leaks in a group reply."""
import unittest
from unittest import mock

from tests import helpers as h
from crumble import context, repeat
from crumble import llm
from crumble.llm import generate_reply
from crumble.prompt import build_messages

MIRA = {"id": "mira", "name": "Mira", "personality": "shy, quiet", "description": "A library assistant."}
REX = {"id": "rex", "name": "Rex", "personality": "bold, loud, sarcastic", "description": "A mechanic."}
GRP = dict(name="Garage Crew", scenario="Monday morning in the garage. Rain on the roof.", members=[MIRA, REX], narrator=False)
HIST = [{"role": "user", "content": "Hey everyone, rough morning."},
        {"role": "assistant", "content": '*Rex wipes his hands.* "You look like death, Sam."', "cid": "rex", "name": "Rex"},
        {"role": "user", "content": "@Mira can you help me?"}]
STATE = {"summary": "SETTING & STATE\nLocation: The garage\nCurrent State: Sam is tired.", "mood": "calm", "affection": 60}


def group_req(replies, who=MIRA, cue=None, quick=True, hist=None, **extra):
    fake = h.install(h.FakeLLM(replies))
    b = {"char": who, "grp": GRP, "user": "Sam", "history": hist or HIST, "state": STATE, "kind": "reply", "cue": cue or {"why": "chat", "by": "Rex"},
         "params": {"mode": "story", "think": False, "max_tokens": 200, "quick": quick}}
    b.update(extra)
    return fake, generate_reply(b, None)


class GroupPrompt(unittest.TestCase):
    def msgs(self, cue):
        return build_messages(MIRA, "Sam", HIST, {"mode": "story", "state": STATE, "words": (10, 30), "group": GRP, "tail": cue,
                                                  "private": []})

    def test_cue_is_inside_the_private_note_not_a_bare_parenthesis(self):
        last = self.msgs("(Sam just addressed Mira directly. Answer them. Write only Mira's next message.)")[-1]["content"]
        self.assertNotIn("\n\n(Sam just addressed", last)
        note = last[last.index("<<PRIVATE NOTE"):]
        self.assertIn("Sam just addressed Mira directly", note)
        self.assertTrue(note.endswith(">>"))
        self.assertIn("never begin your message with a name and a colon", note)

    def test_group_summary_and_scene_are_private_prose(self):
        s = h.ptxt(self.msgs("(x)"))
        self.assertTrue(s.index(context.START) < s.index("takes place at the garage") < s.index(context.END))
        self.assertNotIn("Location:", s)
        self.assertIn("already said their piece", s)            # Rex spoke: Mira is told not to repeat him

    def test_a_group_member_leak_in_history_is_cleaned_for_everyone(self):
        hist = HIST[:1] + [{"role": "assistant", "content": 'Location: The garage\n*Rex nods.* &quot;Fine.&quot;', "cid": "rex", "name": "Rex"}] + HIST[2:]
        m = build_messages(MIRA, "Sam", hist, {"mode": "story", "state": {}, "words": (10, 30), "group": GRP})
        self.assertIn('Rex: *Rex nods.* "Fine."', m[1]["content"])
        self.assertNotIn("Location:", m[1]["content"])


class GroupReplies(unittest.TestCase):
    def test_leaked_state_in_a_group_reply_is_removed(self):
        _, r = group_req(['Current State: Sam is tired.\nScene: the garage\n*Mira looks up.* "Of course."'])
        self.assertEqual(r["text"], '*Mira looks up.* "Of course."')

    def test_second_speaker_copying_the_first_is_retried_even_in_quick_mode(self):
        line = '*Rex wipes his hands.* "You look like death, Sam."'
        fake, r = group_req([line, '*Mira fidgets with her sleeve.* "I can try. What do you need?"'])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("someone else in the scene", fake.calls[1][-1]["content"])
        self.assertNotIn("look like death", r["text"])

    def test_a_different_reply_is_not_retried(self):
        fake, r = group_req(['*Mira nods.* "Sure, sit down."'])
        self.assertEqual(len(fake.calls), 1)

    def test_a_repeated_own_line_is_retried_in_quick_mode(self):
        hist = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": '*Mira shrugs.* "I guess it is fine."', "cid": "mira", "name": "Mira"},
                {"role": "user", "content": "really?"}]
        fake, r = group_req(['*Mira shrugs.* "I guess it is fine."', '"Honestly? No. It is not."'], hist=hist, quick=True)
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Not", r["text"].title())

    def test_pure_duplicate_of_someone_else_is_a_silent_pass_unless_addressed(self):
        line = '*Rex wipes his hands.* "You look like death, Sam."'
        _, r = group_req([line, line, line], cue={"why": "chat", "by": "Rex", "pass": True})
        self.assertTrue(r.get("pass"))
        _, r = group_req([line, line, line], cue={"why": "mention", "by": "Sam"})
        self.assertFalse(r.get("pass"))
        self.assertTrue(r["text"])

    def test_least_repetitive_attempt_wins_when_all_repeat(self):
        a = '*Rex wipes his hands.* "You look like death, Sam."'
        b = '*Rex wipes his hands.* "You look like death, Sam. Really."'
        c = '*Mira wipes a table.* "You look like death warmed over, Sam, honestly."'
        with mock.patch.object(llm, "TIME_BUDGET", 100):    # the replies come back instantly here, so pin the clock out of it
            _, r = group_req([a, b, c], cue={"why": "mention", "by": "Sam"}, quick=False)
        self.assertEqual(r["text"], c)

    def test_swipe_alternatives_are_not_repeated(self):
        old = '*Mira smiles.* "Hello again, Sam."'
        fake, r = group_req([old, '*Mira tilts her head.* "Back so soon?"'], avoid=[old], hist=HIST[:2] + [HIST[2]])
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Back so soon", r["text"])


class RepeatScore(unittest.TestCase):
    def test_scores(self):
        a = 'She smiles. "I guess it is fine, really, it is fine."'
        self.assertGreaterEqual(repeat.score(a, a), repeat.HARD)
        self.assertGreaterEqual(repeat.score('*smiles* "I guess it is fine, really, it is fine." Then she leaves the room quickly.', a), repeat.SOFT)
        self.assertLess(repeat.score('"Absolutely not. Put that down right now."', a), repeat.SOFT)
        self.assertEqual(repeat.score("Fine.", "Fine."), 0.0)      # one-word replies are not "repeats"


if __name__ == "__main__":
    unittest.main()
