"""The history keeper: older history is folded, but events, relationships and exact details survive."""
import json
import unittest

from tests import helpers as h
from crumble import keeper
from crumble.llm import generate_reply
from crumble.memory import keep_update
from crumble.prompt import build_messages

MSGS = [{"role": "user", "content": "My sister Nadia is coming on Friday. I promise I will never tell anyone your secret."},
        {"role": "assistant", "content": "*Mira nods.* I told you the truth about the necklace, nobody knows it was my mother's gift."},
        {"role": "user", "content": "She gave me a sword and I lost it in the Ashen Keep."}]
SUM = "SETTING & STATE\nLocation: Cafe\nCurrent State: They talk about Nadia and the sword.\nRELATIONSHIP DYNAMIC\nPrimary Dynamic: warming up slowly"


class Fold(unittest.TestCase):
    def test_summary_being_replaced_becomes_a_chapter(self):
        k = keeper.fold(None, SUM, MSGS, "Sam", "Mira", 0, 3)
        self.assertEqual(len(k["chapters"]), 1)
        self.assertIn("Nadia", k["chapters"][0]["t"])
        self.assertNotIn("SETTING", k["chapters"][0]["t"])      # prose, not the form

    def test_promises_secrets_and_gifts_are_key_events(self):
        k = keeper.fold(None, "", MSGS, "Sam", "Mira", 0, 3)
        kinds = {e["k"] for e in k["events"]}
        self.assertTrue({"secret", "object"} <= kinds)
        self.assertTrue(any("promise" in e["t"] for e in k["events"]))
        self.assertTrue(all(e["t"].startswith("{{") for e in k["events"]))   # placeholders survive a rename

    def test_relationships_are_recorded_once_and_counted(self):
        k = keeper.fold(None, "", MSGS, "Sam", "Mira", 0, 3)
        k = keeper.fold(k, "", [{"role": "user", "content": "Nadia says hi."}] + MSGS[:1], "Sam", "Mira", 3, 5)
        self.assertEqual(list(k["bonds"]), ["nadia"])
        self.assertEqual(k["bonds"]["nadia"]["rel"], "sister")
        self.assertGreaterEqual(k["bonds"]["nadia"]["n"], 2)

    def test_the_users_own_name_is_not_a_relationship(self):
        k = keeper.fold(None, "", [{"role": "user", "content": "My friend Sam is here."}], "Sam", "Mira", 0, 1)
        self.assertEqual(k["bonds"], {})

    def test_change_of_stage_becomes_a_key_event(self):
        k = keeper.fold(None, "", [], "Sam", "Mira", 0, 1, affection=20)
        k = keeper.fold(k, "", [], "Sam", "Mira", 1, 2, affection=90)
        self.assertEqual(len(k["main"]["log"]), 1)
        self.assertTrue(any(e["k"] == "bond" for e in k["events"]))
        k2 = keeper.fold(k, "", [], "Sam", "Mira", 2, 3, affection=91)       # same stage: nothing new
        self.assertEqual(len(k2["main"]["log"]), 1)

    def test_nothing_is_duplicated_when_the_same_stretch_is_folded_twice(self):
        k = keeper.fold(None, SUM, MSGS, "Sam", "Mira", 0, 3)
        n = len(k["events"])
        k = keeper.fold(k, SUM, MSGS, "Sam", "Mira", 3, 6)
        self.assertEqual(len(k["events"]), n)
        self.assertEqual(len(k["chapters"]), 1)

    def test_rewinding_drops_what_came_from_messages_that_no_longer_exist(self):
        k = keeper.fold(None, "", MSGS, "Sam", "Mira", 0, 3)
        self.assertTrue(any("Ashen" in e["t"] for e in k["events"]))
        k = keeper.fold(k, "", [{"role": "user", "content": "I swear I will bring the map tomorrow."}], "Sam", "Mira", 1, 2)   # the chat was rewound to turn 1
        txt = " ".join(e["t"] for e in k["events"])
        self.assertNotIn("Ashen", txt)          # turn 2 no longer exists
        self.assertNotIn("necklace", txt)       # nor turn 1 as it was
        self.assertIn("map", txt)
        self.assertIn("Nadia", txt)             # turn 0 is untouched
        self.assertEqual(k["covered"], 2)

    def test_a_lie_is_never_recorded_as_a_fact(self):
        lie = [{"role": "assistant", "content": "I swear I have never seen that necklace in my life.", "dyn": {"quirk": "lie"}}]
        k = keeper.fold(None, "", lie, "Sam", "Mira", 0, 1)
        self.assertEqual(k["events"], [])

    def test_damaged_input_never_breaks(self):
        for bad in (None, "x", 5, {"chapters": "no", "events": [1, None], "bonds": {"a": 3}, "main": 4}):
            k = keeper.ensure(bad)
            self.assertEqual(set(keeper.blank()) - set(k), set())
        self.assertEqual(keeper.render({"events": "?"}, "hi", 5, 300, "Sam", "Mira"), "")


class Compaction(unittest.TestCase):
    def chain(self, n):
        k = None
        for i in range(n):
            s = f"Current State: Chapter {i} happened and Mira met Person{i} at the old harbour number {i}. " + ("Mira promised to return the ring. " if i == 1 else "")
            k = keeper.fold(k, s, [], "Sam", "Mira", i * 10, i * 10 + 10)
        return k

    def test_old_chapters_merge_but_stay_bounded(self):
        k = self.chain(12)
        self.assertLessEqual(len(k["chapters"]), keeper.CHAPTERS)
        self.assertLessEqual(len(k["long"]), keeper.LONG_CAP + 5)
        self.assertTrue(k["long"])

    def test_a_promise_survives_every_merge(self):
        k = self.chain(14)
        everything = k["long"] + " " + " ".join(c["t"] for c in k["chapters"])
        self.assertIn("promised to return the ring", everything)

    def test_merge_adds_no_new_words(self):
        a = "Mira met Jonas at the harbour. Jonas gave her a brass key."
        b = "Mira opened the old chest. She promised never to tell."
        m = keeper._merge_text(a, b, cap=90)
        src = set((a + " " + b).lower().replace(".", "").split())
        self.assertTrue(set(m.lower().replace(".", "").split()) <= src)
        self.assertLessEqual(len(m), 95)


class Render(unittest.TestCase):
    def kept(self):
        k = keeper.fold(None, SUM, MSGS, "Sam", "Mira", 0, 3, affection=20)
        return keeper.fold(k, "", [{"role": "user", "content": "Nadia is my sister, remember?"}], "Sam", "Mira", 3, 4, affection=90)

    def test_block_has_no_labels_ids_or_placeholders(self):
        b = keeper.render(self.kept(), "tell me about Nadia", 10, 400, "Sam", "Mira")
        self.assertIn("Nadia", b)
        for bad in ("{{", "}}", "k1", "k2", "'t'"):
            self.assertNotIn(bad, b)

    def test_budget_is_respected(self):
        k = self.kept()
        for tokens in (60, 120, 400):
            b = keeper.render(k, "Nadia", 10, tokens, "Sam", "Mira")
            self.assertLessEqual(len(b) // 3 + 3, tokens + 15, tokens)
        self.assertEqual(keeper.render(k, "Nadia", 10, 20, "Sam", "Mira"), "")

    def test_relevant_event_wins_when_room_is_tight(self):
        k = keeper.blank()
        keeper.add_events(k, [{"t": f"{{{{user}}}}: I promise to bring item number {i} to the camp tomorrow", "k": "promise", "w": 4, "turn": i} for i in range(30)]
                          + [{"t": "{{user}}: my brother Dario owns the lighthouse at Dunmore", "k": "relation", "w": 3, "turn": 2}])
        b = keeper.render(k, "who owns the lighthouse", 40, 110, "Sam", "Mira")
        self.assertIn("lighthouse", b)


class PastChats(unittest.TestCase):
    def chat(self):
        return {"title": "Harbour night", "updated": 5.0, "history": [],
                "state": {"summary": SUM, "keep": keeper.fold(None, "", MSGS, "Sam", "Mira", 0, 3, affection=85)}}

    def test_digest_carries_summary_and_key_moments(self):
        d = keeper.digest(self.chat(), "Sam", "Mira")
        self.assertIn("Nadia", d["text"])
        self.assertIn("Key moments", d["text"])
        self.assertNotIn("{{", d["text"])

    def test_empty_chats_give_nothing(self):
        self.assertIsNone(keeper.digest({"state": {}, "history": [{"role": "user", "content": "hi"}]}, "Sam", "Mira"))
        self.assertIsNone(keeper.digest(None, "Sam", "Mira"))
        self.assertEqual(keeper.past_block([], "Sam", "Mira"), "")

    def test_newest_first_and_bounded(self):
        ds = [{"title": str(i), "updated": float(i), "text": "x" * 300 + f" chat{i}"} for i in range(6)]
        b = keeper.past_block(ds, "Sam", "Mira", 260)
        self.assertLess(b.find("chat5"), b.find("chat4") if "chat4" in b else 10 ** 9)
        self.assertLessEqual(len(b) // 3 + 3, 275)


class InThePrompt(unittest.TestCase):
    def test_keeper_and_past_blocks_reach_the_model_in_the_private_background(self):
        k = keeper.fold(None, SUM, MSGS, "Sam", "Mira", 0, 3)
        d = keeper.digest({"title": "t", "updated": 1.0, "state": {"summary": SUM}}, "Sam", "Mira")
        o = {"mode": "story", "state": {}, "words": (10, 30), "tier": 1, "keep_block": keeper.render(k, "Nadia", 5, 300, "Sam", "Mira"),
             "past_block": keeper.past_block([d], "Sam", "Mira")}
        txt = h.ptxt(build_messages(h.SHY, "Sam", [{"role": "user", "content": "hi"}], o))
        self.assertIn("Older history", txt)
        self.assertIn("Earlier conversations between", txt)
        self.assertLess(txt.index("=== PRIVATE BACKGROUND"), txt.index("Older history"))
        self.assertLess(txt.index("Older history"), txt.index("=== END OF PRIVATE BACKGROUND"))

    def test_generate_reply_carries_the_keeper_from_state(self):
        k = keeper.fold(None, SUM, MSGS, "Sam", "Mira", 0, 3)
        fake = h.install(h.FakeLLM(["Hm. Sure."]))
        generate_reply({"char": h.SHY, "user": "Sam", "history": [{"role": "user", "content": "How is Nadia doing these days?"}], "state": {"keep": k},
                        "params": {"mode": "story", "think": False, "max_tokens": 120}}, None)
        self.assertIn("Nadia is Sam's sister", h.ptxt(fake.calls[0]))

    def test_past_chats_reach_generate_reply(self):
        fake = h.install(h.FakeLLM(["Hm. Sure."]))
        past = [keeper.digest({"title": "t", "updated": 1.0, "state": {"summary": SUM}}, "Sam", "Mira")]
        generate_reply({"char": h.SHY, "user": "Sam", "history": [{"role": "user", "content": "hello again"}], "state": {}, "past": past,
                        "params": {"mode": "story", "think": False, "max_tokens": 120}}, None)
        self.assertIn("Earlier conversations between", h.ptxt(fake.calls[0]))


class Endpoints(unittest.TestCase):
    def test_summarize_returns_the_keeper_and_the_page_can_send_it_back(self):
        h.install(h.FakeLLM())
        srv = h.serve()
        body = {"char": h.SHY, "user": "Sam", "history": MSGS, "summary": SUM, "turn0": 0, "aff": 30}
        code, r = h.call(srv, "POST", "/api/summarize", body)
        self.assertEqual(code, 200)
        self.assertIn("keep", r)
        self.assertTrue(r["keep"]["events"])
        json.dumps(r["keep"])
        body.update(keep=r["keep"], turn0=3, history=[{"role": "user", "content": "I swear I will come back with the map."}], aff=90)
        code, r2 = h.call(srv, "POST", "/api/summarize", body)
        self.assertTrue(any("map" in e["t"] for e in r2["keep"]["events"]))
        self.assertTrue(any("Ashen" in e["t"] for e in r2["keep"]["events"]))      # the earlier ones are still there
        srv.shutdown()


class LongChat(unittest.TestCase):
    def test_a_very_long_chat_stays_bounded_and_keeps_the_early_promise(self):
        k, summary = None, ""
        msgs = [{"role": "user", "content": "I swear on my life I will bring back your brother's ring, Mira. It is a promise."}]
        for i in range(1, 700):
            who = "user" if i % 2 else "assistant"
            msgs.append({"role": who, "content": f"Message {i}: we walked past stall {i} and talked about the weather and {['bread', 'rain', 'the road', 'tea'][i % 4]}. "
                                                f"{'My cousin Teo gave me a copper coin number ' + str(i) + '.' if i % 37 == 0 else ''}"})
        for a in range(0, len(msgs), 14):
            chunk = msgs[a:a + 14]
            k = keeper.fold(k, summary, chunk, "Sam", "Mira", a, a + len(chunk), affection=40 + (a // 14) % 50)
            summary = f"Current State: so far we reached message {a + len(chunk)} and walked a lot. " + " ".join(m["content"][:40] for m in chunk[:3])
        self.assertLessEqual(len(k["events"]), keeper.EVENTS_CAP)
        self.assertLessEqual(len(k["chapters"]), keeper.CHAPTERS)
        self.assertLessEqual(len(k["bonds"]), keeper.BONDS_CAP)
        self.assertLess(len(json.dumps(k)), 40000)
        b = keeper.render(k, "did you bring the ring back like you promised", 700, 420, "Sam", "Mira")
        self.assertIn("ring", b)
        self.assertLessEqual(len(b) // 3 + 3, 435)
        self.assertEqual(k["bonds"]["teo"]["rel"], "cousin")


class PastChatsOverHttp(unittest.TestCase):
    """The server reads the other chats of the same character itself: the page only says which chat this is."""

    def test_earlier_chats_reach_the_prompt_but_not_the_current_one_or_a_fresh_start(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from crumble import server
        from crumble.storage import wj
        k = keeper.fold(None, "", MSGS, "Sam", "Mira", 0, 3, affection=85)
        with tempfile.TemporaryDirectory() as tmp:
            chats = Path(tmp)
            (chats / "shy").mkdir()
            wj(chats / "shy" / "old1.json", {"id": "old1", "title": "Harbour", "updated": 5, "history": [], "state": {"summary": SUM, "keep": k}})
            wj(chats / "shy" / "fresh.json", {"id": "fresh", "title": "Alt", "updated": 6, "history": [], "cfg": {"fresh": True},
                                              "state": {"summary": "Current State: an alternate universe where Mira is a pirate captain"}})
            wj(chats / "shy" / "now.json", {"id": "now", "title": "Now", "updated": 7, "history": [], "state": {"summary": "Current State: THIS CHAT ITSELF"}})
            wj(chats / "shy" / "bare.json", {"id": "bare", "title": "Bare", "updated": 8, "history": [{"role": "user", "content": "hi"}], "state": {}})
            fake = h.install(h.FakeLLM(["Hm. Sure."]))
            with mock.patch.object(server, "CHATS", chats):
                srv = h.serve()
                body = {"char": dict(h.SHY), "user": "Sam", "chat_id": "now", "history": [{"role": "user", "content": "hello again"}], "state": {}, "turn": 1,
                        "params": {"mode": "story", "think": False, "max_tokens": 120, "past": True}}
                with mock.patch.object(server, "get_char", lambda cid: dict(h.SHY)):
                    import json
                    from http.client import HTTPConnection
                    c = HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
                    c.request("POST", "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
                    out = c.getresponse().read().decode()
                    self.assertIn('"done"', out)
                    txt = h.ptxt(fake.calls[0])
                    self.assertIn("Earlier conversations between", txt)
                    self.assertIn("Nadia", txt)
                    self.assertNotIn("pirate captain", txt)       # marked as a fresh start
                    self.assertNotIn("THIS CHAT ITSELF", txt)     # the chat itself is never its own past
                    body["params"]["past"] = False
                    c = HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10)
                    c.request("POST", "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
                    c.getresponse().read()
                    self.assertNotIn("Earlier conversations between", h.ptxt(fake.calls[-1]))
                srv.shutdown()


if __name__ == "__main__":
    unittest.main()
