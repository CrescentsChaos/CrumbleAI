"""Regression tests: internal context must not leak into replies, entities and Markdown must come out well formed."""
import re
import unittest

from tests import helpers as h
from crumble import context, leak, memory
from crumble.llm import generate_reply
from crumble.prompt import build_messages
from crumble.textutil import finish_reply, tidy_markup, unescape

MIRA = {"id": "mira", "name": "Mira", "personality": "shy, quiet", "scenario": "Monday morning in the garage."}
SUMMARY = ("SETTING & STATE\nLocation: The garage\nCurrent State: Sam is tired.\nRELATIONSHIP DYNAMIC\nPrimary Dynamic: Friends.\n"
           "Tone: Warm.\nPIVOTAL MOMENTS\n- Sam gave Mira a necklace.")
STATE = {"mood": "happy", "energy": "medium", "affection": 72, "summary": SUMMARY, "facts": ["Sam likes tea"]}


def clean(raw, mode="story"):
    return finish_reply(raw, "stop", "Sam", "Mira", mode, others=["Rex"])


def system(**o):
    base = {"mode": "story", "state": STATE, "words": (10, 30), "clock": "Friday 3:15 PM", "gap_s": 700}
    base.update(o)
    return build_messages(MIRA, "Sam", [{"role": "user", "content": "hi"}], base)[0]["content"]


class StructuralLeaks(unittest.TestCase):
    def test_field_lines_and_headings_are_removed(self):
        t = clean('Location: The garage\nCurrent State: Sam is tired.\nPrimary Dynamic: Friends.\nSETTING & STATE\n*Mira nods.* "Sure."')["text"]
        self.assertEqual(t, '*Mira nods.* "Sure."')

    def test_story_clock_mood_and_ratings_are_removed(self):
        for raw in ['In the story it is Monday, around 9:00 AM (morning). "Hi."', '[Right now] Mira\'s current mood: happy; energy: medium. "Hi."',
                    '"Hi." (Affection: 72/100)', '*Mira is fond of them and close.* "Hi."', '[3:15 PM] "Hi."', '{{char}} says hi.']:
            r = clean(raw)
            for bad in ("In the story", "current mood", "72/100", "fond of them", "3:15", "{{"):
                self.assertNotIn(bad, r["text"], raw)
            self.assertTrue(r["scrubbed"], raw)

    def test_the_prompts_own_sentences_are_removed(self):
        for line in ("Let this shape warmth, openness, teasing and patience.", "Never mention numbers or scores.",
                     "Pick one or two of these per reply, vary them.", "Apply them silently."):
            self.assertEqual(clean(f'*Mira waves.* {line} "Hi."')["text"], '*Mira waves.* "Hi."')

    def test_every_block_the_prompt_writes_is_caught_if_echoed(self):
        s = system(amb={"place": {"name": "the garage", "indoors": True, "sense": "tools clinking"}, "weather": "rain", "indoors": True},
                   sim={"clock": "Monday, around 9:00 AM (morning)", "night": False, "daytime": True, "period": "morning"})
        grams = leak.corpus([s[s.index("=== PRIVATE"):s.index("=== END")]])
        for ln in ("Weather has physics: it follows its own logic, it does not change on a whim, and it affects what people say, wear, want and do.",
                   "Pick one or two of these per reply, vary them, and fold them into what Mira does and notices; never list them."):
            self.assertTrue(leak.find_echoes(ln, grams) or leak.scrub(ln, "Mira", ["Sam"])[1], ln)

    def test_legitimate_roleplay_is_untouched(self):
        for ok in ['"Location? The garage, obviously."', '"It is nine in the morning, Sam." *Mira checks the clock: 9:00 AM.*',
                   '"My mood: terrible today," *she mutters.*', '*Mira feels fond of Sam, and it scares her.* "Stay."',
                   '"The scene was awful." *Mira shudders at the memory of the story so far.*']:
            self.assertEqual(clean(ok)["text"], ok)
            self.assertEqual(clean(ok)["scrubbed"], [])

    def test_echoed_background_is_detected_but_not_deleted_from_dialogue(self):
        grams = leak.corpus(["Sam gave Mira a necklace on her birthday after the long class ended"])
        copied = "Sam gave Mira a necklace on her birthday after the long class ended"
        self.assertTrue(leak.find_echoes(copied, grams))
        self.assertEqual(leak.find_echoes("You gave me a necklace on my birthday.", grams), [])
        self.assertIn("necklace", leak.drop_echo_sentences(f'"{copied}." *waves*', grams))   # spoken words stay
        self.assertNotIn("necklace", leak.drop_echo_sentences(f"{copied}. *waves*", grams))   # a pasted narration line goes


class EntitiesAndMarkdown(unittest.TestCase):
    def test_entities_are_decoded_once(self):
        self.assertEqual(unescape("&quot;I can&#39;t&quot; &amp; &lt;sigh&gt; &amp;quot;ok&amp;quot;"), "\"I can't\" & <sigh> \"ok\"")
        self.assertEqual(unescape("R&D and AT&T &notreal;"), "R&D and AT&T &notreal;")
        self.assertEqual(clean("&quot;Hello,&quot; she says.")["text"], '"Hello," she says.')

    def test_multiline_action_keeps_the_dialogue_after_it(self):
        t = clean('*She walks over\nand sits down.* "Hey."')["text"]
        self.assertIn('"Hey."', t)
        self.assertEqual(t.count("*") % 2, 0)

    def test_bold_triple_and_underscore_actions_become_actions(self):
        for raw in ('**Mira smiles.** "Hey."', '***Mira smiles.*** "Hey."', '_Mira smiles._ "Hey."'):
            self.assertEqual(clean(raw)["text"], '*Mira smiles.* "Hey."', raw)
        self.assertEqual(tidy_markup('I said **no** way'), "I said **no** way")      # emphasis stays emphasis
        self.assertEqual(tidy_markup("use snake_case_names here"), "use snake_case_names here")

    def test_no_nested_stars_from_asides(self):
        self.assertEqual(clean('*She waits (quietly) here.* "Okay." (sighs) Fine.')["text"], '*She waits (quietly) here.* "Okay." *sighs* Fine.')
        self.assertNotIn("**", clean('*Mira [sighs] nods.* "Hi."')["text"])

    def test_touching_quotes_and_spans_are_not_merged_or_dropped(self):
        t = '"Is it a dog?" "Yes, he was big." *waves*'
        self.assertEqual(clean(t)["text"], t)

    def test_block_markdown_is_stripped(self):
        self.assertEqual(clean('### Mira\n"Hey."')["text"], '"Hey."')
        self.assertEqual(clean('```\nhey\n```')["text"], "hey")


class PromptSeparation(unittest.TestCase):
    def test_private_context_sits_between_markers_with_a_usage_rule(self):
        s = system()
        a, b = s.index(context.START), s.index(context.END)
        inside = s[a:b]
        for want in ("What has happened so far", "In the story it is" if False else "Mira currently feels happy", "Sam likes tea"):
            self.assertIn(want, inside)
        self.assertIn("[How to use the private background]", s[b:])
        self.assertLess(s.index("[Mira - Core]"), a)

    def test_summary_form_is_not_in_the_prompt(self):
        s = system()
        for bad in ("SETTING & STATE", "RELATIONSHIP DYNAMIC", "PIVOTAL MOMENTS", "Location:", "Current State:", "Primary Dynamic:", "Tone:"):
            self.assertNotIn(bad, s)
        self.assertIn("takes place at the garage", s)
        self.assertIn("Sam gave Mira a necklace", s)

    def test_no_label_value_lines_for_state_and_no_nested_brackets(self):
        s = system()
        self.assertNotIn("Story time:", s)
        self.assertNotIn("current mood:", s)
        self.assertNotRegex(s, r"\[[^\]\n]*\[[^\]\n]*\]")
        self.assertNotIn("{CH}", s)
        self.assertNotIn("{USER}", s)
        self.assertNotIn("Reply as", s)

    def test_headings_are_not_glued_to_the_previous_rule(self):
        self.assertRegex(system(), r"\n\nCONVERSATION AND CONTINUITY:\n")

    def test_recap_handles_free_text_and_empty_fields(self):
        self.assertEqual(context.recap("Sam and Mira met at the pier."), "Sam and Mira met at the pier.")
        self.assertEqual(context.recap("SETTING & STATE\nLocation: Not established\nTone: tense"), "The mood between them has been tense.")

    def test_old_leaks_in_saved_history_are_not_fed_back(self):
        hist = [{"role": "user", "content": "hi"},
                {"role": "assistant", "content": 'Location: The garage\nCurrent State: tired\n*Mira nods.* &quot;Hi.&quot;'},
                {"role": "user", "content": "how are you"}]
        msgs = build_messages(MIRA, "Sam", hist, {"mode": "story", "state": {}, "words": (10, 30)})
        said = [m["content"] for m in msgs[1:] if m["role"] == "assistant"][0]
        self.assertEqual(said, '*Mira nods.* "Hi."')


class Pipeline(unittest.TestCase):
    def run_reply(self, replies, hist=None, state=None, **extra):
        fake = h.install(h.FakeLLM(replies))
        b = {"char": MIRA, "user": "Sam", "history": hist or [{"role": "user", "content": "hello there"}], "state": state or {},
             "params": {"mode": "story", "think": False, "max_tokens": 200, "quick": True}}
        b.update(extra)
        return fake, generate_reply(b, None)

    def test_leaked_state_never_reaches_the_chat(self):
        _, r = self.run_reply(['Location: The garage\nStory time: Monday 9:00 AM\n*Mira nods.* "Morning, Sam."'])
        self.assertEqual(r["text"], '*Mira nods.* "Morning, Sam."')
        self.assertIn("field", r["leaks"])

    def test_a_reply_that_is_only_state_is_retried(self):
        fake, r = self.run_reply(["Location: The garage\nMood: happy", '*Mira nods.* "Morning, Sam."'])
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(r["text"], '*Mira nods.* "Morning, Sam."')
        self.assertIn("field names", fake.calls[1][-1]["content"])

    def test_copying_the_background_is_retried(self):
        copied = "Sam gave Mira a necklace on her birthday after the long class ended"
        st = {"summary": f"PIVOTAL MOMENTS\n- {copied}"}
        fake, r = self.run_reply([f"*Mira smiles.* {copied}.", '*Mira smiles.* "Nice to see you."'], state=st)
        self.assertEqual(len(fake.calls), 2)
        self.assertNotIn("necklace", r["text"])


class TrackerLabels(unittest.TestCase):
    def test_other_characters_are_not_the_tracked_one(self):
        fake = h.install(h.FakeLLM(track={"mood": "calm", "affection_delta": 0, "facts": []}))
        hist = [{"role": "user", "content": "hi all"}, {"role": "assistant", "content": "*Rex grins.* Hey.", "cid": "rex", "name": "Rex"},
                {"role": "assistant", "content": "Morning.", "cid": "mira", "name": "Mira"}]
        memory.track({"char": MIRA, "user": "Sam", "history": hist, "state": {}, "group": "g1", "mem": {"on": False}})
        ask = fake.calls[-1][-1]["content"]
        self.assertIn("Rex (another character, not Mira)", ask)
        self.assertIn("Mira (the character)", ask)


if __name__ == "__main__":
    unittest.main()
