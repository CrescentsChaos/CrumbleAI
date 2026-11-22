import json
import re
import unittest
from pathlib import Path

from crumble import chronicle
from crumble.llm import generate_reply
from crumble.recall import store
from crumble.rp import body as B
import crumble.rp.dice as _dice
from crumble.rp import skillset as SK
from crumble.rp.dice import check, judge
from crumble.rp.resolve import rp_observe, rp_resolve
from tests import helpers as h

M = [{"id": "m", "name": "Mira", "stats": "STR 10 DEX 12 CON 12", "combat": "dagger, leather armor", "skills": "Novice rogue"},
     {"id": "g", "name": "Golem", "stats": "STR 16 DEX 8 CON 16", "combat": "stone fists, golem, fearless", "skills": ""}]
SKILLS = "Master swordsman, 12 years of kenjutsu. Fire magic (level 6). Resurrection magic (rank A). Weak to water."
BASE = dict(members=M, user="Tonoy", ustats="STR 13 DEX 14 CON 12 INT 10 WIS 12 CHA 10", ugear="katana, leather armor", uskills=SKILLS,
            aff={"m": 50, "g": 50}, mood={}, cfg={"mode": "auto", "romance": True}, turn=5)


def go(text, rp=None, **kw):
    return rp_resolve(dict(BASE, text=text, rp=rp or {}, **kw))


class NoDiceTests(unittest.TestCase):
    def test_judging_is_deterministic(self):
        self.assertEqual([check(2, 12) for _ in range(20)], [check(2, 12)] * 20)
        self.assertEqual(judge(15, 11)["tier"], "win")
        self.assertEqual(judge(30, 11)["tier"], "crit")
        self.assertEqual(judge(5, 11)["tier"], "fail")

    def test_no_randomness_in_the_engine(self):
        for f in ("dice.py", "resolve.py", "skillset.py", "body.py"):
            src = (Path(_dice.__file__).parent / f).read_text()
            self.assertNotRegex(src, r"(?m)^\s*(?:import random|from random)", f)
            self.assertNotRegex(src, r"\brandom\.\w+\(", f)



class SkillTests(unittest.TestCase):
    def test_description_becomes_data(self):
        p = SK.parse(SKILLS, "katana; silver ankh")
        names = {t["name"].lower() for t in p["techs"]}
        self.assertIn("swordsmanship", names)
        self.assertGreaterEqual(p["lvl"]["melee"], 4)       # master + 12 years
        self.assertGreaterEqual(p["lvl"]["magic"], 3)       # fire (level 6)
        self.assertGreaterEqual(p["lvl"]["revive"], 4)      # rank A resurrection
        self.assertIn("water", p["weak"])
        self.assertTrue(any("water" in x.lower() for x in p["lim"]))

    def test_named_technique_is_the_one_used(self):
        p = SK.parse("Master swordsman. Novice healer. Fire magic (level 6)")
        self.assertEqual(SK.pick(p, "I hurl a bolt of fire", "special")["tags"][0], "fire")
        self.assertEqual(SK.pick(p, "I bandage the wound", "heal")["kinds"][0], "heal")

    def test_the_skill_sheet_reaches_the_prompt_only_when_conflict_brews(self):
        from crumble.rp.blocks import rp_blocks
        calm = {"rp": {"on": True, "state": {}, "fx": "", "cfg": {}, "uskills": SKILLS, "ugear": "katana"}, "story": {"info": {"tension": 0}}}
        ctx, fx = rp_blocks(M[0], calm)
        self.assertNotIn("dagger", "\n".join(ctx).lower())
        hot = {"rp": calm["rp"], "story": {"info": {"tension": 2}}}
        ctx, fx = rp_blocks(M[0], hot)
        blob = "\n".join(ctx).lower()
        self.assertIn("dagger", blob)
        self.assertIn("katana", blob)
        self.assertIn("never mention game mechanics", blob)

    def test_no_fight_is_ever_started_by_a_word(self):
        for t in ("*I attack Mira*", "I hit the snooze button and fire up the stove", "*slaps the table and laughs*", "let's fight"):
            r = go(t)
            self.assertFalse((r["rp"] or {}).get("combat"), t)
            self.assertNotIn("Combat", str((r.get("card") or {}).get("title", "")), t)
            self.assertFalse(r["acting"], t)


class BodyTests(unittest.TestCase):
    def test_wounds_persist_and_heal_with_time(self):
        b = B.blank()
        B.add_injury(b, "gash", "left arm", 2)
        B.tick(b, 1)
        self.assertEqual(b["inj"][0]["s"], 2)                 # an hour later it still hurts
        B.tick(b, 24 * 4.5)
        self.assertEqual(b["inj"][0]["s"], 1)                 # days later it has eased
        B.tick(b, 24 * 2)
        self.assertEqual(b["inj"], [])                        # and finally healed

    def test_critical_wound_needs_treatment_and_bleeds_out(self):
        b = B.blank()
        B.add_injury(b, "bleeding", "side", 4)
        self.assertEqual(B.tick(b, .3), [])
        self.assertTrue(B.helpless(b))
        ev = B.tick(b, 1.0)
        self.assertEqual(ev[0]["ev"], "died")
        c = B.blank()
        B.add_injury(c, "bleeding", "side", 4)
        B.treat(c, 2)
        self.assertEqual(B.tick(c, 3), [])                    # tended: no longer bleeding out
        self.assertFalse(c["dead"])

    def test_pain_changes_what_a_body_can_do(self):
        b = B.blank()
        B.add_injury(b, "fracture", "right arm", 3)
        B.add_injury(b, "gash", "left leg", 3)
        p = B.penalty(b)
        self.assertGreaterEqual(p["atk"], 3)
        self.assertGreaterEqual(p["speed"], 3)
        self.assertLess(B.vitality(b), .75)
        self.assertIn("serious", B.guidance(b, "Mira", "Tonoy"))

    def test_time_skips_are_read(self):
        self.assertEqual(B.skip_hours("three days later"), 72)
        self.assertEqual(B.skip_hours("*sleeps through the night*"), 8)
        self.assertEqual(B.skip_hours("*rests for 2 weeks to recover*"), 336)
        self.assertEqual(B.skip_hours("hello"), 0)

    def test_narration_is_read_conservatively(self):
        ev = B.observe("The blade slashes across Mira's left arm, a deep cut.", M, "Tonoy")
        self.assertEqual((ev[0]["what"], ev[0]["id"], ev[0]["sev"]), ("injury", "m", 3))
        self.assertEqual(B.observe("Mira dodges and the sword barely misses her arm.", M, "Tonoy"), [])
        self.assertEqual(B.observe('"I think I\'m dying," Mira whispers.', M, "Tonoy"), [])
        self.assertEqual(B.observe("Mira would die before she let you go.", M, "Tonoy"), [])
        self.assertEqual(B.observe("Mira dies in your arms.", M, "Tonoy")[0]["what"], "death")


class DeathTests(unittest.TestCase):
    def kill_golem(self):
        o = rp_observe(dict(members=M, user="Tonoy", rp={}, text="The katana goes through the Golem and the Golem dies.", turn=3))
        return o["rp"], o

    def test_killing_blow_and_the_dead_stay_dead(self):
        rp, r = self.kill_golem()
        self.assertTrue(B.is_dead(rp, "g"))
        self.assertIn("g", B.dead_ids(rp))
        t = go("I try to persuade the Golem to stand down", rp)   # the dead cannot be talked to or fought
        self.assertEqual(t["acting"], [])
        self.assertIn("dead", t["brief"].lower())

    def test_death_sets_aside_bond_and_mood_until_resurrection(self):
        rp = {"rom": {"m": {"v": 40}}, "rel": {"m": {"v": 30}}}
        B.kill(rp, "m", "was killed", 3, 77, "happy")
        self.assertNotIn("m", rp["rom"])
        self.assertNotIn("m", rp["rel"])
        self.assertEqual(rp["body"]["m"]["stash"]["aff"], 77)
        st = B.revive(rp, "m", 3)
        self.assertEqual((st["aff"], st["mood"]), (77, "happy"))
        self.assertEqual(rp["rom"]["m"]["v"], 40)
        self.assertFalse(rp["body"]["m"]["dead"])
        self.assertTrue(rp["body"]["m"]["inj"])                 # a fresh wreck, not a perfect reset

    def test_resurrection_needs_real_power(self):
        rp = {}
        B.kill(rp, "m", "was killed", 1, 60, "calm")
        weak = rp_resolve(dict(BASE, uskills="Strong swordsman", ugear="katana", text="*I resurrect Mira*", rp=rp))
        self.assertTrue(B.is_dead(weak["rp"], "m"))
        self.assertEqual(weak["revived"], {})
        ok = go("*I resurrect Mira with my resurrection magic*", rp)
        self.assertFalse(B.is_dead(ok["rp"], "m"))
        self.assertIn("m", ok["revived"])
        self.assertGreater(B.get(ok["rp"], "user")["tired"], 0)    # it costs the caster

    def test_author_can_always_bring_someone_back(self):
        rp = {}
        B.kill(rp, "m", "was killed", 1, 60, "calm")
        r = rp_resolve(dict(BASE, uskills="", text="*Mira is brought back from the dead*", rp=rp, forced="revive"))
        self.assertFalse(B.is_dead(r["rp"], "m"))

    def test_wounds_in_the_story_stay_afterwards(self):
        o = rp_observe(dict(members=M, user="Tonoy", rp={}, text="The blade cuts across Mira's right arm, a deep gash.", turn=3))
        self.assertTrue(o["rp"]["body"]["m"]["inj"])
        rest = go("*rests for 8 hours*", o["rp"], forced="rest")
        self.assertIn("Time passes", rest["brief"])

    def test_observe_endpoint_records_and_kills(self):
        o = rp_observe(dict(members=M, user="Tonoy", rp={}, text="Rex staggers. The blade cuts across Mira's right arm, a deep gash. Golem dies.", turn=3))
        self.assertTrue(o["rp"]["body"]["m"]["inj"])
        self.assertEqual(o["deaths"], ["g"])

    def test_the_dead_never_get_a_turn(self):
        h.install(h.FakeLLM(["should never run"]))
        rp = {}
        B.kill(rp, "shy", "was killed", 1, 50, "calm")
        r = generate_reply({"char": h.SHY, "user": "Sam", "history": [{"role": "user", "content": "hello?"}], "state": {},
                            "rp": {"on": True, "state": rp}, "params": {"mode": "story", "think": False, "max_tokens": 100}}, None)
        self.assertTrue(r.get("pass"))
        self.assertTrue(r.get("dead"))


class ChronicleTests(unittest.TestCase):
    MSGS = [{"role": "user", "content": "My name is Tonoy and I live in Dhaka. I promise I'll be at the cafe at 7pm tomorrow."},
            {"role": "assistant", "content": "*smiles* Okay. Mira hands you a silver key to the old library. The weather is nice.", "name": "Mira"},
            {"role": "user", "content": "ok cool"}]

    def test_details_are_kept_verbatim_and_small_talk_is_not(self):
        f = chronicle.extract(self.MSGS, "Tonoy", "Mira", 0)
        text = " ".join(x["t"] for x in f)
        self.assertIn("7pm", text)
        self.assertIn("silver key", text)
        self.assertNotIn("weather is nice", text)
        self.assertTrue(any(x["pin"] and x["k"] == "promise" for x in f))

    def test_only_what_is_relevant_enters_the_prompt_but_pins_always_do(self):
        c = chronicle.blank()
        chronicle.merge(c, chronicle.extract(self.MSGS, "Tonoy", "Mira", 0), 3)
        picked = chronicle.pick(c, "what did I promise about the cafe", 4, 300)
        self.assertTrue(any("7pm" in i["t"] for i in picked))
        self.assertEqual(chronicle.pick(c, "x", 4, 0), [])

    def test_forgetting_after_a_while(self):
        c = chronicle.blank()
        c["items"] = [{"id": "c1", "t": "Tonoy: saw a Red Bird near the Lake.", "k": "detail", "w": 2, "turn": 0, "keys": [], "pin": False, "n": 0, "last": 0},
                      {"id": "c2", "t": "Tonoy: I promise to return.", "k": "promise", "w": 5, "turn": 0, "keys": [], "pin": True, "n": 0, "last": 0},
                      {"id": "c3", "t": "Tonoy: met Old Joe at the Mill.", "k": "detail", "w": 2, "turn": 0, "keys": [], "pin": False, "n": 3, "last": 200}]
        chronicle.decay(c, 220)
        ids = {i["id"] for i in c["items"]}
        self.assertEqual(ids, {"c2", "c3"})                    # small, old and never needed: gone; pinned and recently used: kept

    def test_memory_store_forgets_small_unused_memories(self):
        m = store.ensure({}, "Tonoy", "Mira")
        store.add(m, "episodic", "something minor happened once", imp=.2, turn=0)
        store.add(m, "episodic", "a vow was made on the bridge", imp=.9, turn=0)
        store.decay(m, 300)
        left = [i["text"] for i in m["items"]]
        self.assertEqual(left, ["a vow was made on the bridge"])

    def test_there_is_no_ceiling_and_a_bigger_window_carries_more(self):
        small, big = chronicle.budget(8192, 900), chronicle.budget(32768, 900)
        self.assertEqual(big["room"], 32768 - 900 - 24)              # the whole window is usable
        self.assertGreater(big["room"], 8000)
        self.assertGreater(big["hist"], small["hist"])               # and it is actually used: more chat and more details are carried
        self.assertGreater(big["chron"], small["chron"])
        self.assertLess(big["target"], big["room"])
        self.assertLessEqual(small["hist"], 2600)                    # an 8192 window keeps the plan it was tuned for
        long = [{"role": "user" if i % 2 else "assistant", "content": "word " * 120} for i in range(80)]
        kept, dropped = chronicle.trim_history(long, 1300)
        self.assertGreaterEqual(len(kept), 3)
        self.assertEqual(len(kept) + len(dropped), 80)
        self.assertLess(sum(len(m["content"]) // 3 for m in kept), 1700)

    def test_update_reads_each_message_once_and_survives_rewinds(self):
        st = {}
        chronicle.update(st, self.MSGS, "Tonoy", "Mira", 3)
        n = len(st["chron"]["items"])
        chronicle.update(st, self.MSGS, "Tonoy", "Mira", 3)
        self.assertEqual(len(st["chron"]["items"]), n)
        chronicle.update(st, self.MSGS[:1], "Tonoy", "Mira", 1)       # rewound to the first message
        self.assertTrue(all(i["turn"] < 1 for i in st["chron"]["items"]))

    def test_a_long_chat_stays_inside_the_window_and_keeps_its_details(self):
        h.install(h.FakeLLM(["Okay."] * 6))
        hist = []
        for i in range(120):
            hist.append({"role": "user", "content": f"Message {i}: I promise to bring {i + 3} apples to the Old Mill on Friday. " + "filler " * 60})
            hist.append({"role": "assistant", "content": "*nods* " + "reply " * 70, "name": "Mira"})
        hist.append({"role": "user", "content": "do you remember my promise about apples?"})
        st = {"chron": chronicle.blank()}
        chronicle.merge(st["chron"], chronicle.extract(hist[:20], "Sam", "Mira", 0), 20)
        r = generate_reply({"char": h.SHY, "user": "Sam", "history": hist, "state": st, "turn": len(hist),
                            "params": {"mode": "story", "think": False, "max_tokens": 300}}, None)
        self.assertLessEqual(r["ctx_used"] + 300, r["ctx"])
        self.assertTrue(r["dropped"] > 0)
        self.assertTrue(r["chron_add"] is not None)


if __name__ == "__main__":
    unittest.main()
