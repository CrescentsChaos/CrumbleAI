"""Tests for the contextual memory overhaul: extraction, attribution, persistence, retrieval, injection, conflicts, restarts, corruption, multi-character roleplay.

Retrieval thresholds are measured by tools/memory_bench.py. Two things are kept apart on purpose:
    TUNED     the cases the system was developed against (tools.memory_bench.CASES, HELDOUT): high thresholds, regression guards
    HELDOUT2  cases written after tuning and run once before anything else changed: a lower floor, the honest generalization estimate
"""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests import helpers as h
from crumble import recall, storage, vault
from crumble.llm import generate_reply
from crumble.recall import entities as en, extract as ex, ops, semantic, store
from tools import memory_bench as mb
from tools.memory_heldout import HELDOUT, HELDOUT2, HELDOUT2_UNKNOWN, HELDOUT_UNKNOWN

U, C = "Tonoy", "Mira"
ON = {"on": True, "depth": "standard", "learn": True}
ROOT = Path(__file__).resolve().parent.parent


def convo(*pairs, name=C):
    return mb.chat(list(pairs), name=name)


def ingest(pairs, **kw):
    st, hist = {}, convo(*pairs)
    recall.ingest(st, hist, user=U, char=C, **kw)
    return st, hist


def items(st, **match):
    return [i for i in st["mem"]["items"] if all(i.get(k) == v for k, v in match.items())]


# ------------------------------------------------------------------ 1. extraction
class ExtractionTests(unittest.TestCase):
    def test_what_the_character_does_is_remembered_not_only_what_the_user_says(self):
        st, _ = ingest([("It's my birthday.", "*Mira smiles.* *She hands you a small silver locket with a tiny moon on it.*")])
        g = items(st, kind="gift")
        self.assertEqual(len(g), 1)
        self.assertIn("silver locket", g[0]["text"])
        self.assertEqual((g[0]["who"], g[0]["about"]), ("{{char}}", ["{{user}}"]))

    def test_promises_plans_secrets_decisions_are_recognised_and_attributed(self):
        st, _ = ingest([("Meet me at the old pier at nine tomorrow, okay?", "I promise I'll be there at nine."),
                        ("Don't tell anyone, I'm writing a novel.", "My lips are sealed."),
                        ("What now?", "We agreed to leave for the mountains at dawn.")])
        self.assertEqual(items(st, kind="promise")[0]["who"], "{{char}}")
        self.assertEqual(items(st, kind="plan")[0]["who"], "{{user}}")
        self.assertEqual(items(st, kind="secret")[0]["who"], "{{user}}")
        self.assertTrue(items(st, kind="decision"))
        self.assertTrue(items(st, kind="promise")[0]["open"])

    def test_hypotheticals_jokes_and_questions_are_never_stored_as_events(self):
        r = mb.hypotheticals()
        self.assertEqual(r["stored_as_real"], 0)
        self.assertEqual(r["real_flagged_hypothetical"], 0, "real statements must not be mistaken for imagined ones")
        st, _ = ingest([("What if I kissed you right now?", "*Mira blushes.* Don't tease me.")])
        self.assertEqual([i for i in st["mem"]["items"] if i.get("who") == "{{user}}"], [], "a question is not something that happened")
        self.assertFalse(items(st, kind="event", who="{{user}}"))

    def test_a_hypothetical_that_is_kept_is_labelled_when_retrieved(self):
        st, hist = ingest([("Imagine we live in a castle by the sea.", "*Mira laughs.* Sure.")])
        self.assertEqual(items(st, kind="hypothetical")[0]["status"], "hypothetical")
        r = mb.retrieve(st, hist, "what if we lived in a castle by the sea, remember imagining it?")
        if "castle" in r["block"]:
            self.assertIn("only imagined", r["block"])

    def test_hearsay_is_a_claim_with_the_speaker_not_a_fact(self):
        st, _ = ingest([("Marcus told me he owes the baker fifty coins.", "Typical Marcus.")])
        c = items(st, kind="claim")[0]
        self.assertEqual((c["status"], c["who"], c["rsrc"]), ("uncertain", "Marcus", "report"))
        self.assertIn("unverified", c["text"])

    def test_hedged_statements_are_uncertain(self):
        st, _ = ingest([("I think Garrick took the lantern last night.", "Maybe.")])
        for i in st["mem"]["items"]:
            self.assertNotEqual(i.get("status", "confirmed"), "confirmed", i["text"])

    def test_every_memory_is_grounded_in_the_chat(self):
        """Never fabricate: the evidence of every stored memory is a quote that is really in the message it came from."""
        rng = random.Random(4)
        pairs = [(c[1], c[2]) for c in mb.CASES] + [(c[1], c[2]) for c in HELDOUT] + mb.fill(20, rng)
        st, hist = ingest(pairs)
        norm = ex.norm
        checked = 0
        for i in st["mem"]["items"]:
            if i.get("src") != "rule" or not i.get("evid") or i.get("msg", -1) < 0:
                continue
            src = norm(hist[i["msg"]]["content"])
            first = norm(i["evid"].rstrip("…")).split("  ")[0]
            self.assertIn(first[:60], src, f"{i['text']!r} is not backed by message {i['msg']}")
            checked += 1
        self.assertGreater(checked, 20)

    def test_chatter_is_not_stored(self):
        st, _ = ingest(mb.fill(30, random.Random(1)))
        self.assertLessEqual(len(st["mem"]["items"]), 3, [i["text"] for i in st["mem"]["items"]])

    def test_out_of_character_talk_and_deliberate_lies_are_not_facts(self):
        hist = [{"role": "user", "content": "I live in Atlantis.", "ooc": True}, {"role": "assistant", "content": "I am the queen of Mars, trust me.", "name": C, "dyn": {"quirk": "lie"}}]
        st = {}
        recall.ingest(st, hist, user=U, char=C)
        self.assertEqual(st["mem"]["items"], [])


# ------------------------------------------------------------------ 2. attribution & multi-character
class AttributionTests(unittest.TestCase):
    def test_each_fact_goes_to_the_one_who_said_it(self):
        r = mb.attribution()
        self.assertEqual(r["correct"], r["asked"], r)

    def test_a_whisper_reaches_only_the_one_it_was_whispered_to(self):
        w = mb.whisper()
        self.assertEqual(w, {"Mira": False, "Rex": True})

    def test_pronouns_never_survive_into_a_stored_line(self):
        st, _ = ingest([("Hand me that.", "*She hands you the old brass key.* It opens the cellar door.")])
        for i in st["mem"]["items"]:
            if i.get("kind") == "gift":
                self.assertNotRegex(i["text"].split("(")[0], r"\b(?:she|he|you|your|me)\b", i["text"].split("(")[0])

    def test_same_words_from_two_speakers_stay_two_memories(self):
        hist = [{"role": "user", "content": "I promise I'll bring the map tomorrow at nine."}, {"role": "assistant", "name": C, "content": "I promise I'll bring the map tomorrow at nine."}]
        st = {}
        recall.ingest(st, hist, user=U, char=C)
        self.assertEqual(sorted(i["who"] for i in items(st, kind="promise")), ["{{char}}", "{{user}}"])

    def test_questions_about_i_versus_you_prefer_the_right_speaker(self):
        st, hist = ingest([("*I hand her a worn leather journal.*", "Oh."), ("Later...", "*She presses a brass key into your palm.* It opens the cellar.")])
        r = mb.retrieve(st, hist, "What did I give you?")
        self.assertIn("journal", r["trace"][0]["text"])
        r = mb.retrieve(st, hist, "What did you give me?")
        self.assertIn("key", r["trace"][0]["text"])

    def test_group_members_do_not_get_each_others_private_secrets(self):
        names = ["Mira", "Garrick", "Rex"]
        hist = [{"role": "user", "content": "Well?"}, {"role": "assistant", "name": "Garrick", "content": "*Garrick whispers to @Rex* Don't tell anyone, the vault key is under the fountain."}]
        mira, rex = {}, {}
        recall.ingest(mira, hist, user=U, char="Mira", group_names=names, viewer="Mira")
        recall.ingest(rex, hist, user=U, char="Rex", group_names=names, viewer="Rex")
        self.assertFalse(any("vault key" in i["text"] for i in mira["mem"]["items"]))
        self.assertTrue(any("vault key" in i["text"] for i in rex["mem"]["items"]))
        r = recall.select(mira, hist, user=U, char="Mira", cfg=recall.settings(ON), turn=3)
        self.assertNotIn("vault key", r["block"])


# ------------------------------------------------------------------ 3. conflicts & chronology
class ConflictTests(unittest.TestCase):
    def test_a_newer_statement_replaces_but_the_old_one_is_kept(self):
        r = mb.contradictions()
        for k in ("lisbon_kept_as_outdated", "porto_current", "answer_has_porto", "answer_hides_lisbon", "history_query_sees_lisbon", "replaced_link"):
            self.assertTrue(r[k], (k, r))

    def test_a_less_reliable_statement_does_not_overwrite_a_reliable_one(self):
        m = store.ensure({}, U, C)
        base = dict(kind="fact", layer="semantic", subj="user", imp=.7, who="{{user}}", msg=0, slot="{{user}}:lives", about=[], evid="x", known_by=[], when="", status="confirmed")
        ops.commit(m, [dict(base, text="{{user}} lives in Lisbon", rsrc="user")], U, C)
        ops.commit(m, [dict(base, text="{{user}} lives in Madrid", rsrc="report", msg=5)], U, C)
        lis = [i for i in m["items"] if "Lisbon" in i["text"]][0]
        mad = [i for i in m["items"] if "Madrid" in i["text"]][0]
        self.assertEqual(lis.get("status", "confirmed"), "confirmed")
        self.assertEqual(mad["status"], "uncertain")

    def test_corroboration_upgrades_hearsay_and_rollback_undoes_it(self):
        m = store.ensure({}, U, C)
        base = dict(layer="episodic", subj="bond", imp=.6, about=[], evid="x", known_by=[], when="", slot="", obj="")
        ops.commit(m, [dict(base, kind="claim", text="Garrick said (per {{user}}, second-hand, unverified): Garrick saw the baron near the harbor", who="Garrick", about=["Garrick"],
                            status="uncertain", rsrc="report", msg=1)], U, C)
        claim = m["items"][0]
        ops.commit(m, [dict(base, kind="event", text="Garrick saw the baron near the harbor at night", who="Garrick", about=["Garrick"], status="confirmed", rsrc="scene", msg=4)], U, C)
        self.assertEqual(claim["status"], "confirmed")
        self.assertTrue(claim["confirmed_by"])
        ops.rollback(m, 4)
        self.assertEqual(claim["status"], "uncertain", "removing the confirming message removes the confirmation")

    def test_accusations_make_both_accounts_disputed_and_both_are_kept(self):
        st, _ = ingest([("Garrick said he saw you with the baron last night.", "*Mira stiffens.* Garrick is lying.")])
        cl = items(st, kind="claim")
        self.assertEqual(len(cl), 2)
        self.assertEqual({c["status"] for c in cl}, {"disputed"})
        self.assertEqual({c["who"] for c in cl}, {"Garrick", "{{char}}"})

    def test_promise_is_closed_when_kept_or_broken_and_history_is_preserved(self):
        st, _ = ingest([("Meet me at the old pier at nine tomorrow, okay?", "I promise I'll be there at nine."), ("*Next evening*", "*Mira arrived at the old pier at nine and waited.*")])
        p = items(st, kind="promise")[0]
        self.assertFalse(p["open"])
        self.assertEqual(p["outcome"], "kept")
        st2, _ = ingest([("Meet me at the old pier at nine tomorrow, okay?", "I promise I'll be there at nine."), ("*Next evening*", "*Mira never came to the old pier at nine.*")])
        self.assertEqual(items(st2, kind="promise")[0]["outcome"], "broken")

    def test_relationships_have_a_timeline_and_endings_are_kept(self):
        st, _ = ingest([("Elena is my wife.", "Congratulations."), ("Filler.", "Mm."), ("Elena and I broke up last week.", "I'm sorry.")])
        tl = en.timeline(st["mem"], "{{user}}", "Elena", user=U, char=C)
        texts = [t["text"] for t in tl]
        self.assertTrue(any("wife" in t for t in texts), texts)
        wife = [r for r in st["mem"]["rels"] if r["rel"] == "wife"]
        self.assertTrue(wife, st["mem"]["rels"])
        self.assertIsNotNone(wife[0]["to"], "the break-up ends the marriage entry (kept, with an end turn)")
        self.assertTrue(any(r["rel"] == "ended" for r in st["mem"]["rels"]))
        m = {}
        en.link_rel(m, "Marcus", "Elena", "married", turn=1)
        en.link_rel(m, "Marcus", "Elena", "enemies", turn=9)
        self.assertEqual([(r["rel"], r["to"]) for r in m["rels"]], [("married", 9), ("enemies", None)])

    def test_ingest_is_idempotent_and_does_not_inflate_importance(self):
        st, hist = ingest([("I'm allergic to shellfish.", "Noted.")] * 1)
        view = lambda: [(i["id"], i["text"], i["imp"], i.get("status"), i.get("seen"), i.get("ver")) for i in st["mem"]["items"]]
        recall.ingest(st, hist, user=U, char=C)
        before = view()
        for _ in range(5):
            r = recall.ingest(st, hist, user=U, char=C)
            self.assertEqual((r["read"], r["added"], r["rolled_back"]), (0, [], 0))
        self.assertEqual(view(), before)

    def test_rewinding_the_chat_undoes_what_was_learned_from_it(self):
        st, hist = ingest([("Hello.", "Hi."), ("I'm allergic to shellfish.", "Noted."), ("My brother Kael is a blacksmith.", "Nice.")])
        self.assertTrue(any("shellfish" in i["text"] for i in st["mem"]["items"]))
        recall.ingest(st, hist[:2], user=U, char=C)
        self.assertFalse(any("shellfish" in i["text"] for i in st["mem"]["items"]))
        self.assertFalse(any("Kael" in i["text"] for i in st["mem"]["items"]))
        self.assertTrue(st["mem"]["tomb"], "rolled-back memories are tombstoned so a stale copy cannot resurrect them")

    def test_editing_an_old_message_replaces_what_it_taught(self):
        st, hist = ingest([("My dog is called Biscuit.", "Cute."), ("Filler.", "Mm."), ("More filler.", "Mm.")])
        hist[0] = dict(hist[0], content="My dog is called Waffles.")
        recall.ingest(st, hist, user=U, char=C)
        texts = " ".join(i["text"] for i in st["mem"]["items"] if i.get("status", "confirmed") == "confirmed")
        self.assertIn("Waffles", texts)
        self.assertNotIn("Biscuit", texts)


# ------------------------------------------------------------------ 4. retrieval quality (measured)
class RetrievalTests(unittest.TestCase):
    def test_tuned_cases_direct_and_indirect_across_distances(self):
        res = mb.retrieval()
        for k, v in res.items():
            self.assertGreaterEqual(v, .94, (k, v, mb.retrieval_failures()))

    def test_held_out_cases(self):
        """HELDOUT2 was written after tuning, so this is the honest number. Its first run was 0.67 direct / 0.42 indirect at 60 turns of distance;
        the floor here guards against going below what was measured after the general fixes that followed."""
        res = {}
        for kind, col in (("direct", 4), ("indirect", 5)):
            ok = 0
            for idx, c in enumerate(HELDOUT2):
                rng = random.Random(200 + idx)
                st, h_ = {}, mb.chat([(c[1], c[2])] + mb.fill(60, rng, idx))
                recall.ingest(st, h_, user=U, char=C)
                ok += mb.hit(mb.retrieve(st, h_, c[col]), c[3])
            res[kind] = ok / len(HELDOUT2)
        self.assertGreaterEqual(res["direct"], .8, res)
        self.assertGreaterEqual(res["indirect"], .6, res)

    def test_what_is_retrieved_is_mostly_on_target(self):
        n = mb.noise()
        self.assertLessEqual(n["avg_items"], 2.5)
        self.assertLessEqual(n["avg_off_target"], .5, n)

    def test_meaning_bridges_different_words(self):
        st, hist = ingest([("Look.", "*Mira hands you a small silver locket with a tiny moon on it.*")] + mb.fill(40, random.Random(2)))
        r = mb.retrieve(st, hist, "Who gave me this pendant?")
        self.assertIn("locket", r["block"])
        self.assertIn("meaning", " ".join(t["why"] for t in r["trace"]))

    def test_a_misspelling_still_finds_it(self):
        st, hist = ingest([("Look.", "*Mira hands you a small silver locket.*")] + mb.fill(20, random.Random(2)))
        self.assertIn("locket", mb.retrieve(st, hist, "where is the lockett you gave me?")["block"])

    def test_a_pluggable_embedder_joins_the_score_and_a_broken_one_is_ignored(self):
        st, hist = ingest([("Look.", "*Mira hands you a small silver locket.*")] + mb.fill(5, random.Random(2)))
        calls = []
        semantic.set_embedder(lambda texts: calls.append(texts) or [[1.0, 0.0] for _ in texts])
        try:
            r = mb.retrieve(st, hist, "tell me about the quartz amulet")
            self.assertTrue(calls)
            self.assertIn("embedding", " ".join(t["why"] for t in r["trace"]))
            semantic.set_embedder(lambda texts: 1 / 0)
            self.assertIsInstance(mb.retrieve(st, hist, "tell me about the quartz amulet"), dict)
        finally:
            semantic.set_embedder(None)

    def test_long_conversation(self):
        r = mb.long_chat(turns=500, planted=14)
        self.assertGreaterEqual(r["direct"], .93, r)
        self.assertGreaterEqual(r["indirect"], .85, r)
        self.assertLess(r["ingest_ms_p95"], 100, r)
        self.assertLess(r["state_kb"], 200, r)

    def test_returning_character_and_topic_change(self):
        pairs = [("Meet Captain Reyes, he commands the harbor guard.", "Pleased to meet him.")] + mb.fill(60, random.Random(8)) + [("Let's talk about cooking now.", "Sure.")] + mb.fill(30, random.Random(9))
        pairs += [("Captain Reyes is back in town.", "Oh?")]
        st, hist = ingest(pairs)
        r = mb.retrieve(st, hist, "What do you know about Captain Reyes?")
        self.assertIn("harbor guard", r["block"])

    def test_nothing_on_record_is_flagged_and_the_prompt_says_so(self):
        g = mb.gaps()
        self.assertGreaterEqual(g["unknown_flagged"], .85, g)
        self.assertLessEqual(g["false_gap_on_known"], .15, g)
        st, hist = ingest([(c[1], c[2]) for c in mb.CASES] + mb.fill(10, random.Random(3)))
        r = mb.retrieve(st, hist, "Do you remember my sister's wedding?")
        self.assertTrue(r["gap"])
        self.assertIn("does not remember", r["block"])

    def test_held_out_unknown_questions(self):
        st, hist = ingest([(c[1], c[2]) for c in HELDOUT2] + mb.fill(20, random.Random(5)))
        flagged = sum(bool(mb.retrieve(st, hist, q)["gap"]) for q in HELDOUT2_UNKNOWN)
        self.assertGreaterEqual(flagged / len(HELDOUT2_UNKNOWN), .8)

    def test_outdated_hypothetical_and_hearsay_are_labelled_never_stated_as_fact(self):
        st, hist = ingest([("I live in Lisbon.", "Nice."), ("Garrick said he saw you with the baron last night.", "Hm.")] + mb.fill(5, random.Random(1)) + [("I live in Porto now.", "Oh.")])
        r = mb.retrieve(st, hist, "Remember what Garrick said about the baron? And where did I used to live before?")
        for line in r["block"].split("\n"):
            if "Garrick said" in line:
                self.assertIn("unverified", line)
            if "Lisbon" in line:
                self.assertIn("outdated", line)

    def test_token_budget_scales_down_without_dropping_the_most_relevant_memory(self):
        st, hist = ingest([(c[1], c[2]) for c in mb.CASES])
        h_ = hist + [{"role": "user", "content": "do you remember the locket and the pier and Nadia and Biscuit and the novel?"}]
        full = recall.select(st, h_, user=U, char=C, cfg=recall.settings(ON), turn=len(h_))
        small = recall.select(st, h_, user=U, char=C, cfg=recall.settings(ON), turn=len(h_), scale=.4)
        self.assertLess(len(small["block"]), len(full["block"]))
        self.assertLessEqual(len(small["trace"]), len(full["trace"]))
        self.assertEqual(small["trace"][0]["id"], full["trace"][0]["id"])
        self.assertLessEqual(len(full["block"]), 2400)


# ------------------------------------------------------------------ 5. injection into the model's prompt
class InjectionTests(unittest.TestCase):
    def body(self, hist, state=None, vkey=None):
        b = {"char": h.BOLD, "user": U, "history": hist, "state": state or {}, "chat_id": "c1",
             "params": {"mode": "story", "think": False, "max_tokens": 100, "mem": ON}}
        if vkey:
            b["_vault"] = vkey
        return b

    def test_retrieved_memory_reaches_the_model_without_any_page_state(self):
        """The page sent NO memory at all: the server read the chat itself and still put the gift into the prompt."""
        fake = h.install(h.FakeLLM(["It's the locket you gave me."]))
        hist = [{"role": "user", "content": "It's my birthday."}, {"role": "assistant", "name": "Rex", "content": "*Rex hands you a small silver locket with a tiny moon on it.*"}]
        hist += [{"role": "user", "content": f"filler talk {i} about buses"} if k == 0 else {"role": "assistant", "name": "Rex", "content": "Mm."} for i in range(25) for k in (0, 1)]
        hist.append({"role": "user", "content": "Who gave me this pendant?"})
        r = generate_reply(self.body(hist), None)
        sent = fake.calls[0][-1]["content"]
        self.assertIn("silver locket", sent)
        self.assertIn("Rex handed Tonoy", sent)
        self.assertNotIn("{{", sent)
        self.assertEqual(sorted(r["mem_report"]["injected"]), sorted(r["recalled"]))
        self.assertTrue(r["recalled"])
        self.assertIsInstance(r["mem"], dict)

    def test_the_message_just_sent_is_already_findable(self):
        fake = h.install(h.FakeLLM(["Noted."]))
        r = generate_reply(self.body([{"role": "user", "content": "Remember this: my safe code is hidden inside the red teapot."}]), None)
        self.assertTrue(any("teapot" in i["text"] for i in r["mem"]["items"]))

    def test_unknown_questions_tell_the_model_not_to_invent(self):
        fake = h.install(h.FakeLLM(["I don't remember."]))
        hist = [{"role": "user", "content": "My dog is called Biscuit."}, {"role": "assistant", "name": "Rex", "content": "Nice."}, {"role": "user", "content": "Do you remember my grandfather's farm?"}]
        r = generate_reply(self.body(hist), None)
        self.assertTrue(r["mem_report"]["gap"])
        self.assertIn("does not remember", fake.calls[0][-1]["content"])

    def test_memory_off_injects_nothing(self):
        fake = h.install(h.FakeLLM(["Fine."]))
        b = self.body([{"role": "user", "content": "I'm allergic to shellfish."}])
        b["params"]["mem"] = {"on": False}
        r = generate_reply(b, None)
        self.assertNotIn("What Rex remembers", h.ptxt(fake.calls[0]))
        self.assertNotIn("mem", r)

    def test_a_memory_failure_never_stops_the_reply(self):
        h.install(h.FakeLLM(["Still here."]))
        orig = recall.ingest
        recall.ingest = lambda *a, **k: 1 / 0
        try:
            r = generate_reply(self.body([{"role": "user", "content": "hello there friend"}]), None)
        finally:
            recall.ingest = orig
        self.assertIn("error", r["mem_report"])
        self.assertTrue(r["text"])


# ------------------------------------------------------------------ 6. persistence, restarts, corruption
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.k = vault.key("host", f"chat{time.time_ns()}", "mira")

    def mem(self):
        st, hist = ingest([("It's my birthday.", "*Mira hands you a small silver locket with a tiny moon on it.*"), ("My dog is called Biscuit.", "Cute.")])
        return st["mem"], hist

    def test_a_blank_page_cannot_wipe_the_memory(self):
        m, hist = self.mem()
        vault.save(self.k, mem=m)
        blank = {}
        info = vault.restore_into(self.k, blank, turns=len(hist))
        self.assertGreater(info["items"], 0)
        self.assertEqual({i["id"] for i in blank["mem"]["items"]}, {i["id"] for i in m["items"]})
        stale = {"mem": store.blank()}
        vault.restore_into(self.k, stale)
        self.assertTrue(stale["mem"]["items"])

    def test_survives_a_real_process_restart(self):
        m, hist = self.mem()
        vault.save(self.k, mem=m)
        prog = (
            "import sys, json\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from crumble import vault, recall\n"
            f"st = {{}}\nvault.restore_into({self.k!r}, st)\n"
            f"hist = {json.dumps(hist)} + [{{'role':'user','content':'Who gave me this pendant?'}}]\n"
            f"r = recall.select(st, hist, user={U!r}, char={C!r}, cfg=recall.settings({ON!r}), turn=40)\n"
            "print(json.dumps(r['block']))\n")
        out = subprocess.run([sys.executable, "-c", prog], cwd=ROOT, env=dict(os.environ), capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("silver locket", json.loads(out.stdout.strip().splitlines()[-1]))

    def test_generate_reply_restores_from_the_vault_when_the_page_has_nothing(self):
        m, hist = self.mem()
        vault.save(self.k, mem=m)
        fake = h.install(h.FakeLLM(["Yes."]))
        hh = hist + [{"role": "user", "content": "Who gave me this pendant?"}]
        b = {"char": dict(h.BOLD, name=C), "user": U, "history": hh, "state": {}, "chat_id": "x", "_vault": self.k, "params": {"mode": "story", "think": False, "max_tokens": 50, "mem": ON}}
        r = generate_reply(b, None)
        self.assertIn("silver locket", fake.calls[0][-1]["content"])
        self.assertGreater(r["mem_report"]["restored"]["items"], 0)

    def test_corrupt_primary_falls_back_to_a_verified_backup_and_the_bad_file_is_kept(self):
        m, _ = self.mem()
        vault.save(self.k, mem=m)
        p = vault._p(self.k)
        os.utime(p.with_name(p.name), None)
        time.sleep(0)
        for i in range(1, 3):      # force backups to exist
            b1 = p.with_name(p.name + ".bak1")
            if not b1.exists():
                b1.write_text(p.read_text())
        p.write_text(p.read_text()[:-40])                       # a torn write
        got = vault.load(self.k)
        self.assertIsNotNone(got)
        self.assertTrue(got["mem"]["items"])
        self.assertTrue(list(p.parent.glob(p.name + ".corrupt-*")), "a damaged file is set aside, never destroyed")

    def test_a_flipped_byte_is_caught_by_the_checksum(self):
        m, _ = self.mem()
        vault.save(self.k, mem=m)
        p = vault._p(self.k)
        env = json.loads(p.read_text())
        env["data"]["mem"]["items"][0]["text"] = "TAMPERED"
        p.write_text(json.dumps(env))
        self.assertIsNone(vault._read(p)[0])

    def test_a_crash_in_the_middle_of_a_write_leaves_the_old_file_intact(self):
        m, _ = self.mem()
        vault.save(self.k, mem=m)
        before = vault._p(self.k).read_text()
        real = os.replace
        os.replace = lambda *a, **k: (_ for _ in ()).throw(OSError("power cut"))
        try:
            with self.assertRaises(OSError):
                vault.save(self.k, mem=dict(m, rev=m["rev"] + 5))
        finally:
            os.replace = real
        self.assertEqual(vault._p(self.k).read_text(), before)
        self.assertTrue(vault.load(self.k)["mem"]["items"])

    def test_deliberate_deletion_stays_deleted_but_is_recoverable(self):
        m, _ = self.mem()
        vault.save(self.k, mem=m)
        victim = m["items"][0]["id"]
        page = json.loads(json.dumps(m))
        store.remove(page, [victim])
        vault.save(self.k, mem=page)
        state = {"mem": json.loads(json.dumps(m))}          # a stale tab that still has it
        vault.restore_into(self.k, state)
        self.assertNotIn(victim, [i["id"] for i in state["mem"]["items"]])
        self.assertIn(victim, [a["id"] for a in page["archive"]], "deleted memories are archived")

    def test_two_copies_merge_item_by_item(self):
        a = store.ensure({}, U, C)
        store.add(a, "semantic", "{{user}} likes tea", subj="user", imp=.5)
        b = json.loads(json.dumps(a))
        store.add(a, "semantic", "{{user}} has a cat named Pip", subj="user", imp=.6)
        store.add(b, "semantic", "{{user}} lives in Porto", subj="user", imp=.6)
        merged = vault.merge_mem(a, b)
        texts = " | ".join(i["text"] for i in merged["items"])
        for want in ("tea", "Pip", "Porto"):
            self.assertIn(want, texts)
        self.assertEqual(len({i["id"] for i in merged["items"]}), len(merged["items"]), "colliding ids are renumbered, not overwritten")

    def test_rewound_chat_does_not_resurrect_memories_from_messages_that_no_longer_exist(self):
        m, hist = self.mem()
        vault.save(self.k, mem=m)
        state = {}
        vault.restore_into(self.k, state, turns=0)
        self.assertEqual(state["mem"]["items"], [])

    def test_deleting_a_chat_moves_its_memory_to_trash(self):
        m, _ = self.mem()
        chat = f"gone{time.time_ns()}"
        k = vault.key("host", chat, "mira")
        vault.save(k, mem=m)
        self.assertGreaterEqual(vault.retire("host", chat), 1)
        self.assertIsNone(vault.load(k))
        self.assertTrue(list(vault.TRASH.glob(f"*{k}*")))

    def test_backups_can_be_listed_and_restored(self):
        m, _ = self.mem()
        vault.save(self.k, mem=m)
        p = vault._p(self.k)
        p.with_name(p.name + ".bak1").write_text(p.read_text())
        self.assertTrue(vault.backups(self.k))
        self.assertTrue(vault.restore_backup(self.k, 1))

    def test_protect_state_keeps_group_members_apart(self):
        chat = f"grp{time.time_ns()}"
        m, _ = self.mem()
        state = {"members": {"rex": {"mem": m}, "mira": {}}}
        vault.protect_state("host", chat, "group1", state, turns=10)
        self.assertTrue(vault.load(vault.key("host", chat, "rex"))["mem"]["items"])
        self.assertIsNone(vault.load(vault.key("host", chat, "mira")))

    def test_chat_files_are_written_atomically_and_a_damaged_one_recovers_from_backup(self):
        d = Path(tempfile.mkdtemp()) / "chats" / "c"
        d.mkdir(parents=True)
        f = d / "one.json"
        storage.wj(f, {"history": [1, 2, 3]})
        os.utime(f, (time.time() - 100, time.time() - 100))
        storage.wj(f, {"history": [1, 2, 3, 4]})
        (d / "one.json.bak1").write_text(json.dumps({"history": [1, 2, 3]}))
        f.write_text('{"history": [1, 2')                    # torn
        self.assertEqual(storage.rj(f, None), {"history": [1, 2, 3]})
        self.assertTrue(list(d.glob("one.json.corrupt-*")))
        self.assertFalse(list(d.glob("*.tmp*")))


# ------------------------------------------------------------------ 7. consolidation & capacity
class ConsolidationTests(unittest.TestCase):
    def test_old_minor_episodes_fold_into_a_digest_and_originals_are_archived(self):
        m = store.ensure({}, U, C)
        for k in range(50):     # appended directly: these are distinct moments, not near-duplicates for add() to merge
            m["seq"] += 1
            m["items"].append({"id": f"e{m['seq']}", "t": "episodic", "text": f"{{{{char}}}} noticed minor thing {k}", "imp": .3, "ts": 0, "turn": k, "n": 0, "last": 0, "pin": False,
                               "src": "rule", "kind": "event", "who": "{{char}}", "ver": 1})
        store.add(m, "episodic", "{{char}} promised to return the book", imp=.8, turn=3, src="rule", kind="promise", who="{{char}}", open=True)
        n_before = len(m["items"])
        made = ops.consolidate(m, turn=400)
        self.assertGreater(made, 0)
        self.assertLess(len(m["items"]), n_before)
        self.assertTrue(any(i.get("kind") == "digest" for i in m["items"]))
        self.assertTrue(any(i.get("open") for i in m["items"]), "open promises are never folded away")
        self.assertGreaterEqual(len(m["archive"]), 4, "the originals are archived, not destroyed")

    def test_aged_out_memories_are_archived_not_destroyed(self):
        m = store.ensure({}, U, C)
        store.add(m, "episodic", "{{user}} sneezed once near the door", imp=.2, turn=1)
        store.add(m, "episodic", "{{char}} swore an oath to guard the gate", imp=.9, turn=1, kind="promise", open=True)
        store.decay(m, 500)
        self.assertEqual([i["text"] for i in m["items"]], ["{{char}} swore an oath to guard the gate"])
        self.assertEqual(m["archive"][0]["why"], "aged out")


if __name__ == "__main__":
    unittest.main()
