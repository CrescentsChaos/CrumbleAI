"""Held-out cases, written after the main benchmark was tuned and never used to tune anything. Same format as tools.memory_bench.CASES."""
HELDOUT = [
    ("spare_key", "I keep a spare house key under the blue flowerpot.", "Good to know.", ["flowerpot"], "Where is my spare key hidden?", "I'm locked out, where did I stash the extra one?"),
    ("knit", "My grandmother taught me to knit.", "That's a lovely skill.", ["knit"], "Who taught me to knit?", "Which relative showed me how to make scarves with yarn?"),
    ("daisy", "What's in my pocket?", "*Mira tucks a pressed daisy into your coat pocket.*", ["daisy"], "What flower did you put in my pocket?", "Is that blossom still in my jacket?"),
    ("violin", "I'm saving up to buy a violin.", "That would suit you.", ["violin"], "What am I saving up for?", "Do I have any instrument plans?"),
    ("cover_shift", "Can you help me on Friday?", "I'll cover your shift on Friday, I promise.", ["Friday"], "What did you promise about Friday?", "Who is working in my place at the end of the week?"),
    ("bicycle", "Rex stole my bicycle last summer.", "That's awful.", ["bicycle"], "What did Rex steal?", "Who took my bike?"),
    ("oslo", "Tell me about your family.", "My brother Tobias lives in Oslo.", ["Oslo"], "Where does Tobias live?", "Where is your sibling based?"),
    ("driving", "I failed my driving test twice.", "Third time lucky.", ["driving test"], "How many times did I fail my driving test?", "Have I passed my exam to drive a car yet?"),
    ("letter", "Where did the letter go?", "*Mira burns the letter in the fireplace.*", ["letter"], "What did you burn?", "Did you destroy that message?"),
    ("kitten", "We decided to name the kitten Pepper.", "Pepper is perfect.", ["Pepper"], "What did we name the kitten?", "What's our little cat called?"),
    ("born", "Where are you from?", "I was born in a fishing village.", ["fishing village"], "Where were you born?", "What was your hometown like?"),
    ("thunder", "I'm scared of thunderstorms.", "I'll stay with you when they come.", ["thunder"], "What am I scared of?", "Is it okay to go out when it's storming?"),
    ("council", "I have a meeting with the council on Monday morning.", "Good luck.", ["council"], "When is my council meeting?", "Do I have anything scheduled with the officials at the start of the week?"),
    ("quiet", "Why are you so tense?", "Don't mention the fire to anyone, please.", ["fire"], "What was I not supposed to mention?", "What matter did you ask me to keep quiet about?"),
    ("owe", "I owe Garrick two hundred coins.", "You should pay him soon.", ["Garrick"], "How much do I owe Garrick?", "Do I have outstanding debts?"),
    ("scarf", "It's freezing out here.", "*Mira wraps a woolen scarf around your neck.*", ["scarf"], "What did you wrap around my neck?", "That woolen thing you put on me when it was cold?"),
]
HELDOUT_UNKNOWN = ["What did my uncle say at the funeral?", "Do you remember the name of my childhood horse?", "Which restaurant did we visit in Rome?",
                   "Who painted the portrait in your hallway?", "What was written on the card I gave you?", "Did I ever tell you where I went to college?"]

# A second set, written after the fixes driven by HELDOUT above, and run once before anything else changed.
HELDOUT2 = [
    ("lamp", "I always leave the porch lamp on when I'm away.", "Smart habit.", ["porch lamp"], "What do I do with the porch lamp when I travel?", "How do I keep burglars thinking someone is home?"),
    ("bakery", "I grew up above my father's bakery in Dhaka.", "That sounds warm.", ["bakery"], "Where did I grow up?", "Which shop was my childhood home above?"),
    ("tattoo", "*Mira rolls up her sleeve, revealing a faded anchor tattoo.*", "Hm.", ["anchor"], "What tattoo do you have?", "What's that old mark on your arm?"),
    ("exam", "My chemistry exam is on the twelfth.", "Study hard.", ["chemistry"], "When is my chemistry exam?", "Do I have a test coming up?"),
    ("ring", "I lost my mother's ring in the river.", "I'm so sorry.", ["ring"], "What did I lose in the river?", "Where did that family jewel disappear?"),
    ("tea", "I can't stand green tea.", "Noted.", ["green tea"], "What drink do I dislike?", "Should I order you a cup of matcha?"),
    ("wager", "Garrick bet me ten coins that I couldn't climb the tower.", "And did you?", ["tower"], "What did Garrick bet me?", "Was there a wager about the high building?"),
    ("nickname", "Everyone calls me Sparrow because I'm small.", "It suits you.", ["Sparrow"], "What do people call me?", "What's my nickname?"),
    ("sibling_bday", "My brother Kael's birthday is in March.", "I'll remember.", ["Kael"], "When is Kael's birthday?", "Is my sibling's celebration coming soon?"),
    ("map", "*Mira unrolls an old map and marks a cross near the marsh.*", "Here.", ["map"], "What did you mark on the map?", "Where did you put the X on that chart?"),
    ("vow", "I swear I will find whoever poisoned the well.", "I'll help you.", ["poisoned"], "What did I swear to find?", "Who am I hunting after the contamination?"),
    ("lang", "I speak three languages: Bengali, English and a little French.", "Impressive.", ["Bengali"], "Which languages do I speak?", "Can I translate for the French merchant?"),
]
HELDOUT2_UNKNOWN = ["What did my aunt cook for us last Eid?", "Do you remember the color of my first bicycle?", "Where did we hide the treasure map?", "Who was the stranger at the gate yesterday?",
                    "What did the doctor say about my knee?", "What was the name of the ship we sailed on?"]
