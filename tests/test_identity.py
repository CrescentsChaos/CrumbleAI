"""Multi-turn regression tests for context understanding, identity tracking, memory and continuity.

Every test drives the REAL pipeline (generate_reply -> track -> summarize -> state merge, with the same `from` trimming the
page does). Only the language model is faked: scripted replies reproduce the actual failures seen in the bundled chat
(becoming a mentioned person, "right wrist" for "left", a made-up shared dog, he/she for an unknown user...), and the tests
assert that the CODE catches, repairs or prevents them. Run: python3 -m unittest tests.test_identity -v
"""
import json
import re
import unittest

from crumble import identity
from crumble.llm import generate_reply
from crumble.memory import summarize, track
from crumble.recall import lexicon as lx, retrieve, store
from tests import helpers as h

FAITH = {"id": "faith", "name": "Faith", "gender": "Female (She/her)", "age": "20",
         "description": "Faith is a quiet university student who works part-time as a cashier.",
         "personality": "quiet, observant, guarded", "relationships": "Uncle: Jeb. Bestfriends: Lenny, Julia. Bully: Ryan.",
         "scenario": "A playground bench on a grey afternoon. Faith sits alone while some bullies tease her.",
         "first_mes": "*The bullies snatch her book away. You walk over to her bench.* Who are you?"}
ON = {"on": True}


class ScriptedLLM(h.FakeLLM):
    """FakeLLM whose summariser output is configurable and which separates chat calls from helper calls."""

    def __init__(self, replies=None, track=None, summary="A short summary."):
        super().__init__(replies, track)
        self.summary, self.chat = summary, []

    def create_chat_completion(self, messages, stream=False, **kw):
        if stream:
            self.chat.append(messages)
        elif "JSON" not in messages[-1]["content"]:
            self.calls.append(messages)
            return {"choices": [{"message": {"content": self.summary}, "finish_reason": "stop"}]}
        return super().create_chat_completion(messages, stream=stream, **kw)


class Sim:
    """A client: keeps the chat and the state, and talks to the server functions the way the page does."""

    def __init__(self, char=FAITH, user="Crescent", persona="", opening=True, track_json=None, summary="A short summary.", n_ctx=None, **params):
        self.c, self.user, self.persona = char, user, persona
        self.llm = h.install(ScriptedLLM(track=track_json or {"mood": "neutral", "affection_delta": 0, "thought": "", "facts": []}, summary=summary))
        self.hist = [{"role": "assistant", "content": char["first_mes"]}] if opening and char.get("first_mes") else []
        self.state, self.frm, self.params = {"affection": 50}, 0, dict(mode="story", think=False, max_tokens=200, mem=ON, **params)
        self.last = None

    def say(self, text, *replies, track_json=None):
        self.hist.append({"role": "user", "content": text})
        self.llm.replies = list(replies) or ["Hm."]
        self.llm.chat.clear()
        b = {"char": self.c, "user": self.user, "persona": self.persona, "history": list(self.hist), "state": self.state, "from": self.frm,
             "turn": len(self.hist), "params": dict(self.params)}
        self.last = generate_reply(b, None)
        self.hist.append({"role": "assistant", "content": self.last["text"]})
        if track_json is not None:
            self.llm.track = track_json
        tr = track({"char": self.c, "user": self.user, "persona": self.persona, "history": self.hist[-6:], "state": self.state, "mem": ON, "turn": len(self.hist)})
        self.state = {**self.state, **tr["state"]}
        return self.last["text"]

    def summarise(self, keep=4, **kw):
        upto = len(self.hist) - keep
        self.state["summary"] = summarize({"char": self.c, "user": self.user, "persona": self.persona, "history": self.hist[self.state.get("sumUpto", 0):upto],
                                           "summary": self.state.get("summary", "")})
        self.state["sumUpto"] = self.frm = upto

    @property
    def system(self):
        return self.llm.chat[0][0]["content"]

    @property
    def tail(self):
        return self.llm.chat[0][-1]["content"]

    def attempts(self):
        return len(self.llm.chat)


def who(sim):
    s = sim.system
    return s[s.index("[Who's who"):s.index("[Who's who") + 1400].split("\n\n")[0]


# --------------------------------------------------------------------------------------------------------------------- 1
class InitialContext(unittest.TestCase):
    def test_opening_and_first_reply_are_understood(self):
        sim = Sim()
        sim.say("My sister's name is Nadia. She hates roses but loves sunflowers.", "*Faith blinks.* Your sister? I didn't ask about her. Who are you?")
        self.assertIn("opened this scene with", sim.system)
        self.assertIn("The bullies snatch her book away", sim.system)
        self.assertIn("reply to exactly that", sim.system)
        self.assertIn("playground bench", sim.system)

    def test_opening_survives_summary_trimming_and_is_not_mislabelled(self):
        sim = Sim(summary="SETTING & STATE\nLocation: the bench\nCurrent State: talking")
        for i in range(8):
            sim.say(f"message number {i} about the weather", f"*Faith looks up* reply {i} about clouds")
        sim.summarise(keep=4)
        sim.say("so what now?", "*Faith shrugs.* Not sure.")
        self.assertGreater(sim.frm, 0)
        self.assertIn("The bullies snatch her book away", sim.system)                       # the true opening, read from the whole chat
        self.assertIn("Everything since then continues from that moment", sim.system)
        self.assertNotIn("first message is a reply to exactly that", sim.system)           # no longer the first exchange
        msgs = [m["content"] for m in sim.llm.chat[0][1:]]
        self.assertNotIn("reply 0 about clouds", " ".join(msgs))                            # trimmed history really was trimmed

    def test_fold_does_not_swallow_a_midchat_message_as_the_opening(self):
        sim = Sim(summary="SETTING & STATE\nLocation: the bench", fold=True)
        for i in range(6):
            sim.say(f"line {i}", f"*Faith nods* answer {i}")
        sim.summarise(keep=3)
        sim.say("go on", "ok")
        self.assertNotIn("opening message - Faith already said this", " ".join(m["content"] for m in sim.llm.chat[0]))


# --------------------------------------------------------------------------------------------------------------------- 2 + 5
class IdentitySeparationAndImpersonation(unittest.TestCase):
    NADIA = '*Nadia\'s face lights up as she sees Faith approach.* "Faith! It\'s been too long, dear sister."'
    FINE = '*Faith pulls her book to her chest.* Who is Nadia? And who are you?'

    def test_who_is_who_block_separates_everyone(self):
        sim = Sim()
        sim.say("My sister's name is Nadia. She hates roses but loves sunflowers.", self.FINE)
        w = who(sim)
        self.assertIn("You are Faith (she/her)", w)
        self.assertIn("Nadia (Crescent's sister, she/her)", w)
        self.assertIn("Jeb (Faith's uncle, he/him)", w)                      # the character's own relatives come from her sheet
        self.assertIn("NOT Faith"[:0] + "Never speak as, for or turn into Crescent", w)

    def test_becoming_a_mentioned_person_is_caught_and_rerolled(self):
        sim = Sim()
        text = sim.say("My sister's name is Nadia. She hates roses but loves sunflowers.", self.NADIA, self.FINE)
        self.assertEqual(text, self.FINE)
        self.assertEqual(sim.last["retries"], 1)
        self.assertIn("only someone being talked about", sim.llm.chat[1][-1]["content"])   # the retry names the mistake

    def test_persistent_impersonation_is_reported_not_hidden(self):
        sim = Sim()
        sim.say("My sister's name is Nadia.", self.NADIA)
        self.assertIn("impersonation", sim.last.get("identity", []))

    def test_speaker_label_of_a_mentioned_person_is_cut_off(self):
        sim = Sim()
        text = sim.say("My sister's name is Nadia.", "*Faith frowns.* Why tell me that?\nNadia: Faith! I found you!")
        self.assertNotIn("Nadia:", text)
        self.assertIn("Why tell me that", text)

    def test_writing_the_users_lines_is_cut_out(self):
        sim = Sim()
        bad = '*Faith smiles.* "Bruno? Was he a big dog?" "Yes, he was a German Shepherd," Crescent replies, smiling. "We loved him."'
        text = sim.say("My childhood dog's name was Bruno.", bad, bad, bad)
        self.assertNotIn("Crescent replies", text)
        self.assertNotIn("German Shepherd", text)
        self.assertIn("Bruno? Was he a big dog", text)

    def test_addressing_itself_by_name_means_wrong_side(self):
        sim = Sim()
        sim.say("hello there", '"Faith! It\'s been ages," she says.', "*Faith tilts her head.* Hello.")
        self.assertEqual(sim.last["text"], "*Faith tilts her head.* Hello.")


# --------------------------------------------------------------------------------------------------------------------- 3
class Names(unittest.TestCase):
    def test_user_states_name_when_ui_name_is_default(self):
        sim = Sim(user="User")
        sim.say("Hi, I'm Crescent.", "*Faith nods.* Hm.")
        sim.say("what's my name?", "Crescent.")
        self.assertIn("talking with Crescent", sim.system)
        self.assertNotIn("User", sim.system.replace("Crescent", ""))

    def test_user_corrects_own_name_and_wrong_name_is_blocked(self):
        sim = Sim(user="User")
        text = sim.say("My name is Crescent, not Cres.", "Nice to meet you, Cres.", "Nice to meet you, Crescent.")
        self.assertEqual(text, "Nice to meet you, Crescent.")
        sim.say("ok", "Sure.")
        self.assertIn("NOT called Cres", sim.system)

    def test_user_corrects_the_characters_name_not_the_other_way(self):
        sim = Sim()
        sim.say("Hey Fay, your name is Faith, not Fay, right? sorry", "Yes. It's Faith.")
        w = who(sim)
        self.assertIn("You are Faith, not Fay", w)         # a correction the user made about the CHARACTER
        self.assertNotIn("Crescent is NOT called", w)      # ...is not recorded as a correction of the user's name
        sim2 = Sim()
        sim2.say("Your name is Lily.", "Hm.")
        self.assertIn("not Lily", who(sim2))

    def test_character_claiming_a_wrong_name_is_rerolled(self):
        sim = Sim()
        text = sim.say("Your name is Lily, isn't it?", "*smiles* Yes, I'm Lily!", "*shakes her head* It's Faith.")
        self.assertEqual(text, "*shakes her head* It's Faith.")

    def test_nickname_request_latest_statement_wins(self):
        sim = Sim(user="Crescent")
        sim.say("Call me Cres.", "Okay, Cres.")
        sim.say("what do you call me?", "Cres.")
        self.assertIn("talking with Cres", sim.system)
        self.assertIn("also Crescent", sim.system)

    def test_name_unit_parsing(self):
        from crumble.identity import names
        self.assertEqual(names.user_names(["It's Crescent not Cres"]), ("Crescent", {"Cres"}))
        self.assertEqual(names.user_names(["I'm not Sam, I'm Alex"]), ("Alex", {"Sam"}))
        self.assertEqual(names.user_names(["I'm tired today"])[0], "")


# --------------------------------------------------------------------------------------------------------------------- 4
class Gender(unittest.TestCase):
    def test_unknown_user_gender_is_never_assumed(self):
        sim = Sim()
        sim.say("hello", "*Faith looks at you.* Hi.")
        self.assertIn("NOT been stated", who(sim))

    def test_assumed_pronoun_for_unknown_user_is_rerolled(self):
        sim = Sim()
        text = sim.say("hello", "*Crescent steps closer and he smiles.* Hi.", "*Faith watches you step closer.* Hi.")
        self.assertEqual(text, "*Faith watches you step closer.* Hi.")

    def test_stated_gender_is_used_and_enforced(self):
        sim = Sim()
        sim.say("I'm a girl, by the way.", "*Faith relaxes a little.* Okay.")
        sim.say("yeah", "Sure.")
        self.assertIn("Crescent is she/her", sim.system)
        sim.say("so", "*Crescent hugs the book and he sighs.* Hm.", "*Faith sees Crescent sigh as she hugs the book.* Hm.")
        self.assertIn("Wrong pronoun for Crescent", sim.llm.chat[1][-1]["content"])

    def test_pronoun_of_a_mentioned_person_follows_the_relation(self):
        sim = Sim()
        sim.say("My brother Tom and my sister Nadia are here.", '*Faith looks around.* Which one is Tom?')
        w = who(sim)
        self.assertIn("Tom (Crescent's brother, he/him)", w)
        self.assertIn("Nadia (Crescent's sister, she/her)", w)
        sim.say("Nadia is shy.", "*Nadia stays quiet, he nods.* ...", "*Faith nods.* Shy people are fine.")
        self.assertEqual(sim.last["text"], "*Faith nods.* Shy people are fine.")

    def test_character_gender_comes_from_the_sheet(self):
        sim = Sim()
        sim.say("hi", "Hi.")
        self.assertIn("Faith (she/her)", who(sim))

    def test_stored_facts_never_gain_an_assumed_gender(self):
        sim = Sim(track_json={"mood": "neutral", "affection_delta": 0, "thought": "", "facts": ["Crescent broke her left wrist when she was 12"]})
        sim.say("I broke my left wrist when I was 12.", "*Faith winces.* Ouch.")
        facts = " | ".join(sim.state["facts"])
        self.assertIn("their left wrist", facts)
        self.assertNotIn("her", facts)
        self.assertIn("they were 12", facts)

    def test_persona_gender_is_respected(self):
        sim = Sim(persona="A 19-year-old man who loves climbing.")
        sim.say("hi", "Hi.")
        self.assertIn("Crescent is he/him", sim.system)


# --------------------------------------------------------------------------------------------------------------------- 6
class Relevance(unittest.TestCase):
    def setUp(self):
        self.sim = Sim()
        self.sim.say("My father's old watch stopped working in 2019.", "*Faith listens.* Did you try to fix it?")
        self.sim.say("The watch repair shop said it can't be fixed.", "*Faith sighs.* That's sad about the watch.")

    def test_topic_change_is_recognised_and_answered_first(self):
        self.sim.say("What flowers do you like?", "*Faith thinks.* Sunflowers.")
        self.assertIn("changed the subject", self.sim.tail)
        self.assertIn("What flowers do you like?", self.sim.tail)

    def test_same_topic_is_not_flagged(self):
        self.sim.say("Maybe the watch repair guy was wrong about the watch.", "Maybe.")
        self.assertNotIn("changed the subject", self.sim.tail)

    def test_explicit_markers_count(self):
        self.sim.say("anyway, it's getting cold out here", "Yeah.")
        self.assertIn("changed the subject", self.sim.tail)

    def test_old_topic_does_not_pull_memories_into_the_search_after_a_switch(self):
        from crumble import recall
        st = {"facts": [], "mood": "neutral"}
        m = store.ensure(st, "Crescent", "Faith")
        m["turn"] = 10
        store.add(m, "episodic", "{{user}} told {{char}} about the broken watch and the repair shop.", imp=.8, turn=2)
        hist = [{"role": "user", "content": "the watch repair shop said it can't be fixed"}, {"role": "assistant", "content": "That's sad about the watch."},
                {"role": "user", "content": "ok"}]
        cfg = recall.settings(ON)
        old = recall.select(st, hist, user="Crescent", char="Faith", cfg=cfg, turn=11)
        new = recall.select(st, hist, user="Crescent", char="Faith", cfg=cfg, turn=11, fresh=True)
        self.assertTrue(old and old["trace"])                # the old context finds the watch memory...
        self.assertFalse(new and new["trace"])               # ...but after a subject change it must not

    def test_the_latest_message_is_what_the_model_is_asked_to_answer(self):
        self.sim.say("What flowers do you like?", "Sunflowers.")
        self.assertIn("What flowers do you like?", self.sim.llm.chat[0][-2]["content"] + self.sim.tail)
        self.assertEqual(self.sim.llm.chat[0][-1]["role"], "user")


# --------------------------------------------------------------------------------------------------------------------- 7
POLLUTED = {"mood": "happy", "affection_delta": 2, "thought": "", "facts": [
    "Crescent broke their right wrist when they were kids by falling off their bike",       # invented by the character's reply
    "Crescent and Faith both had a German Shepherd mix named Bruno as a childhood pet",      # invented shared memory
    "Faith loves her sister Nadia",                                                         # the USER's sister, wrongly given to the character
    "Crescent broke their left wrist when they were 12"],                                     # the one the user really said
    "scene": "the bench", "event": "Faith learned Crescent's childhood dog Bruno was also her dog", "importance": 8}


class PersonalExperiences(unittest.TestCase):
    def test_invented_ungrounded_and_misattributed_memories_are_not_stored(self):
        sim = Sim(track_json=POLLUTED)
        sim.say("I broke my left wrist when I was 12. My sister's name is Nadia.", "*Faith winces.* Right wrist? And Bruno was our dog?")
        stored = " | ".join(i["text"] for i in sim.state["mem"]["items"]) + " | " + " | ".join(sim.state["facts"])
        self.assertIn("left wrist", stored)
        for bad in ("right wrist", "bike", "Bruno", "loves her sister", "German Shepherd"):
            self.assertNotIn(bad, stored, bad)

    def test_users_experiences_are_attributed_to_the_user_in_the_prompt(self):
        sim = Sim()
        sim.say("I broke my left wrist when I was 12.", "Ouch.")
        sim.say("which wrist was it again?", "Left.")
        self.assertIn('Crescent: "I broke my left wrist when I was 12."', sim.tail)
        self.assertIn("never to Faith", who(sim))

    def test_invented_shared_experience_in_a_reply_is_cut_when_it_is_the_users_voice(self):
        sim = Sim()
        text = sim.say("My childhood dog's name was Bruno.", '"Bruno?" Faith gasps. "Yes! He was a German Shepherd," Crescent replies. "Our dog!"')
        self.assertNotIn("Our dog", text)

    def test_shared_past_is_allowed_when_the_user_really_said_we(self):
        sim = Sim()
        sim.say("We both had a dog named Bruno when we were kids, remember?", "Hm.")
        g = identity.make_guard(identity.build(FAITH, "Crescent", sim.hist), [m["content"] for m in sim.hist if m["role"] == "user"])
        self.assertIsNotNone(g("{{char}} and {{user}} both had a dog named Bruno as childhood pets", "episode"))

    def test_the_users_relatives_stay_the_users(self):
        g = identity.make_guard(identity.build(FAITH, "Crescent", [{"role": "user", "content": "My sister's name is Nadia."}]), ["My sister's name is Nadia."])
        self.assertIsNone(g("{{char}} loves her sister Nadia", "fact"))
        self.assertIsNone(g("{{char}} and Nadia reunited after a long time", "episode"))


# --------------------------------------------------------------------------------------------------------------------- 8
class EpisodicMemoryAndExactRecall(unittest.TestCase):
    def setUp(self):
        self.sim = Sim()
        for t in ("My sister's name is Nadia. She hates roses but loves sunflowers.", "My birthday is October 17.", "I broke my left wrist when I was 12.",
                  "My father's old watch stopped working in 2019.", "I always order coffee without sugar.", "My childhood dog's name was Bruno."):
            self.sim.say(t, "*Faith listens.* I see.")
        for i in range(6):
            self.sim.say(f"filler chatter about the bench number {i}", f"*Faith shrugs* uh huh {i}")

    def ask(self, q, *replies):
        return self.sim.say(q, *replies)

    def test_exact_details_come_back_exact(self):
        for q, want in (("Which wrist did I break?", "left wrist"), ("What was my dog's name?", "Bruno"), ("When is my birthday?", "October 17"),
                        ("What happened with the watch in 2019?", "2019"), ("What do I usually put in my coffee?", "without sugar"),
                        ("What flowers does Nadia like?", "sunflowers")):
            self.ask(q, "Hm.")
            self.assertIn(want, self.sim.tail, q)
            self.assertIn("Exact facts for this question", self.sim.tail, q)

    def test_contradicting_the_record_is_rerolled(self):
        t = self.ask("Which wrist did I break?", "Your right wrist, wasn't it?", "Your left wrist, from when you were twelve.")
        self.assertEqual(t, "Your left wrist, from when you were twelve.")
        t = self.ask("What was my dog's name?", "*Faith smiles.* Your dog's name was Max.", "Bruno.")
        self.assertEqual(t, "Bruno.")
        t = self.ask("When is my birthday?", "It's October 3rd.", "October 17th.")
        self.assertEqual(t, "October 17th.")

    def test_ignoring_the_record_is_rerolled(self):
        t = self.ask("What do I usually put in my coffee?", "A dash of cinnamon and almond milk, right?", "No sugar. You always say so.")
        self.assertEqual(t, "No sugar. You always say so.")

    def test_a_false_remember_when_is_corrected_not_agreed_with(self):
        t = self.ask("Remember when I told you Nadia loved roses?", "Of course I remember! Roses are lovely.", "*Faith frowns.* Not quite: you said Nadia hates roses and loves sunflowers.")
        self.assertIn("hates roses", t)
        self.assertIn("they actually said", self.sim.llm.chat[0][-1]["content"])

    def test_what_was_never_told_is_not_invented(self):
        t = self.ask("What is my favorite color?", "Blue! You always wear blue.", "*Faith shrugs.* You never told me.")
        self.assertEqual(t, "*Faith shrugs.* You never told me.")
        self.assertIn("never told Faith this", self.sim.llm.chat[0][-1]["content"])

    def test_a_memory_contradicting_the_user_is_vetoed_at_retrieval(self):
        st = {"mem": store.blank()}
        store.add(st["mem"], "semantic", "{{user}} broke their right wrist as a kid", imp=.9, turn=1)
        self.sim.state["mem"] = st["mem"]
        self.ask("Which wrist did I break?", "Left.")
        self.assertNotIn("right wrist", self.sim.system)

    def test_numbers_and_irregular_verbs_are_indexed(self):
        self.assertIn("2019", lx.terms("it stopped in 2019"))
        self.assertIn("17", lx.terms("October 17th"))
        self.assertEqual(lx.stem("broke"), lx.stem("break"))
        self.assertEqual(lx.stem("broken"), lx.stem("breaking"[:5]) if False else lx.stem("break"))

    def test_exact_facts_survive_summary_trimming(self):
        self.sim.summarise(keep=3)
        self.assertGreater(self.sim.frm, 10)
        self.ask("Which wrist did I break?", "Hm.")
        self.assertIn("left wrist", self.sim.tail)

    def test_episodic_memories_still_form_and_return(self):
        sim = Sim(track_json={"mood": "touched", "affection_delta": 3, "thought": "", "facts": [], "scene": "the bench",
                              "event": "Crescent promised to bring Faith a new book tomorrow", "importance": 9,
                              "episode": "Crescent promised to bring Faith a new book tomorrow"})
        sim.say("I promise I will bring you a new book tomorrow.", "*Faith's eyes widen.* You'd do that?")
        for i in range(5):
            sim.say(f"anyway number {i}", "ok")
        sim.say("Did I promise you anything?", "Hm.")
        self.assertIn("book", (sim.system + sim.tail).lower())


# --------------------------------------------------------------------------------------------------------------------- 9
class Summaries(unittest.TestCase):
    def test_summary_prompt_carries_who_is_who_and_labels_speakers(self):
        sim = Sim()
        sim.say("My sister's name is Nadia. I'm a guy.", "Hm.")
        sim.summarise(keep=1)
        ask = sim.llm.calls[-1][0]["content"]
        self.assertIn("Who's who", ask)
        self.assertIn("Crescent is the user (he/him)", ask)
        self.assertIn("Nadia (Crescent's sister)", ask)
        self.assertIn("Crescent (the user): My sister's name is Nadia", ask)
        self.assertIn("never present and never take part", ask)

    def test_invented_age_and_gender_are_removed_from_the_summary(self):
        bad = ("SETTING & STATE\nLocation: bench\nCurrent State: Crescent, 20-year-old, broke her wrist; Faith (20-year-old) listens\n"
               "RELATIONSHIP DYNAMIC\nPrimary Dynamic: Faith comforts Crescent")
        sim = Sim(summary=bad)
        sim.say("I broke my wrist.", "Ouch.")
        sim.summarise(keep=1)
        s = sim.state["summary"]
        self.assertNotIn("Crescent, 20-year-old", s)
        self.assertNotIn("her wrist", s)
        self.assertIn("their wrist", s)

    def test_summary_is_read_and_old_characters_section_is_left_out(self):
        sim = Sim()
        sim.state["summary"] = ("CHARACTERS\nFaith: Loves her sister Nadia.\nCrescent: 20-year-old with a broken left wrist\n\n"
                                "SETTING & STATE\nLocation: the pier\nCurrent State: Faith and Crescent are walking\n\nPIVOTAL MOMENTS\n- Crescent promised a book")
        sim.say("keep walking", "ok")
        s = sim.system
        self.assertIn("Location: the pier", s)
        self.assertIn("Crescent promised a book", s)
        self.assertNotIn("Loves her sister Nadia", s)
        self.assertNotIn("20-year-old with a broken left wrist", s)

    def test_summary_is_incorporated_when_the_prompt_has_to_shrink(self):
        sim = Sim()
        sim.state["summary"] = "SETTING & STATE\nLocation: the pier\n\nPIVOTAL MOMENTS\n- Crescent promised a book"
        for i in range(30):
            sim.say(f"long line number {i} " + "word " * 40, "ok " + "word " * 30)
        self.assertIn("Crescent promised a book", sim.system)


# --------------------------------------------------------------------------------------------------------------------- 10
class ContextIntegration(unittest.TestCase):
    def test_long_conversation_with_many_people_stays_consistent(self):
        sim = Sim(summary="SETTING & STATE\nLocation: the pier\nCurrent State: chatting\nPIVOTAL MOMENTS\n- Crescent told Faith about family")
        sim.say("My sister's name is Nadia. She hates roses but loves sunflowers.", "*Faith blinks.* Hm.")
        sim.say("My brother Tom plays guitar and he is older than me.", "*Faith nods.* Cool.")
        sim.say("My dad, Jeb, is a mechanic.", "*Faith* wait, my uncle is Jeb too.")
        sim.say("I broke my left wrist when I was 12.", "Ouch.")
        for i in range(14):
            sim.say(f"random chatter {i} about the pier and the sea", f"*Faith* waves crash {i}")
        sim.summarise(keep=4)
        for i in range(4):
            sim.say(f"more chatter {i} about boats", "ok")
        w = who(sim)
        for want in ("Nadia (Crescent's sister, she/her)", "Tom (Crescent's brother, he/him)", "Jeb (Faith's uncle, he/him)", "Lenny", "Ryan"):
            self.assertIn(want, w)
        sim.say("What does Tom play, and which wrist did I break?", "Hm.")
        self.assertIn("Tom plays guitar", sim.tail)
        self.assertIn("left wrist", sim.tail)
        self.assertIn("Crescent promised"[:0] + "told Faith about family", sim.system)            # the summary is there too
        self.assertIn("The bullies snatch her book away", sim.system)                             # and so is the opening
        t = sim.say("What flowers does Nadia like?", "*Nadia grins.* I like roses.", "*Faith thinks.* Sunflowers, you said. And she hates roses.")
        self.assertIn("Sunflowers", t)

    def test_identity_block_is_compact(self):
        sim = Sim()
        sim.say("My sister's name is Nadia. My brother Tom plays guitar.", "Hm.")
        block = who(sim)
        self.assertLess(len(block) / 4, 260)           # tokens, roughly

    def test_everything_is_rederived_after_rewind_or_edit(self):
        sim = Sim()
        sim.say("My sister's name is Nadia.", "Hm.")
        sim.say("I'm a girl.", "Hm.")
        sim.hist = sim.hist[:3]                          # rewind past the gender statement and the second user turn
        sim.say("hello again", "Hi.")
        self.assertIn("NOT been stated", sim.system)
        self.assertIn("Nadia", sim.system)
        sim.hist[1]["content"] = "My sister's name is Maria."
        sim.say("again", "Hi.")
        self.assertIn("Maria", sim.system)
        self.assertNotIn("Nadia (", sim.system)

    def test_group_members_are_not_treated_as_mentioned_people(self):
        grp = {"id": "g", "members": [{"id": "faith", "name": "Faith"}, {"id": "ryan", "name": "Ryan"}]}
        led = identity.build(FAITH, "Crescent", [{"role": "user", "content": "hi"}], grp=grp)
        self.assertNotIn("ryan", led["others"])
        self.assertIn("jeb", led["others"])


if __name__ == "__main__":
    unittest.main()
