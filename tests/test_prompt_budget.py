"""H12: the static rules stay short, one-per-idea, well formed, and shrink with the model size."""
import re
import unittest
from tests.helpers import ptxt

from crumble import prompt
from crumble.config import model_tier
from crumble.prompt import build_messages

FAITH = {"id": "faith", "name": "Faith", "personality": "Calm. Introverted.", "scenario": "Monday morning."}
HIST = [{"role": "user", "content": "hi"}]


def system(tier=1, group=False, **extra):
    o = {"mode": "story", "state": {}, "words": (10, 30), "tier": tier}
    if group:
        o["group"] = {"name": "G", "members": [FAITH, {"id": "rex", "name": "Rex"}]}
    o.update(extra)
    return ptxt(build_messages(FAITH, "Crescent", HIST, o))


class Budget(unittest.TestCase):
    def test_smaller_models_get_fewer_rules(self):
        a, b, c = (len(system(t)) for t in (0, 1, 2))
        self.assertLess(a, b)
        self.assertLess(b, c)

    def test_budget_per_tier(self):    # tokens ~ chars / 4. Most of what is left is the intimacy block, which is left alone on purpose
        for tier, cap in ((0, 3300), (1, 3500), (2, 3600)):
            self.assertLess(len(system(tier)) // 4, cap, f"tier {tier}")

    def test_group_adds_little(self):
        self.assertLess(len(system(1, group=True)) - len(system(1)), 2500)


class WellFormed(unittest.TestCase):
    def test_no_glued_bullets(self):
        for tier in (0, 1, 2):
            s = system(tier, group=True)
            self.assertEqual(re.findall(r"[.!?\"”')]- [A-Z{]", s), [], f"tier {tier}")
            self.assertNotIn("- - ", s)

    def test_every_bullet_is_on_its_own_line(self):
        s = system(1)
        for line in s.split("\n"):
            self.assertLessEqual(len(re.findall(r"(?:^|\s)- [A-Z{]", line)), 1, line[:120])

    def test_no_typos(self):
        s = system(1)
        for bad in (" wont ", " dont ", " cant ", " doesnt "):
            self.assertNotIn(bad, s)


class NoRepeats(unittest.TestCase):
    def test_user_is_never_written_for_is_said_once_in_the_rules(self):
        s = system(1).split("<<PRIVATE NOTE")[0]     # the rules, not the per-turn note
        self.assertEqual(len(re.findall(r"(?i)never write[^.\n]{0,40}(?:words|dialogue)", s)), 1)

    def test_no_banned_phrase_list(self):    # a list of forbidden quotes makes small models say them; prompts describe, the lexicon filter catches
        s = system(2)
        for phrase in ("what brings you here", "I'm all ears", "your feelings are valid", "is there anything else"):
            self.assertNotIn(phrase, s)

    def test_group_rule_survives_realism_off(self):
        self.assertIn("group roleplay", system(1, group=True, realism=False))

    def test_asterisk_rule_comes_from_the_style_block_only(self):    # text and call modes forbid asterisks; the core must not demand them
        s = system(1, mode="text")
        self.assertEqual(s.count("enclosed in *asterisks*"), 0)
        self.assertIn("No narration, no actions, no asterisks", s)


class Tier(unittest.TestCase):
    def test_from_file_name(self):
        for name, tier in (("Llama-3.1-8B-Instruct-Q4_K_M.gguf", 0), ("mistral-7b-v0.3.gguf", 0), ("gemma-2-9b-it.gguf", 1),
                           ("Qwen3-30B-A3B-Q4.gguf", 2), ("Llama-3.3-70B.gguf", 2), ("Mixtral-8x7B.gguf", 1), ("mystery.gguf", 1)):
            self.assertEqual(model_tier(name), tier, name)

    def test_register_hook_still_finds_its_rule(self):    # personality.register swaps the rule that starts with this text
        self.assertTrue(any(t.startswith("Talk like a real person") for _, t in prompt.REALISM))


if __name__ == "__main__":
    unittest.main()
