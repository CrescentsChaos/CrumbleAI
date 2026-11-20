"""How private generation context is packaged for the model.

Before: scene summary, memories, mood, relationship stage, story clock and location notes were separate '[Label]' blocks with
'Field: value' lines (and the summary still carried its 'SETTING & STATE / Location: / Primary Dynamic:' template), mixed in with the
character sheet. The model saw a form, so it filled in the form: characters printed 'Location: ...', 'Current State: ...' and
timestamps in their replies. Now:

    recap(summary, ...)      the stored summary (a template with headings and labelled fields) rewritten as plain sentences, so
                             there is no form left to copy
    prose_short(lines)       'Scene: x' / 'Just happened: a; b' from the short-term memory as sentences
    envelope(blocks)         all private blocks between two explicit markers, so the model can tell reference from story
    CONTRACT                 the rule for using it, placed late in the prompt where small models listen most
    history_text(...)        earlier replies cleaned before they are shown to the model again (a leak left in the history is a
                             precedent the model happily repeats)

Pure text functions apart from the history cleaner, which uses leak/textutil.
"""
import re

START = "=== PRIVATE BACKGROUND (silent reference for the writer: never part of the story) ==="
END = "=== END OF PRIVATE BACKGROUND ==="

CONTRACT = ("[How to use the private background]\n"
            "- Everything between the PRIVATE BACKGROUND markers is silent knowledge, like what a real person simply knows about their own life. "
            "It is never dialogue and never narration.\n"
            "- Never reproduce its headings, field names, bracketed labels, timestamps or clock times given as data, mood or relationship ratings, "
            "numbers, summaries or instructions, and never describe {CH} or the scene as if reading a status panel.\n"
            "- Let it work invisibly: it decides what {CH} knows, feels, wants and notices. Mention a remembered fact only when it comes up "
            "naturally, in {CH}'s own words.\n"
            "- A reply is only what {CH} says and does inside the story.")

_EMPTY = re.compile(r"(?i)^(?:not\s+established|n/?a|none|unknown|unclear|nothing|-+|\.+)\.?$")
_HEAD = re.compile(r"^[ \t#*]*([A-Z][A-Z &/]{3,})[ \t*]*:?[ \t]*$")
_FIELD = re.compile(r"^[ \t#*-]*([A-Za-z][A-Za-z '&/]{1,30}?)[ \t*]*:[ \t*]*(.*\S)[ \t]*$")


def _sentence(x):
    x = re.sub(r"\s+", " ", x or "").strip().strip("*").strip()
    if not x:
        return ""
    return x if x[-1] in ".!?…" else x + "."


def _lower(x):
    return x[:1].lower() + x[1:] if x[:2] != "I " and not x[:2].isupper() else x


def recap(summary, char="", user="", group=False):
    """The stored summary as plain prose. A summary that does not follow the template (an older chat, or one the user edited by hand)
    is kept as written, only without its capital-letter headings and 'Label:' prefixes."""
    raw = (summary or "").strip()
    if not raw:
        return ""
    fields, moments, loose, section = {}, [], [], ""
    for line in raw.split("\n"):
        if not line.strip():
            continue
        h = _HEAD.match(line)
        if h:
            section = h.group(1).strip().lower()
            continue
        f = _FIELD.match(line)
        if f:
            key, val = f.group(1).strip().lower(), f.group(2).strip()
            if not _EMPTY.match(val):
                fields.setdefault(key, val)
            continue
        item = re.sub(r"^[ \t]*[-•*][ \t]*", "", line).strip()
        if not item or _EMPTY.match(item):
            continue
        (moments if "pivotal" in section or line.lstrip().startswith(("-", "•")) else loose).append(item)
    out = []
    if fields.get("location"):
        out.append(f"The story so far takes place at {_lower(fields['location']).rstrip('.')}.")
    if fields.get("current state"):
        out.append(_sentence(fields["current state"]))
    if fields.get("primary dynamic"):
        out.append(("As for how they all relate, " if group else "As for the relationship, ") + _lower(_sentence(fields["primary dynamic"])))
    if fields.get("tone"):
        out.append(f"The mood between them has been {_lower(fields['tone']).rstrip('.')}.")
    for k, v in fields.items():
        if k not in ("location", "current state", "primary dynamic", "tone"):
            out.append(_sentence(v))
    if moments:
        out.append("Moments that still matter: " + "; ".join(m.rstrip(".") for m in moments[:8]) + ".")
    out += [_sentence(x) for x in loose]
    return " ".join(x for x in out if x).strip()


def prose_short(lines):
    """Short-term memory lines ('Scene: ...', 'Just happened: a; b') as sentences without labels."""
    out = []
    for l in lines or []:
        m = re.match(r"(?i)^(scene|just happened)\s*:\s*(.+)$", l.strip())
        if not m:
            out.append(_sentence(l))
        elif m.group(1).lower() == "scene":
            out.append(_sentence(m.group(2)))
        else:
            out.append("Moments ago: " + m.group(2).strip().rstrip(".") + ".")
    return [x for x in out if x]


def envelope(blocks):
    blocks = [b for b in blocks if b and b.strip()]
    return (START + "\n\n" + "\n\n".join(b.strip() for b in blocks) + "\n\n" + END) if blocks else ""


def history_text(text, name="", user="", others=()):
    """An earlier assistant message, cleaned the same way a new reply is (entities, leaked labels, broken stars), so a leak that got into
    the saved chat before is not fed back to the model as an example of how to write."""
    from . import leak, textutil
    t = textutil.unescape(text or "")
    t, _ = leak.scrub(t, name, user, others)
    return textutil.tidy_markup(t).strip() or (text or "").strip()
