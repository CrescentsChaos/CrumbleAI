import json
import unittest

from tests import helpers as h
from crumble import recall
from crumble.llm import generate_reply
from crumble.memory import memorize, track
from crumble.prompt import build_messages
from crumble.recall import analyze, learn, lexicon as lx, retrieve, store

ON = {"on": True, "depth": "standard", "learn": True}
CFG = recall.settings(ON)


def word(k):
    """A unique letters-only made-up word, stable under stemming (digits are ignored by the matcher, so they cannot tell texts apart)."""
    return "zq" + "".join("bcfghjklmn"[int(d)] for d in str(k))


def mem_with(*specs, turn=60, user="Sam", char="Mira"):
    """A state whose memory holds the given (type, text, kwargs) memories."""
    st = {"facts": [], "mood": "neutral"}
    m = store.ensure(st, user, char)
    m["turn"] = turn
    for t, text, kw in specs:
        store.add(m, t, text, **kw)
    return st


def pick(st, text, turn=61, cfg=CFG, mood=None, hist=None):
    if mood:
        st["mood"] = mood
    return retrieve.select(st, hist or [{"role": "user", "content": text}], user="Sam", char="Mira", cfg=cfg, turn=turn)


def texts(r):
    return [t["text"] for t in r["trace"]]


class MemLLM(h.FakeLLM):
    """FakeLLM that answers the memory-consolidation ask with its own JSON and everything else as usual."""

    def __init__(self, mem=None, **kw):
        super().__init__(**kw)
        self.mem, self.mem_calls = mem, 0

    def create_chat_completion(self, messages, stream=False, **kw):
        if not stream and "long-term memory of a roleplay character" in messages[-1]["content"]:
            self.calls.append(messages)
            self.mem_calls += 1
            return {"choices": [{"message": {"content": json.dumps(self.mem) if self.mem is not None else "I cannot do that."}, "finish_reason": "stop"}]}
        return super().create_chat_completion(messages, stream, **kw)


class LexiconTests(unittest.TestCase):
    def test_stemmer_agrees_across_inflections(self):
        for a, b in (("kissed", "kisses"), ("hugging", "hugged"), ("gifts", "gift"), ("promised", "promise"), ("necklaces", "necklace"),
                     ("interrupted", "interrupting"), ("parties", "party"), ("brothers", "brother")):
            self.assertEqual(lx.stem(a), lx.stem(b), (a, b))

    def test_event_categories_bridge_wording(self):
        self.assertIn("gift", lx.categories("Sam gave her a necklace"))
        self.assertIn("gift", lx.categories("what present did you bring"))
        self.assertIn("birthday", lx.categories("on her birthday"))
        self.assertEqual(lx.categories("nice weather today"), [])


class StoreTests(unittest.TestCase):
    def test_placeholders_survive_a_rename(self):
        t = store.placeholders("Sam gave Mira Rose a necklace. Samantha smiled.", "Sam", "Mira Rose")
        self.assertEqual(t, "{{user}} gave {{char}} a necklace. Samantha smiled.")
        self.assertEqual(store.resolve(t, "Alex", "Mira Rose"), "Alex gave Mira Rose a necklace. Samantha smiled.")

    def test_near_duplicates_merge_and_reinforce(self):
        m = store.ensure({}, "Sam", "Mira")
        a, made = store.add(m, "semantic", "{{user}} likes hiking in the mountains.", imp=.5)
        b, made2 = store.add(m, "semantic", "{{user}} likes hiking in the mountains a lot", imp=.5)
        self.assertTrue(made)
        self.assertFalse(made2)
        self.assertEqual(len(m["items"]), 1)
        self.assertGreater(b["imp"], .5)

    def test_newer_opposite_statement_replaces_the_old(self):
        m = store.ensure({}, "Sam", "Mira")
        store.add(m, "semantic", "{{user}} likes coffee", imp=.5)
        store.add(m, "semantic", "{{user}} hates coffee", imp=.6)
        self.assertEqual([i["text"] for i in m["items"]], ["{{user}} hates coffee"])

    def test_old_flat_facts_are_migrated_once(self):
        st = {"facts": ["Sam likes tea", "Sam has a dog named Rex"]}
        m = store.ensure(st, "Sam", "Mira")
        self.assertEqual([i["text"] for i in m["items"]], ["{{user}} likes tea", "{{user}} has a dog named Rex"])
        store.ensure(st, "Sam", "Mira")
        self.assertEqual(len(m["items"]), 2)

    def test_caps_drop_the_weakest_and_keep_pins(self):
        m = store.ensure({}, "Sam", "Mira")
        m["turn"] = 500
        store.add(m, "episodic", "{{user}} planted a tree long ago", imp=.1, turn=0, pin=True)
        for k in range(store.CAPS["episodic"] + 15):
            store.add(m, "episodic", f"Event with {word(k)} and {word(k + 1000)} nearby", imp=.3 + (k % 5) / 10, turn=k)
        store.compact(m, 500)
        eps = [i for i in m["items"] if i["t"] == "episodic"]
        self.assertEqual(len(eps), store.CAPS["episodic"])
        self.assertTrue(any(i["pin"] for i in eps))

    def test_bad_hand_edited_data_never_breaks(self):
        st = {"mem": {"items": [{"t": "episodic", "text": "x" * 10, "imp": "high", "turn": None}, {"t": "bogus", "text": "no"}, "junk"]}}
        m = store.ensure(st)
        self.assertEqual(len(m["items"]), 1)
        self.assertEqual(m["items"][0]["imp"], .5)
        retrieve.select(st, [{"role": "user", "content": "hello there"}], user="Sam", char="Mira", cfg=CFG)

    def test_recent_buffer_overflows_oldest_first(self):
        m = store.ensure({}, "Sam", "Mira")
        out = []
        for k in range(store.RECENT_MAX + 2):
            out += store.push_recent(m, f"Something about {word(k)} happened here", .5, k)
        self.assertEqual(len(m["recent"]), store.RECENT_MAX)
        self.assertEqual(len(out), 2)
        self.assertIn(word(0), out[0]["text"])


class AnalyzeTests(unittest.TestCase):
    def test_stated_facts(self):
        f = {t for t, _, _ in analyze.user_facts("I hate being interrupted. Call me Sammy. I work at St Mary's and I live in Leeds.")}
        self.assertIn("{{user}} dislikes being interrupted", f)
        self.assertIn("{{user}} wants to be called Sammy", f)
        self.assertIn("{{user}} works at St Mary's", f)
        self.assertIn("{{user}} lives in Leeds", f)

    def test_no_false_facts_from_chatter(self):
        for t in ("I love you so much", "I'm 5 minutes away", "I'm a bit tired", "Do I like it? I hate it when people lie?", "I'm so happy today"):
            self.assertEqual(analyze.user_facts(t), [], t)

    def test_boundaries_are_third_person_and_important(self):
        (text, imp, subj), = analyze.user_facts("Please don't interrupt me while I explain.")
        self.assertEqual(text, "{{user}} asked {{char}} not to interrupt {{user}}")
        self.assertGreaterEqual(imp, .85)

    def test_people_from_mentions_names_and_known(self):
        self.assertEqual(analyze.people_in("Marcus came, then I saw Elena. Bob left", known=["Bob"]), ["Marcus", "Elena", "Bob"])
        self.assertEqual(analyze.people_in("Hello. Well, okay."), [])
        self.assertEqual(analyze.people_in("ask @Rex about it"), ["Rex"])

    def test_query_reads_topic_event_feeling_and_reach_back(self):
        q = analyze.query("Do you remember what Elena gave me for my birthday?", mood="embarrassed", known=["Elena"])
        self.assertIn("birthday", q["terms"])
        self.assertIn("gift", q["events"])
        self.assertEqual(q["people"], ["Elena"])
        self.assertTrue(q["reach"])
        self.assertEqual(q["mood"][0], "shame")

    def test_moment_separates_milestones_from_chatter(self):
        big = analyze.moment("Here, I got you a necklace for your birthday!", "*gasps*", 3, "neutral", "touched", 8)
        small = analyze.moment("nice weather today", "yeah it is", 0, "neutral", "neutral", 1)
        self.assertGreater(big["score"], .75)
        self.assertLess(small["score"], .2)
        self.assertGreaterEqual(analyze.moment("Remember this, please: I'm moving away.", "ok", 0, "", "", 0)["score"], .9)

    def test_model_cannot_promote_a_mere_mention(self):
        self.assertLess(analyze.moment("what's a good gift for a friend?", "hm", 0, "", "", 1)["score"], .55)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.st = mem_with(
            ("episodic", "{{user}} gave {{char}} a necklace on her birthday.", dict(imp=.8, turn=10)),
            ("emotional", "{{char}} felt deeply touched and nearly cried when {{user}} gave her the necklace.", dict(imp=.8, emo="touched", val=.9, turn=10, link="e1")),
            ("episodic", "{{user}} spilled coffee on {{char}}'s sketchbook and apologised.", dict(imp=.5, turn=40)),
            ("episodic", "{{user}} and {{char}} argued about Marcus lying to them.", dict(imp=.7, turn=30, people=["Marcus"])),
            ("semantic", "{{user}} dislikes being interrupted.", dict(imp=.9)),
            ("semantic", "{{user}} likes hiking in the mountains.", dict(imp=.5)),
            ("semantic", "{{user}} works as a nurse at St Mary's.", dict(imp=.6)),
            ("emotional", "{{char}} felt embarrassed when {{user}} discovered her secret diary.", dict(imp=.7, emo="embarrassed", val=-.6, turn=20)))

    def test_relevant_memories_are_found_by_meaning_not_just_words(self):
        r = pick(self.st, "what did you do with the present I bought you?")
        self.assertTrue(any("necklace" in t for t in texts(r)))

    def test_people_bring_their_events(self):
        r = pick(self.st, "I ran into Marcus today")
        self.assertTrue(any("Marcus" in t for t in texts(r)))

    def test_topic_match_in_the_semantic_layer(self):
        self.assertTrue(any("hiking" in t for t in texts(pick(self.st, "Want to go hiking this weekend?"))))

    def test_small_talk_does_not_dump_the_store(self):
        r = pick(self.st, "what's the weather like?")
        self.assertLessEqual(len(r["trace"]), 2)
        self.assertFalse(any(w in " ".join(texts(r)) for w in ("hiking", "nurse", "Marcus", "sketchbook")))

    def test_boundaries_are_always_on(self):
        r = pick(self.st, "what's the weather like?")
        self.assertIn("{{user}} dislikes being interrupted.", texts(r))
        self.assertEqual(r["trace"][0]["why"], "always")

    def test_an_event_brings_the_feeling_it_left(self):
        r = pick(self.st, "do you still have the necklace?")
        self.assertTrue(any("touched" in t for t in texts(r)))

    def test_feelings_match_by_emotion_and_mood(self):
        r = pick(self.st, "Sorry if I embarrassed you earlier")
        self.assertTrue(any("embarrassed" in t for t in texts(r)))
        calm = pick(mem_with(("emotional", "{{char}} felt embarrassed about the diary.", dict(imp=.4, emo="embarrassed", val=-.6, turn=5))), "and then?", mood="flustered")
        self.assertTrue(any("embarrassed" in t for t in texts(calm)))      # mood-congruent recall

    def test_a_fresh_big_moment_still_colours_replies(self):
        st = mem_with(("episodic", "{{user}} confessed their love to {{char}} and kissed her.", dict(imp=.9, turn=58)))
        self.assertEqual(texts(pick(st, "so, what now?")), ["{{user}} confessed their love to {{char}} and kissed her."])
        old = mem_with(("episodic", "{{user}} confessed their love to {{char}} and kissed her.", dict(imp=.9, turn=10)), turn=200)
        self.assertEqual(pick(old, "so, what now?", turn=201)["trace"], [])

    def test_recency_and_importance_break_ties(self):
        st = mem_with(("episodic", "{{user}} cooked pasta for {{char}} on Monday evening.", dict(imp=.5, turn=5)),
                      ("episodic", "{{user}} baked pasta for {{char}} on Friday afternoon.", dict(imp=.5, turn=55)), turn=60)
        order = [e["rec"] for e in retrieve.rank(st["mem"], analyze.query("remember the pasta?"), 61, store.now_ms())]
        self.assertGreater(max(order), min(order))
        r = pick(st, "about that pasta", cfg=recall.settings(dict(ON, depth="deep")))
        self.assertIn("Friday", texts(r)[0])
        st2 = mem_with(("episodic", "{{user}} fixed {{char}}'s bicycle chain.", dict(imp=.3, turn=50)),
                       ("episodic", "{{user}} fixed {{char}}'s bicycle wheel after the crash.", dict(imp=.9, turn=50)), turn=60)
        self.assertIn("wheel", texts(pick(st2, "my bicycle?", cfg=recall.settings(dict(ON, depth="light"))))[0])

    def test_budget_and_depth(self):
        specs = [("semantic", f"{{{{user}}}} enjoys {word(k)} adventures with {word(k + 500)}", dict(imp=.5)) for k in range(30)]
        st = mem_with(*specs)
        msg = " ".join(f"{word(k)} {word(k + 500)}" for k in range(30))
        n = {d: len(pick(st, msg, cfg=recall.settings(dict(ON, depth=d)))["trace"]) for d in ("light", "standard", "deep")}
        self.assertLessEqual(n["light"], 4)
        self.assertLessEqual(n["standard"], 7)
        self.assertLessEqual(n["deep"], 10)
        self.assertLess(n["light"], n["deep"])
        self.assertLessEqual(len(pick(st, msg)["block"]), 1200)

    def test_near_duplicates_are_not_injected_twice(self):
        st = mem_with(("episodic", "{{user}} took {{char}} to the lake for a picnic.", dict(imp=.6, turn=50)))
        first = st["mem"]["items"][0]
        st["mem"]["items"].append(dict(first, id="e99", text="{{user}} took {{char}} to the lake for a picnic lunch.", turn=51))   # e.g. from hand edits
        self.assertEqual(len(pick(st, "remember the lake picnic?")["trace"]), 1)

    def test_pins_always_make_it(self):
        st = mem_with(("semantic", "{{char}} must never reveal the lighthouse key.", dict(imp=.3, pin=True)))
        self.assertEqual(len(pick(st, "hello")["trace"]), 1)

    def test_empty_memory_adds_nothing(self):
        r = pick({}, "hello there")
        self.assertEqual((r["block"], r["ids"]), ("", []))

    def test_chats_from_before_the_feature_still_recall_their_facts(self):
        r = retrieve.select({"facts": ["Sam likes hiking", "Sam has a dog named Rex"]}, [{"role": "user", "content": "walk the dog?"}],
                            user="Sam", char="Mira", cfg=CFG, turn=5)
        self.assertEqual(texts(r), ["{{user}} has a dog named Rex"])

    def test_short_term_scene_and_recent_events(self):
        st = mem_with()
        st["mem"]["scene"] = "A rainy evening in the cafe"
        store.push_recent(st["mem"], "Sam ordered two hot chocolates", .4, 59)
        store.push_recent(st["mem"], "An ancient event from long ago", .4, 5)
        short = pick(st, "hello")["short"]
        self.assertEqual(short, ["Scene: A rainy evening in the cafe", "Just happened: Sam ordered two hot chocolates"])


class LearnTests(unittest.TestCase):
    HIST = [{"role": "user", "content": "Here, I got you a necklace for your birthday! Please don't interrupt me while I explain.", "ts": 1},
            {"role": "assistant", "content": "*gasps* Oh... Sam, I... thank you.", "ts": 2}]
    MEM = {"episode": "Sam gave Mira a necklace on her birthday.", "people": ["Elena"], "importance": 9, "emotion": "touched",
           "feeling": "Mira felt deeply touched when Sam gave her the necklace.", "facts": ["Mira loves jewelry"]}

    def run_update(self, mem=None, st=None, cfg=CFG, hist=None, j=None, **kw):
        st = st if st is not None else {"facts": []}
        ask = (lambda p, n: json.dumps(mem)) if mem is not None else None
        r = learn.update(st, j or {"facts": [], "scene": "Mira's birthday evening", "event": "Sam handed Mira a birthday necklace", "importance": 9},
                         hist or self.HIST, user="Sam", char="Mira", cfg=cfg, turn=2, delta=4, mood_before="neutral", mood_after="touched", ask=ask, **kw)
        return st, r

    def test_important_moment_writes_all_three_layers_linked(self):
        st, r = self.run_update(self.MEM)
        by = {i["t"]: i for i in st["mem"]["items"] if i["t"] != "semantic"}
        self.assertEqual(by["episodic"]["text"], "{{user}} gave {{char}} a necklace on her birthday.")
        self.assertEqual(by["emotional"]["link"], by["episodic"]["id"])
        self.assertEqual(by["emotional"]["emo"], "touched")
        self.assertGreater(by["emotional"]["val"], .5)
        self.assertEqual(by["episodic"]["people"], ["Elena"])
        sem = {i["text"]: i for i in st["mem"]["items"] if i["t"] == "semantic"}
        self.assertEqual(sem["{{char}} loves jewelry"]["subj"], "self")
        self.assertGreaterEqual(sem["{{user}} asked {{char}} not to interrupt {{user}}"]["imp"], .85)
        self.assertIn("Mira's birthday evening".replace("Mira", "{{char}}"), st["mem"]["scene"])
        self.assertTrue(r["added"])

    def test_small_talk_writes_only_short_term(self):
        hist = [{"role": "user", "content": "nice weather today"}, {"role": "assistant", "content": "Yeah, it is."}]
        called = []
        st = {"facts": []}
        learn.update(st, {"facts": [], "scene": "Walking in the park", "event": "", "importance": 1}, hist, user="Sam", char="Mira", cfg=CFG, turn=2,
                     ask=lambda p, n: called.append(p) or "{}")
        self.assertEqual(called, [])
        self.assertEqual([i for i in st["mem"]["items"]], [])
        self.assertEqual(st["mem"]["scene"], "Walking in the park")

    def test_model_failure_falls_back_to_a_plain_note(self):
        st = {"facts": []}
        learn.update(st, {"importance": 9}, self.HIST, user="Sam", char="Mira", cfg=CFG, turn=2, delta=4, mood_before="neutral", mood_after="touched", ask=lambda p, n: "sorry, no")
        eps = [i for i in st["mem"]["items"] if i["t"] == "episodic"]
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0]["src"], "auto-lite")
        self.assertIn("necklace", eps[0]["text"])
        self.assertTrue(any(i["t"] == "emotional" and i["link"] == eps[0]["id"] for i in st["mem"]["items"]))

    def test_learning_can_be_switched_off(self):
        st, _ = self.run_update(self.MEM, cfg=recall.settings(dict(ON, learn=False)))
        self.assertFalse([i for i in st["mem"]["items"] if i["t"] in ("episodic", "emotional")])
        self.assertTrue([i for i in st["mem"]["items"] if i["t"] == "semantic"])     # stated facts are still kept

    def test_asking_to_remember_always_counts(self):
        hist = [{"role": "user", "content": "Remember this: my sister Anna is called Anna and she visits in June."}, {"role": "assistant", "content": "Okay."}]
        st = {"facts": []}
        learn.update(st, {"importance": 0}, hist, user="Sam", char="Mira", cfg=CFG, turn=2, ask=lambda p, n: json.dumps(self.MEM))
        self.assertTrue([i for i in st["mem"]["items"] if i["t"] == "episodic"])

    def test_events_that_fall_out_of_short_term_are_promoted(self):
        st = {"facts": []}
        for k in range(store.RECENT_MAX + 3):
            learn.update(st, {"event": f"Sam showed Mira the {word(k)} thing", "importance": 8}, [{"role": "user", "content": f"look at thing {k}!"}, {"role": "assistant", "content": "wow"}],
                         user="Sam", char="Mira", cfg=recall.settings(dict(ON, learn=False)), turn=2 + 2 * k)
        promoted = [i for i in st["mem"]["items"] if i["src"] == "promoted"]
        self.assertEqual(len(promoted), 3)
        self.assertIn(word(0), promoted[0]["text"])
        dull = {"facts": []}                                    # events the model found unremarkable are simply forgotten
        for k in range(store.RECENT_MAX + 3):
            learn.update(dull, {"event": f"Sam mentioned the {word(k)} thing", "importance": 2}, [{"role": "user", "content": f"thing {k}"}, {"role": "assistant", "content": "ok"}],
                         user="Sam", char="Mira", cfg=recall.settings(dict(ON, learn=False)), turn=2 + 2 * k)
        self.assertEqual([i for i in dull["mem"]["items"] if i["src"] == "promoted"], [])

    def test_old_facts_list_follows_semantic_memory(self):
        st, _ = self.run_update(self.MEM, st={"facts": ["Sam likes tea"]})
        self.assertIn("{{user}} likes tea", st["facts"])
        self.assertTrue(all("{{char}} loves jewelry" != f for f in st["facts"]))      # only facts about the user
        store.remove(st["mem"], [i["id"] for i in st["mem"]["items"] if "tea" in i["text"]])
        self.assertNotIn("{{user}} likes tea", store.user_facts_mirror(st["mem"]))

    def test_recalling_strengthens_a_memory(self):
        st, _ = self.run_update(self.MEM)
        ep = next(i for i in st["mem"]["items"] if i["t"] == "episodic")
        learn.update(st, {}, [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}], user="Sam", char="Mira", cfg=CFG, turn=9, used=[ep["id"]])
        self.assertEqual((ep["n"], ep["last"]), (1, 9))

    def test_backfill_asks_only_about_important_windows(self):
        chat = []
        for k in range(12):
            chat += [{"role": "user", "content": f"just chatting about nothing in particular {k}", "ts": k}, {"role": "assistant", "content": "mm hm", "ts": k}]
        chat[8:8] = [{"role": "user", "content": "I promise I will come back for you, I swear it.", "ts": 99}, {"role": "assistant", "content": "...I'll hold you to that.", "ts": 100}]
        asked = []
        st = {"facts": []}
        mem = {"episode": "Sam promised to come back for Mira.", "importance": 9, "emotion": "hopeful", "feeling": "Mira felt hopeful when Sam promised to return.", "facts": []}
        r = learn.backfill(st, chat, user="Sam", char="Mira", cfg=CFG, ask=lambda p, n: asked.append(p) or json.dumps(mem))
        self.assertEqual(len(asked), 1)
        self.assertEqual(r["calls"], 1)
        self.assertTrue([i for i in st["mem"]["items"] if "promised" in i["text"]])


class PromptTests(unittest.TestCase):
    def build(self, st, text, mem=ON, user="Sam", hist=None):
        return build_messages(h.SHY, user, hist or [{"role": "user", "content": text}],
                              {"state": st, "mem": mem, "mode": "story", "words": (20, 60), "turn": 61})[0]["content"]

    def setUp(self):
        self.st = mem_with(("episodic", "{{user}} gave {{char}} a necklace on her birthday.", dict(imp=.8, turn=10)),
                           ("semantic", "{{user}} likes hiking in the mountains.", dict(imp=.5)),
                           ("semantic", "{{user}} works as a nurse.", dict(imp=.6)))
        self.st["facts"] = ["Sam likes hiking in the mountains", "Sam works as a nurse"]
        self.st["mem"]["scene"] = "A rainy evening"

    def test_only_what_matters_reaches_the_prompt(self):
        sys_ = self.build(self.st, "do you still wear the necklace I gave you?")
        self.assertIn("necklace on her birthday", sys_)
        self.assertNotIn("hiking", sys_)
        self.assertNotIn("nurse", sys_)
        self.assertIn("A rainy evening", sys_)
        self.assertNotIn("Scene: A rainy", sys_)
        self.assertIn("[What Mira remembers", sys_)

    def test_names_are_filled_in_from_placeholders(self):
        sys_ = self.build(self.st, "do you still wear the necklace?", user="Alex")
        self.assertIn("Alex gave Mira a necklace", sys_)
        self.assertNotIn("{{", sys_)

    def test_off_means_the_old_behaviour(self):
        sys_ = self.build(self.st, "hello", mem=None)
        self.assertIn("Things Mira knows about Sam", sys_)
        self.assertIn("hiking", sys_)
        self.assertNotIn("What Mira remembers", sys_)
        self.assertNotIn("Scene:", sys_)

    def test_summary_still_covers_trimmed_history(self):
        self.st["summary"] = "They met at the cafe and talked for hours."
        self.assertIn("They met at the cafe", self.build(self.st, "hello"))

    def test_nothing_relevant_means_no_memory_block(self):
        st = mem_with(("semantic", "{{user}} likes hiking in the mountains.", dict(imp=.5)))
        self.assertNotIn("What Mira remembers", self.build(st, "what time is it?"))


class PipelineTests(unittest.TestCase):
    def test_reply_reports_what_was_recalled_and_searches_once(self):
        fake = h.install(h.FakeLLM(["Oh, the necklace? I wear it every day."]))
        st = mem_with(("episodic", "{{user}} gave {{char}} a necklace on her birthday.", dict(imp=.8, turn=10)))
        b = {"char": h.BOLD, "user": "Sam", "history": [{"role": "user", "content": "still got the necklace?"}], "state": st,
             "params": {"mode": "story", "think": False, "max_tokens": 200, "mem": ON}}
        r = generate_reply(b, None)
        self.assertEqual(r["recalled"], ["e1"])
        self.assertEqual(r["recall"][0]["t"], "episodic")
        self.assertIn("necklace on her birthday", fake.calls[0][0]["content"])

    def test_off_adds_nothing(self):
        h.install(h.FakeLLM(["Fine."]))
        r = generate_reply({"char": h.BOLD, "user": "Sam", "history": [{"role": "user", "content": "hi"}], "state": {}, "params": {"mode": "story", "think": False}}, None)
        self.assertNotIn("recalled", r)

    def test_tracker_gets_extra_fields_only_when_on(self):
        fake = h.install(h.FakeLLM(track={"mood": "happy", "affection_delta": 1, "thought": "ok", "facts": []}))
        hist = [{"role": "user", "content": "hi there"}, {"role": "assistant", "content": "hello"}]
        track({"char": h.BOLD, "user": "Sam", "history": hist, "state": {}, "mem": ON})
        self.assertIn('"scene"', fake.calls[-1][-1]["content"])
        self.assertIn('"importance"', fake.calls[-1][-1]["content"])
        track({"char": h.BOLD, "user": "Sam", "history": hist, "state": {}})
        self.assertNotIn('"scene"', fake.calls[-1][-1]["content"])

    def test_track_end_to_end(self):
        h.install(MemLLM(mem=TestMem, track={"mood": "touched", "affection_delta": 4, "thought": "aw", "facts": ["Sam got a necklace for a birthday"],
                                             "scene": "Mira's birthday evening at the cafe", "event": "Sam handed Mira a necklace", "importance": 9}))
        hist = [{"role": "user", "content": "Here, I got you a necklace for your birthday!"}, {"role": "assistant", "content": "*gasps* Sam..."}]
        r = track({"char": h.BOLD, "user": "Sam", "history": hist, "state": {"affection": 50}, "mem": ON, "turn": 2})
        items = r["state"]["mem"]["items"]
        self.assertEqual({i["t"] for i in items}, {"episodic", "emotional", "semantic"})
        self.assertTrue(r["mem_added"])
        self.assertEqual(r["state"]["mem"]["turn"], 2)
        self.assertIn("{{user}} got a necklace for a birthday", r["state"]["facts"])   # facts must be grounded in what the user said
        self.assertIn("Sam handed", json.dumps(r["state"]["mem"]["recent"]).replace("{{user}}", "Sam"))

    def test_track_does_not_touch_the_callers_state(self):
        h.install(h.FakeLLM(track={"mood": "happy", "affection_delta": 0, "thought": "", "facts": ["Sam likes jazz"]}))
        st = {"affection": 50, "facts": [], "mem": {"items": [], "recent": [], "scene": "", "turn": 0, "seq": 0, "legacy": True}}
        track({"char": h.BOLD, "user": "Sam", "history": [{"role": "user", "content": "I like jazz."}, {"role": "assistant", "content": "ok"}], "state": st, "mem": ON})
        self.assertEqual(st["mem"]["items"], [])

    def test_memorize_builds_from_existing_chat(self):
        h.install(MemLLM(mem={"episode": "Sam promised to come back for Mira.", "importance": 9, "emotion": "hopeful",
                              "feeling": "Mira felt hopeful when Sam promised to return.", "facts": []}))
        chat = [{"role": "user", "content": "I promise I will come back for you, I swear."}, {"role": "assistant", "content": "I'll hold you to that."}]
        r = memorize({"char": h.BOLD, "user": "Sam", "history": chat, "state": {"facts": ["Sam likes tea"]}, "mem": ON})
        self.assertEqual(r["calls"], 1)
        self.assertTrue(any("promised" in i["text"] for i in r["state"]["mem"]["items"]))


TestMem = {"episode": "Sam gave Rex a necklace on Rex's birthday.", "importance": 9, "emotion": "touched",
           "feeling": "Rex felt touched when Sam gave him the necklace.", "facts": []}


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = h.serve()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_recall_preview_explains_itself(self):
        st = mem_with(("episodic", "{{user}} gave {{char}} a necklace on her birthday.", dict(imp=.8, turn=10)))
        code, r = h.call(self.srv, "POST", "/api/recall", {"name": "Mira", "user": "Sam", "state": st, "query": "the necklace?", "turn": 61})
        self.assertEqual(code, 200)
        self.assertEqual(r["trace"][0]["text"], "Sam gave Mira a necklace on her birthday.")
        self.assertIn("topic", r["trace"][0]["why"])

    def test_memorize_endpoint(self):
        h.install(MemLLM(mem={"episode": "Sam promised to come back for Mira.", "importance": 9, "emotion": "hopeful", "feeling": "", "facts": []}))
        chat = [{"role": "user", "content": "I promise I will come back for you, I swear."}, {"role": "assistant", "content": "I'll hold you to that."}]
        code, r = h.call(self.srv, "POST", "/api/memorize", {"char": h.SHY, "user": "Sam", "history": chat, "state": {}, "mem": ON})
        self.assertEqual(code, 200)
        self.assertGreaterEqual(r["added"], 1)

    def test_memorize_needs_a_model(self):
        h.install(None)
        code, r = h.call(self.srv, "POST", "/api/memorize", {"char": h.SHY, "user": "Sam", "history": [], "state": {}})
        self.assertIn("err", r)


if __name__ == "__main__":
    unittest.main()
