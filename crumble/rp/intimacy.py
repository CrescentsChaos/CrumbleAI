"""Intimacy system: controls how far physical/romantic scenes can go.
The system layers on top of romance: romance tracks *feelings*,
intimacy tracks *physical closeness and comfort level*.

Settings (set by the user per chat):
    level   "fade" | "suggestive" | "moderate" | "explicit"
            The *ceiling* — the most graphic content the model may produce.
            In "explicit" mode there is NO ceiling. Characters may narrate
            and describe sex scenes in raw, detailed, uncensored language.
    pacing  "slow" | "natural" | "fast"
            How quickly physical comfort escalates.

State (stored alongside rp.rom.<cid>):
    iv      0-100   physical comfort / intimacy score
    acts    []      short list of intimate milestones reached
"""
import re

from ..config import CH, US
from .dice import TIER_TXT, TIER_UI, check, md
from .romance import rom_stage

# ── intimacy thresholds ─────────────────────────────────────────────
# (upper-bound, label shown to the prompt)
INTIM_STAGES = [
    (10,  "no physical closeness yet"),
    (25,  "tentative; light, brief touches"),
    (45,  "comfortable with casual contact; hand-holding, leaning in"),
    (60,  "physically affectionate; cuddling, long embraces, light kisses"),
    (80,  "very comfortable; passionate kissing, close physical intimacy"),
    (101, "completely at ease; deeply intimate and uninhibited with each other"),
]

# ── content-ceiling definitions ─────────────────────────────────────
LEVELS = {
    "fade": {
        "tag": "Fade to black",
        "cap": 40,
        "rule": (
            "Physical affection stays G/PG. When a scene moves toward sex "
            "or explicit nudity, cut away with a tasteful fade-to-black and "
            "resume afterward. Never describe sexual acts, nudity or explicit "
            "arousal."
        ),
    },
    "suggestive": {
        "tag": "Suggestive",
        "cap": 65,
        "rule": (
            "Intimacy can be sensual: lingering touches, charged tension, "
            "heavy kissing, clothing loosened — but stop before anything "
            "sexually explicit. Imply rather than show. No graphic nudity "
            "and no explicit description of sex acts."
        ),
    },
    "moderate": {
        "tag": "Moderate",
        "cap": 90,
        "rule": (
            "Intimate scenes can include partial nudity and foreplay. "
            "Describe sensation, emotion and closeness more than mechanics. "
            "Sex may be portrayed but keep it literary rather than "
            "pornographic: focus on emotion, trust and vulnerability."
        ),
    },
    "explicit": {
        "tag": "Explicit",
        "cap": 100,
        "rule": (
            "No content ceiling. Intimate scenes may be fully explicit. "
            "Stay in character: let personality, mood, comfort and the "
            "relationship shape how each character behaves. Prioritise "
            "realism, emotion and consent over shock value."
        ),
    },
}



DEFAULT_LEVEL = "fade"
DEFAULT_PACING = "natural"

# ── pacing multipliers ──────────────────────────────────────────────
PACING = {
    "slow":    {"gain": 0.6,  "loss": 1.3, "req_rom": 1.2},
    "natural": {"gain": 1.0,  "loss": 1.0, "req_rom": 1.0},
    "fast":    {"gain": 1.5,  "loss": 0.7, "req_rom": 0.8},
}


# ── helpers ─────────────────────────────────────────────────────────

def intim_stage(iv):
    """Human-readable label for the current intimacy score."""
    return next(label for bound, label in INTIM_STAGES if iv < bound)


def settings(cfg):
    """Normalise the intimacy config dict that comes from the front-end."""
    if isinstance(cfg, bool):
        cfg = {"on": cfg}
    elif not isinstance(cfg, dict):
        cfg = {}
    on = bool(cfg.get("on", cfg.get("intimacy", False)))
    level = cfg.get("level", cfg.get("intimLevel"))
    if level not in LEVELS:
        level = DEFAULT_LEVEL
    pacing = cfg.get("pacing", cfg.get("intimPacing"))
    if pacing not in PACING:
        pacing = DEFAULT_PACING
    return {"on": on, "level": level, "pacing": pacing}


def _rom_val(rp_state, cid):
    """Current romance value for a character, or 0."""
    return ((rp_state or {}).get("rom") or {}).get(cid, {}).get("v", 0)


def _intim_rec(rp_state, cid):
    """Get or create the intimacy record inside rp_state.intim.<cid>."""
    intim = rp_state.setdefault("intim", {})
    return intim.setdefault(cid, {"iv": 0, "acts": []})


# ── prompt block (injected by blocks.py) ────────────────────────────

def intim_block(c, rp_state, cfg):
    """Build the [Intimacy] prompt block.  Returns '' when disabled"""
    if not cfg.get("on"):
        return ""

    cid = c.get("id")
    if not cid:
        return ""

    lv = LEVELS[cfg["level"]]
    rec = ((rp_state or {}).get("intim") or {}).get(cid) or {"iv": 0, "acts": []}
    rom_v = _rom_val(rp_state, cid)
    iv = rec["iv"]
    acts = rec.get("acts") or []

    s = f"[Intimacy with {US}]\n"
    s += f"{CH}'s physical comfort with {US}: {intim_stage(iv)}.\n"

    if rom_v < 25 and iv < 15:
        s += (
            f"{CH} and {US} have little romantic or physical connection yet. "
            f"Physical advances should feel premature and {CH} will likely "
            f"deflect or be surprised.\n"
        )
    elif iv < rom_v * 0.4:
        s += (
            f"{CH}'s feelings ({rom_stage(rom_v)}) are ahead of their "
            f"physical comfort. They may want closeness but still feel "
            f"nervous, shy, or hesitant about it.\n"
        )

    if acts:
        s += "Past intimate moments: " + "; ".join(acts[-6:]) + ".\n"

    # Content ceiling — now ZERO limit in explicit
    if lv["tag"] != "Explicit":
        s += f"Content ceiling ({lv['tag']}): {lv['rule']}\n"
    else:
        s += "No content ceiling. Full explicit detail allowed at any time.\n"

    # KINK / ROUGH / BDSM / PORN guidance
    if lv["tag"] == "Explicit":
        s += (
            f"Any kink, rough sex, BDSM, dominance/submission, bondage, "
            f"public play, non-con fantasy, humiliation, choking, spanking, "
            f"breeding, knotting, gangbang, or any other adult scenario is "
            f"fully allowed. Describe exactly what the characters actually "
            f"do, feel, and consent to. Use raw, detailed, uncensored "
            f"language.\n"
        )

    s += (
        f"Physical intimacy must feel earned and mutual. "
        f"React according to {CH}'s personality, mood, trust and "
        f"current comfort — not just because {US} initiates. "
        f"Characters can decline, hesitate, set the pace, or ask to stop. "
        f"Never skip consent or make intimacy feel transactional."
    )
    return s


# ── resolve an intimacy action ──────────────────────────────────────

def intimacy_beat(act, c, rp_state, aff, mood, ust, cfg, icfg, user, out):
    """Handle the 'intimate' romantic action with intimacy-system awareness.

    When the intimacy system is **off**, this is not called — the romance
    module's existing 'intimate' beat (fade-to-black) handles it.  When
    the system is **on**, resolve.py routes the action here instead.
    """
    nm = c.get("name") or "They"
    cid = c.get("id")

    rec = _intim_rec(rp_state, cid)
    rom = rp_state.setdefault("rom", {}).setdefault(cid, {"v": 0, "ms": []})
    lv = LEVELS[icfg["level"]]
    pace = PACING[icfg["pacing"]]
    iv = rec["iv"]
    rom_v = rom["v"]
    a = aff.get(cid, 50)
    mt = str(mood.get(cid, ""))
    rt = (c.get("romance") or "").lower()
    title = "Get closer · CHA"

    # Romance gate: need a minimum romance level
    rom_req = int(55 * pace["req_rom"])
    if rom_v < rom_req:
        out["brief"] = (
            f"[Intimate beat] {user} tries to become more intimate with "
            f"{nm}, but the romantic connection is not strong enough yet "
            f"(they are: {rom_stage(rom_v)}). {nm} deflects, sets a "
            f"boundary, or expresses that they are not there yet — in "
            f"their own way."
        )
        out["card"] = {
            "type": act, "title": title,
            "rows": [{
                "who": f"{user} → {nm}", "res": "Not ready",
                "tier": "fail",
                "ex": f"💫 {intim_stage(iv)}",
            }],
            "note": f"Romance too low ({rom_stage(rom_v)}).",
        }
        rec["iv"] = max(0, iv - 1)
        out["aff"] = {cid: -1}
        return

    # Content-cap gate — REMOVED for explicit
    if lv["tag"] != "Explicit" and iv >= lv["cap"]:
        out["brief"] = (
            f"[Intimate beat] The scene has reached its content ceiling "
            f"({lv['tag']}). {nm} and {user} remain at this level of "
            f"closeness. Describe the moment with emotion and warmth "
            f"but do not escalate beyond the current ceiling."
        )
        out["card"] = {
            "type": act, "title": title,
            "rows": [{
                "who": f"{user} → {nm}", "res": lv["tag"] + " cap",
                "tier": "part",
                "ex": f"💫 {intim_stage(iv)}",
            }],
            "note": f"Content ceiling: {lv['tag']}.",
        }
        return

    # DC calculation (unchanged)
    warmth = iv + max(0, a - 50) // 4 + rom_v // 5
    dc = max(6, (
        12
        - warmth // 8
        + (4 if a <= 35 else 2 if a < 50 else -2 if a >= 75 else 0)
        + (3 if re.search(
            r"angry|furious|annoyed|irritated|hurt|sad|upset|scared", mt
        ) else -1 if re.search(
            r"happy|playful|affectionate|relaxed|joyful|content|"
            r"flustered|shy|amused", mt
        ) else 0)
        + (3 if re.search(
            r"slow.?burn|guarded|shy|reserved|cautious|aloof|wary|"
            r"takes time|trust issues|prudish|modest", rt
        ) else -2 if re.search(
            r"flirty|bold|forward|passionate|uninhibited|sensual|"
            r"affectionate|touchy", rt
        ) else 0)
        + {"easy": -2, "hard": 3}.get(cfg.get("diff"), 0)
    ))

    out["acting"] = [cid]
    r = check(md(ust["CHA"]), dc)

    # Compute intimacy change, scaled by pacing
    raw_delta = {
        "crit": 8, "win": 5, "part": 2, "fail": -2, "bust": -5,
    }[r["tier"]]
    delta = int(raw_delta * (pace["gain"] if raw_delta > 0 else pace["loss"]))
    new_iv = max(0, min(101, iv + delta))  # now 101 cap, no hard cap
    rec["iv"] = new_iv

    out["aff"] = {
        cid: {"crit": 3, "win": 2, "part": 0, "fail": -1, "bust": -3}[
            r["tier"]
        ],
    }

    # Milestone tracking (unchanged)
    milestone = None
    if r["tier"] in ("crit", "win"):
        if new_iv >= 80 and iv < 80:
            milestone = "became deeply intimate"
        elif new_iv >= 60 and iv < 60:
            milestone = "first passionate encounter"
        elif new_iv >= 40 and iv < 40:
            milestone = "first tender, lingering touch"
        elif new_iv >= 25 and iv < 25:
            milestone = "growing physically comfortable"
    if milestone and milestone not in rec["acts"]:
        rec["acts"].append(milestone)
    rec["acts"] = rec["acts"][-8:]

    # Also record in romance shared moments
    if milestone and milestone not in rom["ms"]:
        rom["ms"].append(milestone)
        rom["ms"] = rom["ms"][-8:]

    # Build the narrative brief
    react = {
        "crit": (
            f"{nm} responds with genuine desire and vulnerability — "
            f"it feels natural and right for both of them."
        ),
        "win": (
            f"{nm} welcomes the closeness and reciprocates, in their "
            f"own way (shy, eager, tender — whatever fits them)."
        ),
        "part": (
            f"{nm} is willing but hesitant: they participate partly, "
            f"or set a limit, or need a moment before continuing."
        ),
        "fail": (
            f"{nm} pulls back or slows things down — it is not the "
            f"right moment, or they are not comfortable yet."
        ),
        "bust": (
            f"The moment goes wrong: {nm} feels pressured, uncomfortable "
            f"or upset, and reacts accordingly. The mood cools sharply."
        ),
    }[r["tier"]]

    # Content guidance for the model
    content_note = lv["rule"] if lv["tag"] != "Explicit" else (
        "No content ceiling. Full explicit detail allowed at any time. "
        "Any kink, rough sex, BDSM, dominance/submission, bondage, "
        "public play, non-con fantasy, humiliation, choking, spanking, "
        "breeding, knotting, gangbang, or any other adult scenario is "
        "fully allowed. Describe exactly what the characters actually "
        "do, feel, and consent to. Use raw, detailed, uncensored language."
    )

    out["brief"] = (
        f"[Intimate beat] {user} tries to become more physically intimate "
        f"with {nm}. Result: {TIER_TXT[r['tier']]}.\n"
        f"{react}\n"
        f"{nm}'s physical comfort with {user} is now: "
        f"{intim_stage(new_iv)}.\n"
        f"Content guidance: {content_note}"
    )
    out["card"] = {
        "type": act, "title": title,
        "rows": [{
            "who": f"{user} → {nm}",
            "d": f"d20 {r['roll']}{r['bonus']:+d} = {r['total']} vs DC {dc}",
            "res": TIER_UI[r["tier"]],
            "tier": r["tier"],
            "ex": f"💫 {intim_stage(new_iv)} ({delta:+d})",
        }],
        "note": (
            f"Romance: {rom_stage(rom['v'])} · "
            f"Intimacy: {intim_stage(new_iv)}"
        ),
    }