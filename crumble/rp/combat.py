"""Turn-based fights: units, strikes, NPC behaviour and the round narration."""
import random
import re

from .actions import LAB
from .dice import TIER_TXT, TIER_UI, best, best_name, check, md, parse_stats, roll


def weapon_die(txt):
    t = (txt or "").lower()
    for pat, d in ((r"greatsword|greataxe|warhammer|maul|halberd|rifle|shotgun|sniper|cannon|scythe|battleaxe|axe|hammer", 10),
                   (r"sword|blade|katana|saber|sabre|mace|spear|rapier|pistol|gun|revolver|crossbow|bow|whip|staff|bat|club|trident|chain", 8),
                   (r"dagger|knife|claws?|fangs?|talons?|stiletto|dart|sling|taser|baton|brass knuckles", 6)):
        if re.search(r"\b(?:%s)\b" % pat, t):
            return d
    return 4


def armor_bonus(txt):
    t, b = (txt or "").lower(), 0
    if re.search(r"\b(plate|full armou?r|power armou?r|exosuit)\b", t):
        b = 5
    elif re.search(r"\b(chain ?mail|mail|scale|kevlar|riot|heavy armou?r)\b", t):
        b = 3
    elif re.search(r"\b(leather|armou?r|vest|padded|robes?)\b", t):
        b = 2
    return min(6, b + (1 if re.search(r"\bshield\b", t) else 0))


# ----- fights
def alive(u):
    return u["hp"] > 0 and not u.get("fled")


def cond(u):
    if u.get("fled"):
        return "fled the fight"
    if u["hp"] <= 0:
        return "knocked out"
    r = u["hp"] / u["max"]
    return "unhurt" if r > .75 else "wounded" if r > .5 else "badly hurt" if r > .25 else "barely standing"


def heft(d, mx):
    return "a devastating blow" if d >= mx * .3 else "a heavy hit" if d >= mx * .2 else "a solid hit" if d >= mx * .1 else "a light hit"


def mk_unit(uid, name, side, stats, gear, hp=None):
    g = (gear or "").lower()
    mx = max(10, 20 + 2 * md(stats["CON"]))
    return dict(id=uid, name=name, side=side, max=mx, hp=mx if hp is None else max(1, min(mx, int(hp))),
                ac=10 + md(stats["DEX"]) + armor_bonus(g), atk=max(md(stats["STR"]), md(stats["DEX"])) + 2,
                dmg=max(0, md(stats["STR"]), md(stats["DEX"])), magic=best(stats, ("INT", "WIS", "CHA")) + 2, die=weapon_die(g),
                init=md(stats["DEX"]), special=bool(re.search(r"magic|spell|power|psychic|telekin|curse|hex|summon|fire|ice|lightning|blast|aura|chi|ki\b|ability|gift", g)),
                brave=bool(re.search(r"fearless|berserk|undead|golem|robot|android|unyielding|never retreat|to the death", g)), roll=0)


def strike(a, t, magic=False, adv=0):
    ac = t["ac"] + (4 if t.get("def") else 0)
    r = check(a["magic"] if magic else a["atk"], ac, adv)
    dmg = 0
    if r["tier"] in ("crit", "win", "part"):
        base = (roll(2, 6) + max(0, a["magic"] - 2)) if magic else (random.randint(1, a["die"]) + a["dmg"])
        if r["tier"] == "crit":
            base += roll(2, 6) if magic else random.randint(1, a["die"])
        dmg = max(1, base // 2 if r["tier"] == "part" else base)
        t["hp"] = max(0, t["hp"] - dmg)
    r.update(act="power" if magic else "attack", who=a["name"], wid=a["id"], tgt=t["name"], tid=t["id"], dmg=dmg, thp=t["hp"], tmax=t["max"], ac=ac)
    return r


def npc_turn(u, cb, evs):
    foe = u["side"] == "foe"
    opp = [x for x in cb["units"] if alive(x) and ((x["side"] in ("player", "ally")) if foe else x["side"] == "foe")]
    if not opp:
        return
    if u["hp"] <= u["max"] * .3 and not u["brave"] and random.random() < .55:
        u["fled"] = True
        evs.append({"act": "yield" if random.random() < .5 else "flee", "who": u["name"], "wid": u["id"]})
        return
    pl = next((x for x in opp if x["side"] == "player"), None)
    t = (pl if pl and (len(opp) == 1 or random.random() < .65) else random.choice(opp)) if foe else min(opp, key=lambda x: x["hp"])
    evs.append(strike(u, t, u["special"] and random.random() < .3, -1 if u.pop("shaken", 0) else 0))


def begin_fight(rp, user, ust, ugear, members, foe_ids, aff):
    hp = rp.setdefault("hp", {})
    units = [mk_unit("user", user, "player", ust, ugear, hp.get("user"))]
    for c in members:
        side = "foe" if c["id"] in foe_ids else "ally" if aff.get(c["id"], 50) >= 65 else None
        if side:
            u = mk_unit(c["id"], c.get("name") or "?", side, parse_stats(c.get("stats")), c.get("combat"), hp.get(c["id"]))
            u["roll"] = roll(1, 20) + u["init"]
            units.append(u)
    rp["combat"] = {"on": True, "round": 1, "units": units}
    return rp["combat"]


def end_fight(rp):
    hp = rp.setdefault("hp", {})
    for u in rp["combat"]["units"]:
        hp[u["id"]] = u["hp"] if u["hp"] > 0 else max(1, u["max"] // 4)   # the downed come round, shaken
    rp["combat"] = None


def fight_round(rp, user, ust, aff, act, tids):
    cb = rp["combat"]
    P = next(u for u in cb["units"] if u["id"] == "user")
    P["def"] = False
    foes = [u for u in cb["units"] if u["side"] == "foe" and alive(u)]
    tgt = next((u for u in foes if u["id"] in tids), None) or (min(foes, key=lambda u: u["hp"]) if foes else None)
    evs, end, skip = [], None, False
    me = dict(who=user, wid="user")
    if act in ("attack", "special") and tgt:
        evs.append(strike(P, tgt, act == "special"))
    elif act == "defend":
        P["def"] = True
        evs.append(dict(me, act="defend"))
    elif act == "flee":
        r = check(md(ust["DEX"]), 10 + 2 * len(foes))
        evs.append(dict(r, me, act="flee_try", label="Flee", stat="DEX"))
        if r["tier"] in ("crit", "win"):
            end = "fled"
    elif act == "heal":
        ally = next((u for u in cb["units"] if u["side"] == "ally" and alive(u) and u["id"] in tids), None) or P
        r = check(best(ust, ("WIS", "INT")), 10)
        amt = 0
        if r["tier"] != "bust" and r["tier"] != "fail":
            amt = roll(1, 8) + max(0, best(ust, ("WIS", "INT")))
            amt = amt * 2 if r["tier"] == "crit" else max(1, amt // 2) if r["tier"] == "part" else amt
            ally["hp"] = min(ally["max"], ally["hp"] + amt)
        evs.append(dict(r, me, act="heal", label="Aid", stat=best_name(ust, ("WIS", "INT")), tgt=ally["name"], amt=amt, thp=ally["hp"], tmax=ally["max"]))
    elif act == "persuade":
        a = sum(aff.get(u["id"], 50) for u in foes) // max(1, len(foes))
        r = check(md(ust["CHA"]), max(8, 12 + 2 * (len(foes) - 1) - (a - 50) // 10))
        evs.append(dict(r, me, act="talk", label="Talk them down", stat="CHA"))
        if r["tier"] in ("crit", "win"):
            end = "truce"
        elif r["tier"] == "part":
            skip = True
    elif act == "intimidate":
        r = check(best(ust, ("STR", "CHA")), 12)
        evs.append(dict(r, me, act="check", label="Intimidate", stat=best_name(ust, ("STR", "CHA"))))
        if r["tier"] in ("crit", "win"):
            for u in foes:
                u["shaken"] = 1
                if u["hp"] <= u["max"] * .5 and not u["brave"]:
                    u["fled"] = True
                    evs.append({"act": "flee", "who": u["name"], "wid": u["id"]})
    elif act in LAB and act not in ("attack", "special"):
        r = check(best(ust, LAB[act][1]), 12)
        evs.append(dict(r, me, act="check", label=LAB[act][0], stat=best_name(ust, LAB[act][1])))
    else:
        evs.append(dict(me, act="other"))
    if not end:
        for u in sorted([u for u in cb["units"] if u["side"] != "player" and alive(u)], key=lambda u: -u["roll"]):
            if not alive(u) or P["hp"] <= 0 or not [x for x in cb["units"] if x["side"] == "foe" and alive(x)]:
                continue
            if skip and u["side"] == "foe":
                continue
            npc_turn(u, cb, evs)
    if not end:
        if P["hp"] <= 0:
            end = "defeat"
        elif not [u for u in cb["units"] if u["side"] == "foe" and alive(u)]:
            end = "victory"
    return evs, end


def ev_text(e):
    a = e["act"]
    if a in ("attack", "power"):
        r = {"crit": "a CRITICAL HIT", "win": "a hit", "part": "only a glancing graze", "fail": "a miss", "bust": "a clumsy fumble"}[e["tier"]]
        s = f"{e['who']} {'unleashes a power on' if a == 'power' else 'attacks'} {e['tgt']}: {r}"
        if e["dmg"]:
            s += f" ({heft(e['dmg'], e['tmax'])})" + (f"; {e['tgt']} is knocked down" if e["thp"] <= 0 else "")
        return s
    if a == "defend":
        return f"{e['who']} braces and guards."
    if a == "flee_try":
        return f"{e['who']} tries to break away and escape: {TIER_TXT[e['tier']]}"
    if a == "heal":
        return f"{e['who']} tends to {e['tgt']}: {TIER_TXT[e['tier']]}"
    if a == "talk":
        return f"{e['who']} tries to talk everyone down: {TIER_TXT[e['tier']]}"
    if a == "check":
        return f"{e['who']} tries to {e['label'].lower()}: {TIER_TXT[e['tier']]}"
    if a in ("flee", "yield"):
        return f"{e['who']} " + ("is beaten and yields, backing down." if a == "yield" else "loses their nerve and runs from the fight.")
    return f"{e['who']} does what their message says."


def ev_row(e):
    a = e["act"]
    if a in ("attack", "power"):
        res = {"crit": "Critical hit", "win": "Hit", "part": "Graze", "fail": "Miss", "bust": "Fumble"}[e["tier"]]
        return {"who": f"{e['who']} → {e['tgt']}" + (" ✨" if a == "power" else ""), "d": f"d20 {e['roll']}{e['bonus']:+d} = {e['total']} vs AC {e['ac']}",
                "res": res + (f" · {e['dmg']} dmg" if e["dmg"] else ""), "tier": e["tier"], "ex": f"{e['tgt']} {e['thp']}/{e['tmax']} HP"}
    if a == "defend":
        return {"who": e["who"], "res": "Braces for impact", "tier": "win", "ex": "+4 defense until next turn"}
    if a in ("flee", "yield"):
        return {"who": e["who"], "res": "Yields" if a == "yield" else "Flees", "tier": "win"}
    if a == "other":
        return {"who": e["who"], "res": "Acts", "tier": "win"}
    r = {"who": e["who"], "d": f"d20 {e['roll']}{e['bonus']:+d} = {e['total']} vs DC {e['dc']}", "res": TIER_UI[e["tier"]], "tier": e["tier"]}
    if a == "heal":
        r["ex"] = f"{e['tgt']} +{e['amt']} HP"
    return r


def fight_brief(cb, evs, end, started, user, byst):
    L = [f"[Combat - round {cb['round']}{'; a fight has just broken out' if started else ''}]", "What happened this round, in order:"]
    L += [f"{i}. {ev_text(e)}" for i, e in enumerate(evs, 1)]
    L.append("Conditions now: " + "; ".join(f"{u['name']}{' (ally)' if u['side'] == 'ally' else ' (opponent)' if u['side'] == 'foe' else ''}: {cond(u)}" for u in cb["units"]) + ".")
    if byst:
        L.append("Not fighting (bystanders): " + ", ".join(byst) + ".")
    L.append({"victory": f"The fight is over: {user} won. The defeated are down or have fled. Wrap up the aftermath in character.",
              "defeat": f"The fight is over: {user} has been beaten and falls. Describe the aftermath from who won and what they are like (captured, spared, robbed, left behind, rescued); keep it tasteful.",
              "truce": "The fight is over: everyone stands down. They may stay wary.", "fled": f"{user} got away. The fight is over."}.get(end, ""))
    return "\n".join(l for l in L if l)
