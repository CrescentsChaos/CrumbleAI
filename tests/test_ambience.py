import unittest

from tests import helpers as h
from crumble import ambience as A, simtime
from crumble.llm import generate_reply
from crumble.prompt import build_messages

C = {"id": "faith", "name": "Faith", "personality": "Calm. Introverted.", "scenario": ""}
M = lambda *t: [{"role": "user" if i % 2 else "assistant", "content": x} for i, x in enumerate(t)]


class DeriveTests(unittest.TestCase):
    def test_place_weather_and_indoors(self):
        a = A.derive(M("We sit in the library. Rain streaks the windows.", "Nice and quiet."))
        self.assertEqual((a["place"]["name"], a["indoors"], a["weather"]), ("the library", True, "rain"))

    def test_stepping_outside_flips_indoors_and_weather_persists(self):
        a = A.derive(M("Rain falls on the library roof.", "ok", "She steps outside into the cold air.", "hm"))
        self.assertIs(a["indoors"], False)
        self.assertEqual(a["weather"], "rain")

    def test_weather_stops_and_negation(self):
        self.assertEqual(A.derive(M("It was raining hard.", "ok", "The rain stops and the sun comes out.", "yay"))["weather"], "clear")
        self.assertEqual(A.derive(M("It isn't raining today.", "ok"))["weather"], "")

    def test_horror_and_tender_levels(self):
        hor = A.derive(M("The abandoned house is silent. A scream, then footsteps behind her. Blood on the wall.", "I'm scared, something is watching us"))
        self.assertEqual(hor["horror"], 2)
        ten = A.derive(M("She leans closer, her breath catching, and he kisses her cheek, then her lips.", "I hold her close and kiss her"))
        self.assertEqual(ten["tender"], 2)
        calm = A.derive(M("Ready for class?", "Yep."))
        self.assertEqual((calm["horror"], calm["tender"]), (0, 0))


class BlockTests(unittest.TestCase):
    def test_horror_block_asks_for_dread_not_jokes(self):
        a = A.derive(M("The abandoned house is silent. A scream, then footsteps behind her. Blood on the wall.", "something is watching us"))
        b = A.block(a, "Faith", "Crescent")
        self.assertIn("HORROR", b)
        self.assertIn("late", b)           # show the threat late
        self.assertIn("cheerful", b)

    def test_indoor_rain_is_heard_not_felt(self):
        b = A.block(A.derive(M("Rain on the bedroom window.", "ok")), "Faith", "Crescent")
        self.assertIn("heard and seen, not felt", b)

    def test_intimacy_defers_to_ceiling(self):
        b = A.block(A.derive(M("She kisses him, lips lingering, and he pulls her close.", "I kiss her back")), "Faith", "Crescent")
        self.assertIn("intimacy ceiling", b)

    def test_in_prompt(self):
        a = A.derive(M("Thunder rolls over the cabin.", "hi"))
        m = build_messages(C, "Crescent", M("Thunder rolls over the cabin.", "hi"), {"mode": "story", "state": {}, "words": (10, 30), "amb": a})
        self.assertIn("[Environment", m[0]["content"])


class GuardTests(unittest.TestCase):
    def test_sun_in_a_storm_and_rain_indoors(self):
        s = A.derive(M("A storm rages over the street.", "hm"))
        self.assertIn("storm", A.env_note("*Sunlight streams over the pavement.* Lovely day.", s))
        i = A.derive(M("In the bedroom, rain taps the glass.", "ok"))
        self.assertIn("indoors", A.env_note("*Rain soaks her hair as she sits on the bed.*", i))
        self.assertEqual(A.env_note("*Rain taps the glass.* Hm.", i), "")

    def test_giggling_in_horror(self):
        a = A.derive(M("Ghost! A scream, blood on the wall, something is behind her.", "run"))
        self.assertIn("horror", A.env_note("*giggles cheerfully* It's fine!", a))

    def test_pipeline_retries_and_boosts(self):
        hist = M("The storm hammers the old house. Thunder, lightning, a scream from the cellar.", "I grab the torch")
        fake = h.install(h.FakeLLM(["*Sunlight streams in as she smiles.* Lovely day.", "*Thunder cracks. Faith freezes, breath shallow.* Did you hear that?"]))
        r = generate_reply({"char": C, "user": "Crescent", "history": hist, "state": {}, "params": {"mode": "story", "think": False, "max_tokens": 200}}, None)
        self.assertEqual(len(fake.calls), 2)
        self.assertIn("Thunder", r["text"])
        self.assertIn("[Environment", fake.calls[0][0]["content"])


if __name__ == "__main__":
    unittest.main()
