"""Action labels and the classifier that guesses which action a message performs."""
import re

LAB = {"heal": ("Aid", ("WIS", "INT")), "intimidate": ("Intimidate", ("STR", "CHA")),
       "persuade": ("Persuade", ("CHA",)), "deceive": ("Deceive", ("CHA", "INT")), "sneak": ("Sneak", ("DEX",)),
       "steal": ("Sleight of hand", ("DEX",)), "athletics": ("Athletics", ("STR", "DEX")),
       "investigate": ("Investigate", ("INT", "WIS")), "craft": ("Craft or repair", ("INT", "DEX")),
       "comfort": ("Comfort", ("WIS", "CHA")), "flirt": ("Flirt", ("CHA",)), "touch": ("Tender touch", ("CHA",)),
       "date": ("Ask on a date", ("CHA",)), "kiss": ("Kiss", ("CHA",)), "confess": ("Confess feelings", ("CHA",)),
       "intimate": ("Get closer", ("CHA",)), "revive": ("Resurrect", ("WIS", "CHA"))}
ROMS = {"flirt": 10, "touch": 25, "date": 30, "kiss": 50, "confess": 55, "intimate": 75}   # how warm they must already be
AUTO = {"heal", "intimidate", "persuade", "deceive", "sneak", "steal", "revive"} | set(ROMS)


# (act, narrated-action words, words that count only when written as "I ..." or inside *asterisks*, words that count even when spoken, where)
RX = [
    ("revive", r"resurrect\w*|reviv\w*|bring\w* (?:\w+ ){0,2}back (?:to life|from the dead)|raise\w* (?:\w+ ){0,2}from the dead|reanimat\w*|restor\w* (?:\w+ ){0,2}to life|breath\w* life (?:back )?into|cast\w* (?:resurrection|revive)|use\w* (?:the |my )?(?:phoenix|ankh|elixir of life)", "", "", ""),
    ("heal", r"heal(?:s|ed|ing)? (?:myself|him|her|them|my|his|their|the|\w+'s)|bandag\w*|dress\w* (?:the |his |her |their |\w+'s )?wound\w*|drink\w* (?:a|the) potion|patch\w* (?:up|myself|him|her|them)|first aid|treat\w* (?:my|the|his|her|their|\w+'s) (?:wounds?|injur\w*)|nurs(?:e|es|ed|ing) (?:my|the|his|her|their|\w+'s) (?:wounds?|injur\w*|arm|leg)|stitch\w*|suture\w*|set\w* (?:the|his|her|their) (?:bone|arm|leg)|tend\w* (?:to )?(?:the |his |her |their |\w+'s )?(?:wounds?|injur\w*)", "", "", ""),
    ("intimidate", r"intimidat\w*|threaten\w*|menac\w*|growl\w* at|loom\w* over|glar\w+ at|bully\w*|snarl\w* at|warn\w* (?:him|her|them)", "",
     r"or else|you(?:'ll| will) regret (?:this|it)|i'?ll (?:kill|hurt|end) you|back off or", ""),
    ("persuade", r"persuad\w*|convinc\w*|plead\w*|bargain\w*|negotiat\w*|reason\w* with|appeal\w* to|talk\w* (?:him|her|them) into|haggl\w*|sweet-?talk\w*|beg\w* (?:him|her|them|you) (?:to|for)", "", r"i'?m begging you|hear me out", ""),
    ("deceive", r"lie\w* to|bluff\w*|deceiv\w*|trick\w*|mislead\w*|fib\w*|con\w* (?:him|her|them)|pretend\w* (?:to be|i)|feign\w*", "", "", ""),
    ("sneak", r"sneak\w*|tiptoe\w*|creep\w* (?:past|up|behind|along)|slip\w* (?:past|away|out)|stalk\w*", "", "", ""),
    ("steal", r"steal\w*|stole|pickpocket\w*|swipe\w* (?:his|her|the|their)|snatch\w* (?:his|her|the|their)|lift\w* (?:his|her|their) (?:wallet|purse|keys)|lockpick\w*|pick\w* (?:the|a) lock", "", "", ""),
    ("intimate", r"make love|sleep with|go to bed with|take (?:her|him|them) to bed|spend the night with|undress (?:her|him|them)", "", "", ""),
    ("kiss", r"kiss\w*|make out|smooch\w*|peck\w* (?:her|him|them)", "", "", ""),
    ("confess", r"confess\w*|(?:tell|tells|telling) (?:her|him|them) (?:i|that i) love|be my (?:girlfriend|boyfriend|partner|valentine)", "",
     r"i love you|i'?m in love with you|be my (?:girlfriend|boyfriend|partner)|i have feelings for you", ""),
    ("date", r"ask\w* (?:her|him|them) out|take\w* (?:her|him|them) (?:out )?on a date|invit\w+ (?:her|him|them) (?:to|for) (?:dinner|a date|a walk|drinks|coffee|a movie)", "",
     r"go (?:out|on a date) with me|let me take you (?:out|to dinner)|would you like to (?:get dinner|grab dinner|go out|get coffee|grab a drink)", ""),
    ("touch", r"hold\w* (?:her|his|their|your) hand|tak\w+ (?:her|his|their|your) hand|caress\w*|cuddl\w*|snuggl\w*|pull\w* (?:her|him|them) (?:close|in)|embrac\w*|stroke\w* (?:her|his|their) (?:cheek|hair|face)|tuck\w* (?:her|his|their) hair|wrap\w* (?:my|his|her) arms? around", "", "", ""),
    ("flirt", r"flirt\w*|wink\w*|bat\w* (?:my|her|his) (?:eyelashes|eyes)|lean\w* in close|whisper\w* in (?:her|his|their) ear|smoulder\w*|smolder\w*", "",
     r"you(?:'re| are) (?:so |really |very )?(?:beautiful|handsome|gorgeous|stunning|hot|cute|adorable)|you look (?:so |really |very )?(?:beautiful|handsome|gorgeous|stunning|amazing)|(?:can|may) i buy you a drink", ""),
]
NEGW = re.compile(r"(?:don't|do not|dont|never|won't|will not|wouldn't|would not|can't|cannot|not|no|stop|without|refuse to|rather than|instead of|wish i could|if i) (?:\w+ ){0,2}$")


def classify(text, combat=False, romance=True):
    """Guess which action a message performs. Spoken lines (inside quotes) only count for the few acts that can be spoken."""
    full = " ".join((text or "").lower().split())
    narr = re.sub(r'["“][^"”“]*["”]', " ", full)
    stars = " ".join(re.findall(r"\*([^*]+)\*", narr))
    scope = stars if stars else narr      # with *actions* only the actions count; plain chat needs an explicit "I ..." (so "he convinced me" starts nothing)
    for key, strong, weak, speech, where in RX:
        if (where == "c" and not combat) or (key in ROMS and not romance):
            continue
        rxs = [((r"\b(?:%s)\b" if stars else r"\bi(?:'ll| will| try to| attempt to| want to| decide to|'m going to| gonna)? (?:%s)\b") % strong, scope)] if strong else []
        if weak:
            rxs.append((r"(?:\bi(?:'ll| will| try to| attempt to| want to| decide to|'m going to| gonna)? |\*\s*)(?:%s)\b" % weak, narr))
        if speech:
            rxs.append((r"\b(?:%s)\b" % speech, full))
        for rx, hay in rxs:
            for m in re.finditer(rx, hay):
                if NEGW.search(hay[max(0, m.start() - 32):m.start()]):
                    continue
                if key == "kiss" and re.match(r"kiss\w* (?:her|his|their|your|the) (?:cheek|forehead|hand|head)", hay[m.start():]):
                    return "touch"
                return key
    return None
