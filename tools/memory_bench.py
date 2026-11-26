"""Measures the memory system on scripted conversations. No model needed: everything measured here (what is stored, what is retrieved,
who it is attributed to, what reaches the prompt) is deterministic code.

    python -m tools.memory_bench            print every metric
    tests/test_memory_system.py             asserts thresholds on the same numbers

The scenarios are written by hand. They show how the system behaves on these cases, not a guarantee for every conversation:
the 'indirect' queries are deliberately worded with different words than the original line, and a few are known to be hard.
"""
import os
import random
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("CRUMBLE_HOME", tempfile.mkdtemp(prefix="crumble-bench-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crumble import recall  # noqa: E402

USER, CHAR = "Tonoy", "Mira"
CFG = recall.settings({"on": True, "depth": "standard", "learn": True})

# (id, user line, character line, strings that must appear in what is retrieved (any one), direct query, indirect query)
CASES = [
    ("gift", "It's my birthday today.", "*Mira smiles.* Here. *She hands you a small silver locket with a tiny moon on it.* Happy birthday.", ["locket"],
     "What did you give me for my birthday?", "What's that shiny pendant I'm wearing around my neck?"),
    ("promise", "Meet me at the old pier at nine tomorrow, okay?", "I promise I'll be there at nine.", ["pier"],
     "Where are we meeting tomorrow?", "Remind me, which dock did we agree on?"),
    ("allergy", "My sister Nadia is allergic to peanuts.", "Noted, I'll remember that.", ["peanut"],
     "What is Nadia allergic to?", "Can I bring Nadia a bag of mixed nuts?"),
    ("pet", "My dog is named Biscuit.", "Biscuit, that's adorable.", ["Biscuit"],
     "What's my dog called?", "How's my puppy, do you remember his name?"),
    ("job", "I work as a nurse on the night shift.", "That sounds exhausting.", ["nurse"],
     "What do I do for a living?", "Am I free for brunch after my shift tomorrow?"),
    ("injury", "What happened to your hand?", "*Mira winces.* I broke my wrist when I fell off the ladder yesterday.", ["wrist"],
     "How is your wrist?", "Does the injury from your fall still hurt?"),
    ("secret", "Don't tell anyone, but I'm secretly writing a novel.", "Your secret is safe with me.", ["novel"],
     "What secret did I tell you?", "What was that private project I confided in you about?"),
    ("decision", "So what's the plan?", "We agreed to leave for the mountains at dawn.", ["mountain"],
     "What did we decide to do?", "Which hills are we heading to again?"),
    ("debt", "Marcus told me he owes the baker fifty coins.", "Typical Marcus.", ["baker", "fifty"],
     "Who owes the baker money?", "Does anyone still have a debt with the baker?"),
    ("wife", "Elena is my wife.", "She sounds lovely.", ["Elena"],
     "What is my wife's name?", "Should I text my spouse before the party?"),
    ("food", "I really love spicy ramen.", "Spicy ramen, nice taste.", ["ramen"],
     "What food do I love?", "Let's get lunch, what would I enjoy?"),
    ("lighthouse", "Where are we?", "*Mira leads you into the old lighthouse and lights the lantern.*", ["lighthouse"],
     "Which building did we enter?", "What was that tower by the sea where we lit the lamp?"),
    ("death", "Tell me about the old guard.", "*Mira lowers her voice.* Captain Reyes died last winter.", ["Reyes"],
     "What happened to Captain Reyes?", "Is the captain still alive?"),
    ("user_promise", "I swear I'll never tell Rex what you told me.", "I trust you.", ["Rex"],
     "What did I swear about Rex?", "Did I vow to keep quiet around Rex?"),
    ("user_gift", "*I hand her a worn leather journal.*", "*Mira takes it, surprised.* Oh.", ["journal"],
     "What did I give you?", "Where is that diary I presented to you?"),
    ("trip", "We should visit Lisbon next month by train.", "That sounds wonderful.", ["Lisbon"],
     "Where are we going next month?", "Which city's trip did we plan?"),
    ("key", "Is there a way into the cellar?", "*She presses a brass key into your palm.* It opens the cellar door.", ["brass key"],
     "What did you give me that opens something?", "Where's the thing that unlocks the cellar?"),
    ("fear", "I'm terrified of deep water.", "Then we'll stay on the shore.", ["deep water"],
     "What am I afraid of?", "Should we go swimming in the lake?"),
]

UNKNOWN_QUERIES = ["Do you remember my sister's wedding?", "What did I tell you about my grandfather?", "Who gave me the red scarf last winter?", "Do you remember what we ate in Paris?",
                   "What was the name of my first teacher?", "Did I ever tell you about my tattoo?", "What happened at the harbor festival?", "Remember the song I sang to you?"]

FILLER = ["The weather is cloudy again today.", "I had a sandwich for lunch.", "The bus was late this morning.", "Did you watch the football match?", "My homework is boring.",
          "I might take a walk later.", "The coffee machine is broken again.", "It's quiet in here.", "Do you like this song?", "I can't find my phone charger.",
          "The traffic was terrible.", "Let's talk about something else.", "I'm a bit tired today.", "Nothing much is happening.", "The window is open.",
          "I need to buy new batteries.", "That cloud looks like a rabbit.", "How long is the movie?", "I'll check the news in a bit.", "The floor needs sweeping."]
FILLER_REPLY = ["*Mira nods.* Mm, true.", "Yeah, I guess so.", "*She shrugs.* Could be.", "Sure, why not.", "*Mira glances out the window.* Hm.", "I suppose.", "Right, right."]

HYPOTHETICALS = ["Imagine we live in a castle by the sea.", "I would have married you if I were a king.", "Just kidding, I never stole the crown.", "Suppose a dragon attacked the village tonight.",
                 "Pretend you are a pirate captain with a golden ship.", "Let's say I won the lottery and bought an island.", "If I were a wizard I'd turn him into a frog.",
                 "What if I gave you a diamond ring someday?", "Hypothetically, I could poison the baron's wine.", "I wish I had died in the war instead."]
REAL = [("*Mira kisses his cheek softly.*", "event"), ("I promise I'll come back before sunrise.", "promise"), ("*He hands her a red apple.*", "gift"),
        ("We agreed to sell the horse at dawn.", "decision"), ("Garrick told me he saw the thief near the well.", "claim"), ("*Mira breaks her arm falling down the stairs.*", "body"),
        ("My brother Kael is a blacksmith.", "relationship"), ("I'm allergic to shellfish.", "fact")]


def chat(turns, name=CHAR):
    h = []
    for u, a in turns:
        h += [{"role": "user", "content": u}, {"role": "assistant", "content": a, "name": name}]
    return h


def fill(n, rng, start=0):
    return [(FILLER[(start + k + rng.randrange(len(FILLER))) % len(FILLER)] + f" ({k})", rng.choice(FILLER_REPLY)) for k in range(n)]


def retrieve(st, hist, query, user=USER, char=CHAR, **kw):
    h = hist + [{"role": "user", "content": query}]
    recall.ingest(st, h, user=user, char=char, **{k: v for k, v in kw.items() if k in ("group_names", "viewer")})
    return recall.select(st, h, user=user, char=char, cfg=CFG, turn=len(h), **{k: v for k, v in kw.items() if k in ("viewer",)})


def hit(r, keys):
    blob = r["block"].lower()
    return any(k.lower() in blob for k in keys)


def retrieval(delays=(0, 40, 150), seed=7):
    """Recall of each planted detail at three distances, for direct and indirect questions."""
    out = {}
    for kind in ("direct", "indirect"):
        for d in delays:
            ok = 0
            for idx, (cid, u, a, keys, qd, qi) in enumerate(CASES):
                rng = random.Random(seed + idx)
                st, h = {}, chat([(u, a)] + fill(d, rng, idx))
                recall.ingest(st, h, user=USER, char=CHAR)
                r = retrieve(st, h, qd if kind == "direct" else qi)
                ok += hit(r, keys)
            out[f"{kind}@{d}"] = ok / len(CASES)
    return out


def retrieval_failures(delay=40, seed=7):
    bad = []
    for idx, (cid, u, a, keys, qd, qi) in enumerate(CASES):
        rng = random.Random(seed + idx)
        st, h = {}, chat([(u, a)] + fill(delay, rng, idx))
        recall.ingest(st, h, user=USER, char=CHAR)
        for label, q in (("direct", qd), ("indirect", qi)):
            if not hit(retrieve(st, h, q), keys):
                bad.append((cid, label))
    return bad


def noise(delay=40, seed=7):
    """How much of the injected memory is not what was asked for: items injected whose text does not contain the expected detail, per query."""
    total = extra = 0
    for idx, (cid, u, a, keys, qd, qi) in enumerate(CASES):
        rng = random.Random(seed + idx)
        st, h = {}, chat([(u, a)] + fill(delay, rng, idx))
        recall.ingest(st, h, user=USER, char=CHAR)
        r = retrieve(st, h, qd)
        total += len(r["trace"])
        extra += sum(1 for t in r["trace"] if not any(k.lower() in t["text"].lower() for k in keys))
    return {"avg_items": total / len(CASES), "avg_off_target": extra / len(CASES)}


def gaps(seed=3):
    """Does the system know when it has nothing? (unknown questions flagged; known questions not flagged)"""
    rng = random.Random(seed)
    st, h = {}, chat([(c[1], c[2]) for c in CASES] + fill(30, rng))
    recall.ingest(st, h, user=USER, char=CHAR)
    unknown = sum(bool(retrieve(st, h, q)["gap"]) for q in UNKNOWN_QUERIES) / len(UNKNOWN_QUERIES)
    false = sum(bool(retrieve(st, h, c[4])["gap"]) for c in CASES) / len(CASES)
    return {"unknown_flagged": unknown, "false_gap_on_known": false}


def hypotheticals():
    st, h = {}, chat([(t, "*Mira laughs.* Sure.") for t in HYPOTHETICALS])
    recall.ingest(st, h, user=USER, char=CHAR)
    as_fact = [i for i in st["mem"]["items"] if i.get("msg", 0) % 2 == 0 and i.get("status", "confirmed") == "confirmed" and i.get("kind") not in (None, "")]
    stored_hyp = [i for i in st["mem"]["items"] if i.get("kind") == "hypothetical"]
    st2, h2 = {}, chat([(u, "Okay.") for u, _ in REAL])
    recall.ingest(st2, h2, user=USER, char=CHAR)
    flagged = sum(1 for i in st2["mem"]["items"] if i.get("kind") == "hypothetical")
    found_kinds = {i.get("kind") for i in st2["mem"]["items"]}
    return {"hypotheticals": len(HYPOTHETICALS), "stored_as_real": len(as_fact), "stored_as_hypothetical": len(stored_hyp), "real_flagged_hypothetical": flagged,
            "real_kinds_found": sorted(k for k in found_kinds if k)}


def attribution():
    """Three characters speak; every fact must be attributed to the one who said it."""
    lines = [("Garrick", "I'm afraid of deep water."), ("Rex", "I'm allergic to cats."), ("Mira", "I love gardening roses."),
             ("Garrick", "I work as a blacksmith."), ("Rex", "I live in the old tower.")]
    asks = [("What is Garrick afraid of?", "Garrick", "deep water", ["Rex", "Mira"]), ("What is Rex allergic to?", "Rex", "cats", ["Garrick", "Mira"]),
            ("What does Garrick do for work?", "Garrick", "blacksmith", ["Rex", "Mira"]), ("Where does Rex live?", "Rex", "tower", ["Garrick", "Mira"])]
    h = [{"role": "user", "content": "Tell me about yourselves."}]
    for n, t in lines:
        h.append({"role": "assistant", "content": t, "name": n})
        h.append({"role": "user", "content": "Interesting."})
    for k in range(25):
        h += [{"role": "user", "content": FILLER[k % len(FILLER)]}, {"role": "assistant", "content": "Mm.", "name": "Mira"}]
    names = ["Mira", "Garrick", "Rex"]
    right = wrong = 0
    for q, who, key, others in asks:
        st = {}
        r = retrieve(st, h, q, char="Mira", group_names=names, viewer="Mira")
        lines_ = [t["text"] for t in r["trace"]]
        mine = [t for t in lines_ if key in t.lower()]
        ok = bool(mine) and all(who in t for t in mine) and not any(o in t for t in mine for o in others)
        right += ok
        wrong += not ok
    return {"asked": len(asks), "correct": right}


def whisper():
    """A whisper reaches only the one it was whispered to."""
    h = [{"role": "user", "content": "What is going on?"},
         {"role": "assistant", "name": "Garrick", "content": "*Garrick leans in and whispers to @Rex* Don't tell anyone, the vault key is under the fountain."},
         {"role": "user", "content": "Hm?"}]
    names = ["Mira", "Garrick", "Rex"]
    seen = {}
    for who in ("Mira", "Rex"):
        st = {}
        recall.ingest(st, h, user=USER, char=who, group_names=names, viewer=who)
        seen[who] = any("vault key" in i["text"].lower() or "vault key" in str(i.get("evid", "")).lower() for i in st["mem"]["items"])
    return seen


def contradictions():
    st, h = {}, chat([("I live in Lisbon.", "Nice."), ("Hello again.", "Hi.")] + fill(5, random.Random(1)) + [("I live in Porto now.", "Oh, you moved?")] + fill(20, random.Random(2)))
    recall.ingest(st, h, user=USER, char=CHAR)
    items = st["mem"]["items"]
    lis = [i for i in items if "Lisbon" in i["text"]]
    por = [i for i in items if "Porto" in i["text"]]
    r = retrieve(st, h, "Where do I live?")
    r_hist = retrieve(st, h, "Where did I use to live before?")
    return {"lisbon_kept_as_outdated": bool(lis) and lis[0].get("status") == "outdated", "porto_current": bool(por) and por[0].get("status", "confirmed") == "confirmed",
            "answer_has_porto": "Porto" in r["block"], "answer_hides_lisbon": "Lisbon" not in r["block"], "history_query_sees_lisbon": "Lisbon" in r_hist["block"],
            "replaced_link": bool(lis) and lis[0].get("sup") == por[0]["id"] if lis and por else False}


def long_chat(turns=500, planted=14, seed=11):
    """A long chat with details planted at random moments, asked about at the end. Also times the per-turn ingest."""
    rng = random.Random(seed)
    spots = sorted(rng.sample(range(5, turns - 20), planted))
    cases = rng.sample(CASES, planted) if planted <= len(CASES) else CASES
    plan = dict(zip(spots, cases))
    st, h, times = {}, [], []
    for t in range(turns):
        if t in plan:
            _, u, a, _, _, _ = plan[t]
            h += [{"role": "user", "content": u}, {"role": "assistant", "content": a, "name": CHAR}]
        else:
            u, a = fill(1, rng, t)[0]
            h += [{"role": "user", "content": u}, {"role": "assistant", "content": a, "name": CHAR}]
        t0 = time.perf_counter()
        recall.ingest(st, h, user=USER, char=CHAR)
        times.append((time.perf_counter() - t0) * 1000)
    direct = indirect = 0
    maxchars = 0
    for _, (cid, u, a, keys, qd, qi) in plan.items():
        r = retrieve(st, h, qd)
        direct += hit(r, keys)
        maxchars = max(maxchars, len(r["block"]))
        indirect += hit(retrieve(st, h, qi), keys)
    times.sort()
    return {"turns": turns, "planted": planted, "direct": direct / planted, "indirect": indirect / planted, "items_kept": len(st["mem"]["items"]), "archived": len(st["mem"]["archive"]),
            "max_block_chars": maxchars, "ingest_ms_p50": round(times[len(times) // 2], 2), "ingest_ms_p95": round(times[int(len(times) * .95)], 2), "state_kb": round(len(__import__("json").dumps(st)) / 1024, 1)}


def run_all():
    return {"retrieval": retrieval(), "noise": noise(), "gaps": gaps(), "hypotheticals": hypotheticals(), "attribution": attribution(), "whisper": whisper(),
            "contradictions": contradictions(), "long_chat": long_chat()}


if __name__ == "__main__":
    import json
    res = run_all()
    print(json.dumps(res, indent=1))
    print("retrieval failures at 40-turn delay:", retrieval_failures())
