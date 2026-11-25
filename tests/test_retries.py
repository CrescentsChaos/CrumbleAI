"""H8: a reply is regenerated only for hard failures, inside a time budget; every rule that trips is logged."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crumble import llm
from crumble.llm import generate_reply
from tests import helpers as h

AI = "*Rex nods.* As an AI language model, hello. Sit down."
HIST = [{"role": "user", "content": "hello there"}]


def req(replies, quick=False, **extra):
    fake = h.install(h.FakeLLM(replies))
    b = {"char": h.BOLD, "user": "Crescent", "history": HIST, "state": {}, "params": {"mode": "story", "think": False, "max_tokens": 200, "quick": quick}}
    b.update(extra)
    return fake, generate_reply(b, None)


class Policy(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(llm, "RETRY_LOG", False)
        p.start()
        self.addCleanup(p.stop)

    def test_an_empty_reply_always_retries(self):
        fake, r = req(["", "Sit down."])
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(r["text"], "Sit down.")

    def test_a_soft_rule_is_repaired_or_flagged_never_retried(self):
        fake, r = req([AI, "Sit down."])
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(r["retries"], 0)
        self.assertNotIn("language model", r["text"])
        self.assertEqual(r["flags"], ["ai_speak"])

    def test_a_soft_rule_can_be_brought_back_by_name(self):
        with mock.patch.object(llm, "SOFT_RETRY", {"ai_speak"}):
            fake, r = req([AI, "*Rex nods.* Sit down."])
            self.assertEqual(len(fake.calls), 2)
            self.assertEqual(r["flags"], [])
            fake, r = req([AI, "*Rex nods.* Sit down."], quick=True)     # never in Quick mode
            self.assertEqual(len(fake.calls), 1)

    def test_a_hard_failure_retries_and_the_note_reaches_the_prompt(self):
        fake, r = req(["Oh. Hi. *Crescent sits down and smiles at her.*", "Oh. Hi."])
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(r["text"], "Oh. Hi.")
        self.assertIn("Never do that", fake.calls[1][-1]["content"] + fake.calls[1][0]["content"])


class Budget(unittest.TestCase):
    DUP = '*Rex smiles.* "Hello again, Crescent."'

    def run_with_clock(self, times):
        clock = iter(times)
        with mock.patch.object(llm, "RETRY_LOG", False), mock.patch.object(llm.time, "monotonic", side_effect=lambda: next(clock)):
            return req([self.DUP] * 3, avoid=[self.DUP])      # a copy of the swipe it must differ from: a hard failure every time

    def test_a_third_attempt_that_would_break_the_budget_is_not_started(self):
        fake, r = self.run_with_clock([0, 1, 1, 2.5, 2.5, 4, 4, 5, 5, 6])    # attempt 1 took 1s, attempt 2 took 1.5s: a third would pass 2x
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(r["retry_log"][-1]["why_not"], "budget")

    def test_faster_retries_may_continue(self):
        fake, r = self.run_with_clock([0, 4, 4, 5, 5, 6, 6, 7])     # 4s, then 1s: two more 1s attempts still fit inside 8s
        self.assertEqual(len(fake.calls), 3)

    def test_the_first_retry_is_always_inside_the_budget(self):
        fake, r = self.run_with_clock([0, 3, 3, 4, 4, 9, 9, 10])
        self.assertGreaterEqual(len(fake.calls), 2)


class Log(unittest.TestCase):
    def test_every_tripped_rule_is_logged_without_the_text(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ROOT", Path(d)), mock.patch.object(llm, "RETRY_LOG", True):
            req([AI])
            line = json.loads((Path(d) / "data" / "retry_log.jsonl").read_text().splitlines()[-1])
        self.assertEqual(line["events"][0]["rules"], ["ai_speak"])
        self.assertFalse(line["events"][0]["retried"])
        self.assertNotIn("language model", json.dumps(line))

    def test_a_clean_reply_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(llm, "ROOT", Path(d)), mock.patch.object(llm, "RETRY_LOG", True):
            req(["*Rex shrugs.* Sit down."])
            self.assertFalse((Path(d) / "data" / "retry_log.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
