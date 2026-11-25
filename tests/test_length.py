import unittest

from tests import helpers as h
from crumble.llm import generate_reply
from crumble.textutil import cap_reply

FIVE = "hey\nwhat are you up to\ni was thinking about you\nanyway\nwanna hang out"


class LengthTests(unittest.TestCase):
    def test_texting_lines_follow_length(self):
        self.assertEqual(len(cap_reply(FIVE, "text", "short", 20).split("\n")), 2)
        self.assertEqual(len(cap_reply(FIVE, "text", "medium", 20).split("\n")), 3)
        self.assertEqual(len(cap_reply(FIVE, "text", "long", 20).split("\n")), 5)
        self.assertEqual(len(cap_reply(FIVE, "text", "auto", 20).split("\n")), 4)

    def test_roleplay_short_cut_to_whole_sentence(self):
        t = " ".join(f"This is sentence number {i} and it keeps going." for i in range(12))
        out = cap_reply(t, "story", "short", 45)
        self.assertLessEqual(len(out.split()), 60)
        self.assertTrue(out.endswith("."))
        self.assertEqual(cap_reply(t, "story", "auto", 45), t.strip())   # auto is left alone
        self.assertEqual(cap_reply("Short one.", "story", "short", 45), "Short one.")

    def test_end_to_end_and_prompt(self):
        fake = h.install(h.FakeLLM([FIVE]))
        b = {"char": h.SHY, "user": "Sam", "history": [{"role": "user", "content": "hi"}], "state": {},
             "params": {"mode": "text", "length": "short", "think": False, "max_tokens": 200}}
        r = generate_reply(b, None)
        self.assertEqual(len(r["text"].split("\n")), 2)
        self.assertIn("at most 2 lines", h.ptxt(fake.calls[0]))


if __name__ == "__main__":
    unittest.main()
