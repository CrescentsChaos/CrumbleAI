"""A world that moves: small things happen around the conversation, and each character has a little life of their own.

World beats are tiny events that fit the place, the hour and the weather (a bus sighs past, the kettle clicks off, a bell rings across the
courtyard, the lights flicker). They arrive on a fixed cadence (the same chat always gives the same turns, so a swipe keeps its beat), never
interrupt a hurting person or a tender or frightening moment, and are written as texture: no new named people, nothing the other person has to
answer. Life seeds are things from the character's own day that they may mention (a hunger, a deadline, a small annoyance), taken from the
routine and the hour, never invented backstory.

    beat(turn, cid, place, indoors, period, weather, horror, setting)    -> str or ''
    seed(turn, cid, routine, hour)                                         -> str or ''
Pure functions.
"""
import zlib

PLACE = {   # place name (as ambience.PLACES) -> small events
    "the library": ["a book is shelved somewhere with a soft thud", "someone's phone buzzes and is muffled in a hurry", "the librarian's cart squeaks past", "a chair scrapes and a few heads turn", "the lights hum, one tube flickering for a second"],
    "the classroom": ["a chair scrapes in the back row", "chalk or a marker squeaks on the board", "a phone buzzes under a desk", "the clock ticks loud in a quiet moment", "somebody sneezes and gets a muttered 'bless you'"],
    "the university campus": ["a bike bell rings behind them", "a group of students laughs somewhere nearby", "a bell tolls the quarter hour", "a flyer skitters past in the wind", "a food cart's smell drifts over"],
    "the bedroom": ["the building creaks as it settles", "a phone lights up on the desk and goes dark", "pipes knock somewhere in the wall", "a neighbour's muffled music comes through, then stops", "a car passes and its lights sweep across the ceiling"],
    "the kitchen": ["the kettle clicks off", "the fridge shudders and settles into its hum", "something in a pan hisses", "the toaster pops", "a tap drips twice"],
    "the living room": ["the heating ticks on", "the TV, left on low, changes to an advert", "a cushion slides off the sofa", "a floorboard pops overhead", "the clock on the wall chimes"],
    "the bathroom": ["a pipe gurgles", "a drop falls from the tap, loud in the quiet", "the extractor fan whirs on", "steam fogs the mirror a little more"],
    "the café": ["the milk steamer shrieks for a moment", "a cup clinks against a saucer at the next table", "the door bell jingles as somebody comes in", "the grinder roars and cuts out", "someone calls a drink name that is not theirs"],
    "the apartment": ["a neighbour's door slams down the hall", "the elevator pings", "pipes knock in the wall", "someone upstairs drags a chair", "the smell of someone's cooking drifts through"],
    "the hallway": ["a door opens and closes somewhere down the corridor", "footsteps approach, pass, and fade", "a light buzzes and blinks", "a trolley rattles past"],
    "the basement": ["a drip echoes in the dark", "the boiler groans and ticks", "something small scurries behind the shelves", "a pipe shudders overhead"],
    "the attic": ["the beams creak as the wind shifts", "something shifts softly under a dust sheet", "a pigeon shuffles on the roof", "a draught stirs the dust in a thin beam of light"],
    "the old house": ["a floorboard creaks upstairs where nobody is", "a door drifts a little further open", "the wind moans through a gap in the wall", "a shutter taps twice and goes still"],
    "the cabin": ["a log in the stove shifts and sparks", "the wind leans on the shutters", "the timber ticks as it cools", "an owl calls from outside, once"],
    "the car": ["the indicator ticks steadily", "the engine note changes on a hill", "a truck rushes past and rocks the car", "a song on the radio fades into static for a moment", "the wipers or the heater kick in"],
    "the train": ["the train lurches over a switch", "the announcement crackles and no one can quite hear it", "the doors hiss at a stop and let a gust through", "a child's laugh carries down the carriage", "the lights dip for a second in a tunnel"],
    "the street": ["a bus sighs to a stop and pulls away", "a scooter weaves by and honks", "a shop shutter rattles up or down", "someone shouts a greeting across the road", "a dog barks twice and loses interest"],
    "the park": ["a jogger passes with a nod", "a dog bounds by trailing its owner's apology", "a gust sends leaves tumbling over the path", "children's laughter carries from the playground", "a bird makes a fuss in a nearby tree"],
    "the forest": ["a branch cracks far off", "birds go quiet for a moment, then start up again", "a breeze moves through the canopy like a long breath", "something small rustles in the undergrowth"],
    "the beach": ["a wave breaks louder than the others", "gulls wheel and complain overhead", "the wind lifts a little sand and drops it", "a distant horn sounds from a boat"],
    "the rooftop": ["the wind tugs at their clothes", "a siren rises and falls far below", "a pigeon lands on the ledge and eyes them", "a plane drones across the sky"],
    "the graveyard": ["a crow shifts on a headstone", "the wind moves the dry leaves along the path", "a bell tolls once somewhere far away", "the grass hisses in a long gust"],
    "the restaurant": ["a tray of plates clatters in the kitchen", "a burst of laughter erupts at another table", "the smell of something frying drifts past", "a waiter squeezes by with a murmured apology"],
    "the shop": ["the door chimes as a customer comes in", "the till beeps and the drawer slides out", "a box thumps down in the back", "a speaker crackles with a bit of music"],
    "the garage": ["an engine somewhere ticks as it cools", "a tool clatters off a bench", "the radio crackles between stations", "a car passes outside and its lights sweep the wall"],
    "the gym": ["a weight plate clanks down", "the treadmill whines up a notch", "a buzzer sounds for the end of a class", "someone grunts, then laughs at themselves"],
}
PERIOD = {   # (indoors, outdoors)
    "early morning": (["the first light is pale at the window", "somewhere a delivery van reverses, beeping"], ["birds start up, tentative and loud", "the street is nearly empty, a milk float or a bus the only sound"]),
    "morning": (["sunlight creeps across the floor", "the building wakes up: doors, taps, footsteps"], ["commuters hurry past with coffee", "a shop opens up and the smell of bread drifts out"]),
    "midday": (["the light is high and flat in the window", "the smell of someone's lunch drifts by"], ["the sun is high and shadows are short", "a lunch crowd spills out of an office"]),
    "afternoon": (["the light has turned slow and golden at the edges", "a distant school bell rings"], ["a school bell rings and the street fills with kids", "the afternoon heat or chill settles in"]),
    "early evening": (["lamps come on one by one in the windows opposite", "dinner smells begin to drift through the walls"], ["streetlights flicker on", "the light turns gold, then orange"]),
    "evening": (["someone's TV laughs faintly through the wall", "the day's noises thin out"], ["windows glow up and down the street", "a train or a bus passes, nearly empty"]),
    "night": (["the building has gone quiet; a fridge hums", "a car passes outside and its lights slide over the wall"], ["a far-off siren rises and fades", "the streets are almost silent; a cat slips across the road"]),
    "late at night": (["the silence has a weight now; the fridge hum seems loud", "a creak in the dark that is only the house settling"], ["a lone car passes and its sound lingers", "somewhere far off, a dog barks once"]),
}
WEATHER = {
    "rain": ["the rain gusts harder against the glass for a moment", "a drip finds its way in somewhere and keeps time", "a car hisses past through a puddle"],
    "storm": ["thunder rolls in, closer than the last", "the lights flicker once, and everyone notices", "a flash of lightning whitens everything for an instant"],
    "snow": ["a clump of snow slides off a roof with a soft thump", "the whole world seems to go quieter for a moment", "someone stamps snow off their boots nearby"],
    "fog": ["a foghorn or a far-off bell sounds somewhere, hard to place", "shapes loom and resolve into ordinary things"],
    "wind": ["a gust rattles something loose nearby", "a door bangs somewhere in the wind"],
    "hot": ["the heat shimmers and a fan labours somewhere", "a cold drink sweats a ring onto the surface"],
    "cold": ["a draught finds the back of the neck", "breath fogs, or a radiator ticks as it warms"],
    "clear": ["a patch of sun slides over the floor or the path", "a bird sings from somewhere above"],
    "overcast": ["the light dips as a heavier cloud passes over", "the grey light makes everything look a bit flatter"],
}
UNEASE = ["a sound nearby stops all at once", "a light flickers and steadies", "something small has moved that no one touched", "a cold draught crosses the room from nowhere", "a distant sound that is almost, but not quite, a voice"]
SEEDS = {   # routine key -> things from the character's own day they may mention (only if natural)
    "wake": ["still needs coffee", "slept badly or too well", "the alarm went off too early"], "breakfast": ["something small about what they are eating", "a craving for something they do not have"],
    "commute": ["the crowd or the traffic", "being a little late or just on time", "something seen on the way"], "work": ["a small annoyance at work", "something they are putting off", "the clock moving too slowly"],
    "class": ["a lecture that dragged", "an assignment hanging over them", "a classmate's odd habit"], "shift": ["feet already aching", "how long until the shift ends", "something odd that happened on shift"],
    "lunch": ["what they are eating or wish they were", "how short the break is"], "break": ["the need for a coffee", "stretching a stiff back"],
    "errands": ["a long list and not enough time", "a queue that will not move"], "exercise": ["sore muscles", "being out of breath", "pushing a little further than they meant to"],
    "dinner": ["what is cooking or what they cannot be bothered to cook", "being starving"], "chores": ["a pile of laundry or dishes", "putting off the thing they should be doing"],
    "hobby": ["something they are working on", "losing track of time over it"], "social": ["the noise and the people around", "someone they have not seen in a while"],
    "relax": ["finally sitting down", "what is on in the background"], "winddown": ["being properly tired now", "tomorrow's early start"], "sleep": ["being woken up and not happy about it", "wanting very much to go back to sleep"],
}


def _h(*a):
    return zlib.crc32("|".join(str(x) for x in a).encode("utf-8", "ignore"))


def beat(turn, cid, place, indoors, period, weather, horror=0, setting="normal", skip=False):
    every = {"off": 0, "rare": 11, "normal": 7, "lively": 4}.get(setting, 7)
    if not every or skip or (horror == 2 and False):
        return ""
    if (turn + _h(cid) % every) % every != 0 or turn < 2:
        return ""
    if horror:
        pool = list(UNEASE)
    else:
        pool = []
        if place and place in PLACE:
            pool += PLACE[place] * 2
        pp = PERIOD.get(period)
        if pp:
            pool += pp[0] if indoors else pp[1]
        if weather in WEATHER:
            pool += WEATHER[weather]
    if not pool:
        return ""
    return pool[_h(cid, turn, "b") % len(pool)]


def seed(turn, cid, key, every=6):
    opts = SEEDS.get(key)
    if not opts or (turn + _h(cid, "seed") % every) % every != 0 or turn < 1:
        return ""
    return opts[_h(cid, turn, "s") % len(opts)]
