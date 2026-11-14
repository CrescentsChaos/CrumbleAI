"""@mentions and plain-name mentions in a group chat."""
import re


def find_ids(text, members, at=True):
    """Ids of characters named in text, in order of appearance. at=True: only '@Name'; at=False: plain names (not '@Name')."""
    hits = []
    for c in members:
        nm = (c.get("name") or "").strip()
        for p in dict.fromkeys([nm, nm.split()[0] if nm else ""]):
            if len(p) < 2:
                continue
            m = re.search((r"@\s?" if at else r"(?<![@\w])") + re.escape(p) + r"(?!\w)", text, re.I)
            if m:
                hits.append((m.start(), c["id"]))
                break
    return [i for _, i in sorted(hits)]


def at_all(text):
    return bool(re.search(r"@\s?(everyone|everybody|all|guys|team|group)(?!\w)", text, re.I))
