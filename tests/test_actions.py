import unittest

from crumble.sanitize import enclose_narration
from crumble.textutil import cap_reply, preview_reply


class ActionsAndPreview(unittest.TestCase):
    def test_every_action_is_wrapped(self):
        out = enclose_narration('*Messmer nods.* His eyes narrow. "Speak." Slowly, he turns toward the fire. The wind howls.', "Messmer", "Crescent")
        self.assertEqual(out, '*Messmer nods. His eyes narrow.* "Speak." *Slowly, he turns toward the fire. The wind howls.*')

    def test_plain_speech_is_not_wrapped(self):
        out = enclose_narration("I know thee not. Where hast thou been?", "Messmer", "Crescent")
        self.assertNotIn("*", out)

    def test_preview_never_longer_than_final(self):
        raw = "Hello there friend. How are you today? I am fine. Truly fine. Quite fine indeed. Very fine."
        final = cap_reply(raw, "story", "short", 10)
        for k in range(1, len(raw) + 1):
            pv = preview_reply(raw[:k], "Sam", "Rex", "story", [], True, "short", 10, True)
            self.assertLessEqual(len(pv), max(len(final), 1) + 2)

    def test_preview_closes_open_action(self):
        self.assertEqual(preview_reply("*He turns slowly", "Sam", "Rex", "story", [], True, "auto", 40, True), "*He turns slowly*")


if __name__ == "__main__":
    unittest.main()
