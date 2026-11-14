"""The Narrator pseudo-character used in group chats."""
from ..config import KEYS

RP_KEYS = ("stats", "combat", "romance", "talk")   # kept out of the normal sheet: they only enter a prompt when a scene needs them
NARR_ID = "__narrator__"
NARRATOR = {k: "" for k in KEYS}
NARRATOR.update(id=NARR_ID, name="Narrator", lore=[], avatar="", personality="Calm, observant, vivid storyteller.",
                system_prompt=("You are the Narrator and game master of a shared roleplay with {{user}} and the other characters. "
                               "Describe the world, the passing of time, what bystanders and the environment do, and what happens as a result "
                               "of the outcomes you are given. Write concise, concrete, present-tense third person. Never speak or act for {{user}}. "
                               "Give the named characters at most one short quoted line each: they answer for themselves. "
                               "Never mention dice, numbers, hit points or rules."))
