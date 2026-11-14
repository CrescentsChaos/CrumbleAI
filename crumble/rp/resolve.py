"""Turn what the player just did into dice, damage and relationship changes."""
import json

from .actions import AUTO, LAB, ROMS, classify
from .combat import begin_fight, end_fight, fight_brief, fight_round, ev_row
from .dice import TIER_TXT, TIER_UI, best, best_name, check, parse_stats
from .mentions import find_ids
from .romance import romance_beat
from .intimacy import intimacy_beat, settings as intim_settings
from .skills import AFF_FX, skill_dc


def rp_resolve(b):
    """Turn what the player just did into dice, damage and relationship changes. Returns the new state, a card for the page and a brief for the model."""
    members, user = b["members"], str(b.get("user") or "User")
    cfg, text, forced = b.get("cfg") or {}, str(b.get("text") or "")[:2000], b.get("forced") or None
    rp = json.loads(json.dumps(b.get("rp") or {}))
    aff = {k: int(v) for k, v in (b.get("aff") or {}).items() if isinstance(v, (int, float))}
    mood = {k: str(v) for k, v in (b.get("mood") or {}).items()}
    ust, ugear = parse_stats(b.get("ustats")), str(b.get("ugear") or "")[:400]
    out = {"rp": rp, "card": None, "brief": "", "acting": [], "aff": {}}
    cb = rp.get("combat") if (rp.get("combat") or {}).get("on") else None
    byid = {c["id"]: c for c in members}
    tids = find_ids(text, members, True) or find_ids(text, members, False)
    if not tids and b.get("last") in byid:
        tids = [b["last"]]
    if not tids and len(members) == 1:
        tids = [members[0]["id"]]
    if forced == "peace":
        if cb:
            end_fight(rp)
            out["brief"] = f"[Combat ended: {user} calls off the fight and everyone stands down, still wary.]"
            out["card"] = {"type": "peace", "title": "Fight ended", "rows": [], "note": "Everyone stands down."}
        return out
    if forced == "rest":
        rp["hp"], rp["combat"] = {}, None
        out["brief"] = f"[Time passes: {user} and everyone rest and recover from their injuries.]"
        out["card"] = {"type": "rest", "title": "Rest", "rows": [], "note": "Everyone is healed."}
        return out
    act = forced or (classify(text, bool(cb), bool(cfg.get("romance", True))) if cfg.get("mode", "auto") == "auto" else None)
    if act and not forced and act not in AUTO:
        act = None
    if act in ROMS and not cfg.get("romance", True):
        act = None
    if cb:
        if act is None and "*" not in text:
            return out    # just talking: the fight does not advance
        act = act if act in LAB else "other"
        started = False
    elif act == "attack":
        foes = tids or [members[0]["id"]]
        begin_fight(rp, user, ust, ugear, members, foes, aff)
        for i in foes:
            out["aff"][i] = -10
            if (rp.get("rom") or {}).get(i):
                rp["rom"][i]["v"] = max(0, rp["rom"][i]["v"] - 15)
        started = True
    elif act in ROMS:
        c = byid.get(tids[0]) if tids else None
        if c:
            icfg = intim_settings(cfg.get("intimacy"))
            if act == "intimate" and icfg["on"]:
                intimacy_beat(act, c, rp, aff, mood, ust, cfg, icfg, user, out)
            else:
                romance_beat(act, c, rp, aff, mood, ust, cfg, user, out)
        return out
    elif act in LAB and act not in ("flee", "defend"):
        tgt = byid.get(tids[0]) if tids and act in ("persuade", "intimidate", "deceive", "comfort", "sneak", "steal", "heal") else None
        r = check(best(ust, LAB[act][1]), skill_dc(act, tgt, aff, mood, cfg))
        label = LAB[act][0]
        who = f" {tgt['name']}" if tgt else ""
        out["brief"] = f"[Action resolved] {user} tries to {label.lower()}{(' (on' + who + ')') if tgt else ''}: {TIER_TXT[r['tier']]}. Show it playing out that way; do not contradict this outcome."
        out["card"] = {"type": act, "title": f"{label} · {best_name(ust, LAB[act][1])}", "note": "",
                       "rows": [{"who": f"{user}{' → ' + tgt['name'] if tgt else ''}", "d": f"d20 {r['roll']}{r['bonus']:+d} = {r['total']} vs DC {r['dc']}",
                                 "res": TIER_UI[r["tier"]], "tier": r["tier"]}]}
        if tgt:
            out["acting"] = [tgt["id"]] if act in ("persuade", "intimidate", "deceive", "comfort") else []
            fx = AFF_FX.get(act)
            if fx:
                out["aff"][tgt["id"]] = fx[("crit", "win", "part", "fail", "bust").index(r["tier"])]
        return out
    else:
        return out
    evs, end = fight_round(rp, user, ust, aff, act, tids)
    cbs = rp["combat"]
    byst = [c.get("name") for c in members if c["id"] not in {u["id"] for u in cbs["units"]}]
    out["brief"] = fight_brief(cbs, evs, end, started, user, byst)
    rows = [ev_row(e) for e in evs]
    out["acting"] = list(dict.fromkeys(e["wid"] for e in evs if e.get("wid") not in (None, "user")))
    for e in evs:
        if e["act"] in ("attack", "power") and e["tid"] != "user" and e["dmg"] and next((u for u in cbs["units"] if u["id"] == e["tid"]), {}).get("side") == "foe":
            out["aff"][e["tid"]] = out["aff"].get(e["tid"], 0) - 2
    cbs["round"] += 0 if end else 1
    note = {"victory": "Victory!", "defeat": "You are down.", "truce": "Everyone stands down.", "fled": "You got away."}.get(end, "")
    if started:
        note = ("Combat begins. " + note).strip()
    out["card"] = {"type": act, "title": "Combat · " + (LAB[act][0] if act in LAB else "Action"), "rows": rows, "note": note, "end": end}
    if end:
        end_fight(rp)
    return out
