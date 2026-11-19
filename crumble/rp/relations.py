"""Relationship paths. Romance is one way two people can grow close; friendship, partnership, mentorship (master and
disciple), rivalry and family are others. Every path climbs the same six-step ladder, so progress looks the same
on the page, but each path has its own stage names, its own colour and its own guidance for the character.

    effective(c, rel)            the path that really applies ('auto' | 'romance' | another path)
    stage_idx(v) / stage_label   where a progress value (0-100) sits on the ladder
    rel_block(c, rel, CH, US)    the prompt block for the non-romantic paths ('' for auto and romance, which have their own)
    decline(...)                 a romantic gesture that does not fit the chosen path: no dice, a gentle in-character answer
    public()                     everything the page needs to draw the paths (served with the app state)
    adult(c)                     False when the sheet states an age under 18: romance never applies to them
"""
import re

CUTS = (10, 25, 45, 65, 85, 101)       # upper bound of each of the six stages; the same ladder for every path
_MINOR = re.compile(r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen)\b(?!\s+(?:hundred|thousand))|"
                    r"\b(?:minor|child|kid|teen\w*|underage)\b")


def adult(c):
    """False only when the sheet says the character is under 18. Romance and intimacy never apply to them."""
    age = str((c or {}).get("age") or "").lower()
    m = re.search(r"\d+", age)
    if m:
        return int(m.group()) >= 18
    return not _MINOR.search(age)


def _p(label, icon, color, blurb, stages, phrases, guide):
    return {"label": label, "icon": icon, "color": color, "blurb": blurb, "stages": stages, "phrases": phrases, "guide": guide}


RELS = {
    "auto": _p("Getting to know each other", "🌱", "#b9a99b", "No path chosen yet. It can grow into any of these.",
               ["Strangers", "Acquaintances", "Familiar", "Comfortable", "Close", "Bonded"],
               ["are strangers", "are acquaintances", "are getting familiar with each other", "are comfortable together", "are close", "share a deep bond"], ""),
    "friend": _p("Friendship", "🤝", "#58b4e8", "Trust, humour and loyalty without romance.",
                 ["Acquaintances", "Friendly", "Friends", "Close friends", "Best friends", "Inseparable"],
                 ["barely know each other", "are friendly acquaintances", "are friends", "are close friends", "are best friends", "are inseparable, ride-or-die friends"],
                 "They are friends, and it stays platonic. Show it through easy humour, inside jokes, honesty, loyalty, remembering small things, "
                 "checking in and teasing that never wounds. The affection is warm, never romantic."),
    "romance": _p("Romance", "💞", "#ef6f93", "Feelings that deepen from a spark into love.",
                  ["No spark", "Curious", "Flirty", "Smitten", "In love", "Devoted"],
                  ["feel no romantic spark yet", "are curious about each other", "are attracted and flirty", "are smitten and romantic", "are in love, a couple", "are deeply committed"], ""),
    "partner": _p("Partners", "⚔️", "#f0a23c", "Allies and teammates who rely on each other.",
                  ["Contacts", "Associates", "Collaborators", "Allies", "Trusted partners", "One team"],
                  ["are barely in contact", "are associates", "work well together", "are reliable allies", "are trusted partners who cover each other", "move as one team"],
                  "They are partners: allies working toward shared goals. Show it through coordination, splitting the work, covering each other, "
                  "useful honesty, respect for each other's skill, and trust that grows with every risk they share. It is comradely, not romantic."),
    "mentor": _p("Master & disciple", "🎓", "#a78bfa", "One guides, the other learns, and trust grows with every lesson.",
                 ["Strangers", "Prospect", "Novice", "Apprentice", "Disciple", "Heir"],
                 ["are strangers", "are testing whether the teaching bond is worth forming", "have just begun as master and student", "are master and apprentice",
                  "are master and devoted disciple", "are master and chosen heir, bound by deep trust"], ""),
    "rival": _p("Rivalry", "⚡", "#f06a5a", "Competition that sharpens both of them and turns into respect.",
                ["Strangers", "Wary", "Rivals", "Fierce rivals", "Respected rivals", "Worthy adversaries"],
                ["are strangers", "are wary of each other", "are rivals", "are fierce rivals", "are rivals who respect each other", "are worthy adversaries who know each other better than anyone"],
                "They are rivals. Show it through competition, sharp banter, pride, challenges and a refusal to let the other win easily. "
                "As the bond deepens, grudging respect appears and the rivalry becomes a bond of its own, without losing its edge. It is not romantic."),
    "family": _p("Family", "🏠", "#7fcf8a", "Kin by blood or by choice.",
                 ["Strangers", "Familiar", "Kindred", "Family", "Close family", "Unbreakable"],
                 ["are strangers", "are growing familiar", "feel like kin", "are family", "are close family", "share an unbreakable family bond"],
                 "They are family, by blood or by choice. Show it through shared history, familiar habits, bickering that never threatens the bond, "
                 "protectiveness, honesty and loyalty. It is familial, never romantic."),
}
MENTOR_GUIDE = {
    "master": "{CH} is {US}'s master (teacher), and {US} is {CH}'s disciple. {CH} guides, tests, corrects and encourages {US}: standards are high, praise is earned, "
              "lessons grow deeper and more personal as trust grows, and {CH} slowly shares their own doubts and secrets. Respect flows both ways. It is a teaching bond, not romantic.",
    "disciple": "{CH} is {US}'s disciple (student), and {US} is {CH}'s master. {CH} listens, practises, asks questions, seeks approval, makes mistakes and grows in "
                "confidence and skill as the bond deepens, and shows loyalty and gratitude in their own way. It is a teaching bond, not romantic.",
}
ROLES = {"mentor": [["master", "{name} is the master"], ["disciple", "{name} is the disciple"]]}


def stage_idx(v):
    v = max(0, min(100, float(v or 0)))
    return next(i for i, t in enumerate(CUTS) if v < t)


def kind_of(rel):
    t = str((rel or {}).get("type") or "auto")
    return t if t in RELS else "auto"


def effective(c, rel):
    """The path that applies. A character whose sheet says they are under 18 never gets 'auto' or 'romance': they get friendship."""
    t = kind_of(rel)
    return "friend" if (t in ("auto", "romance") and not adult(c)) else t


def stage_label(t, v):
    return RELS[t]["stages"][stage_idx(v)]


def stage_phrase(t, v):
    return RELS[t]["phrases"][stage_idx(v)]


def rel_block(c, rel, CH, US):
    """Prompt block for a non-romantic path. '' for auto and romance (their blocks live in blocks.py)."""
    rel = rel or {}
    t = effective(c, rel)
    if t in ("auto", "romance"):
        return ""
    R, v = RELS[t], rel.get("v", 0)
    guide = MENTOR_GUIDE["disciple" if rel.get("role") == "disciple" else "master"] if t == "mentor" else R["guide"]
    s = f"[Relationship with {US}]\n{CH} and {US} are linked as: {R['label']}. Right now they {stage_phrase(t, v)}.\n" + guide.replace("{CH}", CH).replace("{US}", US)
    ms = [str(x) for x in (rel.get("ms") or [])][-6:]
    if ms:
        s += "\nShared moments: " + "; ".join(ms) + "."
    return (s + f"\nLet this stage decide how much trust, openness, humour and effort {CH} gives {US}. It changes only through what really happens between them: "
            "never rush it, never mention numbers or stages, and never make it romantic or sexual unless the author changes the relationship.")


def decline(act, c, rp, user, out, t):
    """A romantic gesture toward someone whose relationship with the user is not romantic: no dice, a kind answer in character."""
    from .actions import LAB
    nm, R = c.get("name") or "They", RELS[t]
    v = ((rp.get("rel") or {}).get(c["id"]) or {}).get("v", 0)
    out["acting"] = [c["id"]]
    out["brief"] = (f"[Relationship note] {user} tries to {LAB[act][0].lower()} with {nm}, but what they share is {R['label'].lower()} and {nm} does not feel it as romance. "
                    f"{nm} answers kindly and in character: laughs it off, gently deflects or says so plainly, and keeps the warmth of what they really are to each other. "
                    "No hostility, no dice.")
    out["card"] = {"type": act, "title": LAB[act][0] + " · " + R["label"],
                   "rows": [{"who": f"{user} → {nm}", "res": "Not that kind of bond", "tier": "part", "ex": f"{R['icon']} {stage_label(t, v)}"}], "note": ""}


def public():
    return {k: {"label": v["label"], "icon": v["icon"], "color": v["color"], "blurb": v["blurb"], "stages": v["stages"], "roles": ROLES.get(k)}
            for k, v in RELS.items()}
