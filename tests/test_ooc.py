import unittest

from tests import helpers as h
from crumble.llm import generate_reply
from crumble.prompt import build_messages
from crumble.rp.narrator import NARRATOR
from crumble.rp.ooc import clean_notes, finish_ooc, notes_block, ooc_messages, ooc_words

MIRA, REX = dict(h.SHY, id="mira"), dict(h.BOLD, id="rex")
GRP = {"name": "Crew", "scenario": "A diner at night.", "members": [MIRA, REX], "narrator": True}


def note(kind, text, who=()):
    return {"kind": kind, "text": text, "who": list(who)}


class NotesTests(unittest.TestCase):
    def test_clean_drops_junk_and_caps(self):
        raw = [note("correct", "  be   quieter  ", ["mira"]), {"kind": "bogus", "text": "x"}, {"kind": "setting", "text": ""},
               "nope", {"kind": "direct", "text": "y" * 2000, "who": "mira"}]
        out = clean_notes(raw)
        self.assertEqual([n["kind"] for n in out], ["correct", "direct"])
        self.assertEqual(out[0]["text"], "be quieter")
        self.assertEqual(len(out[1]["text"]), 600)
        self.assertEqual(out[1]["who"], [])                      # a non-list 'who' means everyone
        self.assertEqual(len(clean_notes([note("setting", str(i)) for i in range(40)])), 12)
        self.assertEqual(clean_notes(None), [])

    def test_solo_correction_applies_and_is_silent(self):
        b = notes_block(MIRA, clean_notes([note("correct", "Mira is not this chatty")]))
        self.assertIn("Mira is not this chatty", b)
        self.assertIn("never mentions", b)

    def test_group_correction_only_for_the_named_character(self):
        ns = clean_notes([note("correct", "stay guarded", ["mira"])], 12)
        self.assertIn("stay guarded", notes_block(MIRA, ns, GRP))
        self.assertEqual(notes_block(REX, ns, GRP), "")

    def test_setting_reaches_everyone(self):
        ns = clean_notes([note("setting", "It is now dawn at the pier")])
        for c in (MIRA, REX, NARRATOR):
            self.assertIn("now dawn at the pier", notes_block(c, ns, GRP))

    def test_direction_goes_to_target_and_narrator(self):
        ns = clean_notes([note("direct", "Rex storms out", ["rex"])])
        self.assertIn("Rex storms out", notes_block(REX, ns, GRP))
        self.assertIn("Rex storms out", notes_block(NARRATOR, ns, GRP))
        self.assertEqual(notes_block(MIRA, ns, GRP), "")

    def test_no_notes_no_block(self):
        self.assertEqual(notes_block(MIRA, []), "")


class PromptTests(unittest.TestCase):
    HIST = [{"role": "assistant", "content": "*looks up*"}, {"role": "user", "content": "hi"}]

    def bm(self, notes):
        return build_messages(MIRA, "Sam", self.HIST, {"mode": "story", "state": {}, "words": (20, 60), "ooc": clean_notes(notes)})

    def test_notes_reach_the_in_character_prompt(self):
        m = self.bm([note("setting", "The bar closed an hour ago")])
        self.assertIn("The bar closed an hour ago", m[0]["content"])
        self.assertIn("Follow the author's notes silently", m[-1]["content"])

    def test_absent_without_notes(self):
        m = self.bm([])
        self.assertNotIn("Author's notes", m[0]["content"])
        self.assertNotIn("author's notes", m[-1]["content"])


class StorytellerTests(unittest.TestCase):
    def test_words(self):
        self.assertEqual(ooc_words("ok", "short"), (10, 45))
        self.assertGreaterEqual(ooc_words("brainstorm some ideas for act two")[1], 200)
        lo, hi = ooc_words("why did she do that?")
        self.assertLess(hi, 120)

    def test_finish_cleans_label_wrapper_and_user_turn(self):
        self.assertEqual(finish_ooc("Storyteller: Sure, I'll tone her down.", "stop", "Sam")["text"], "Sure, I'll tone her down.")
        self.assertEqual(finish_ooc("(OOC: Sure thing.)", "stop", "Sam")["text"], "Sure thing.")
        self.assertEqual(finish_ooc("Fine.\nSam: and then", "stop", "Sam")["text"], "Fine.")
        r = finish_ooc("It could work. But the second part is cut off and goes", "length", "Sam")
        self.assertTrue(r["cut"])
        self.assertEqual(r["text"], "It could work.")
        self.assertTrue(finish_ooc("   ", "stop", "Sam")["empty"])

    def test_prompt_separates_story_from_ooc_chat(self):
        hist = [{"role": "assistant", "content": "*Mira wipes the counter.*"}, {"role": "user", "content": "I sit down."},
                {"role": "user", "content": "Can Mira be less chatty?", "ooc": "correct"},
                {"role": "assistant", "content": "Sure, I'll quiet her down.", "ooc": "correct"},
                {"role": "user", "content": "Also, what happens next?", "ooc": "discuss"}]
        m = ooc_messages(MIRA, "Sam", hist, {"words": (15, 60), "kind": "discuss", "notes": clean_notes([note("correct", "less chatty")])})
        self.assertEqual([x["role"] for x in m], ["system", "user", "assistant", "user"])
        s = m[0]["content"]
        self.assertIn("OUT OF CHARACTER", s)
        self.assertIn("Mira wipes the counter", s)                    # the story is context...
        self.assertNotIn("Can Mira be less chatty", s)                # ...the OOC talk is the conversation
        self.assertIn("less chatty", s)                               # notes already in force are known
        self.assertIn("Out of character", m[-1]["content"])           # the kind's instruction rides on the last turn
        self.assertNotIn("{{", s)


class GenerateTests(unittest.TestCase):
    def req(self, hist, **kw):
        return dict({"char": MIRA, "user": "Sam", "history": hist, "state": {}, "params": {"mode": "story", "think": False, "max_tokens": 200}}, **kw)

    def test_ooc_reply_is_not_policed_like_a_character(self):
        fake = h.install(h.FakeLLM(["As the author, I'd say her shyness could show through hesitation instead."]))
        hist = [{"role": "user", "content": "(( why is she so cold? ))", "ooc": "discuss"}]
        r = generate_reply(self.req(hist, kind="ooc", ooc={"kind": "discuss", "notes": []}), None)
        self.assertIn("shyness", r["text"])                           # no assistant-talk scrubbing, no persona guard
        self.assertEqual(len(fake.calls), 1)
        self.assertIn("OUT OF CHARACTER", fake.calls[0][0]["content"])

    def test_characters_never_see_ooc_messages(self):
        fake = h.install(h.FakeLLM(["*nods slowly.*"]))
        hist = [{"role": "assistant", "content": "*Mira looks up.*"},
                {"role": "user", "content": "ZEBRA-OOC keep her calmer", "ooc": "correct"},
                {"role": "assistant", "content": "ZEBRA-REPLY ok", "ooc": "correct"},
                {"role": "user", "content": "I wave."}]
        generate_reply(self.req(hist, kind="reply", ooc={"notes": [note("correct", "keep her calmer")]}), None)
        blob = " ".join(m["content"] for m in fake.calls[0])
        self.assertNotIn("ZEBRA", blob)
        self.assertIn("keep her calmer", blob)                        # the note, not the message, carries it
        self.assertEqual([m["role"] for m in fake.calls[0][1:]], ["assistant", "user"])

    def test_resume_has_its_own_tail(self):
        fake = h.install(h.FakeLLM(["*the door chimes.*"]))
        generate_reply(self.req([{"role": "assistant", "content": "*Mira waits.*"}], kind="resume"), None)
        self.assertIn("stepped out of the story", fake.calls[0][-1]["content"])


if __name__ == "__main__":
    unittest.main()
