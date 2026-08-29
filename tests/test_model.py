import unittest

from togakuren import model

from . import fixtures


class ParseMinute(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(model.parse_minute("58"), 58)

    def test_half_time_marker(self):
        self.assertEqual(model.parse_minute("HT"), 45)
        self.assertEqual(model.parse_minute("ht"), 45)

    def test_stoppage_time(self):
        self.assertEqual(model.parse_minute("90+2"), 92)
        self.assertEqual(model.parse_minute("90 + 3"), 93)

    def test_superscript_plus_appears_in_the_real_data(self):
        self.assertEqual(model.parse_minute("90⁺5"), 95)

    def test_unparseable(self):
        for value in (None, "", "   ", "later", "??"):
            self.assertIsNone(model.parse_minute(value), value)


class MatchLength(unittest.TestCase):
    def test_declared_length(self):
        self.assertEqual(model.match_length({"matchTime": "90", "extraTime": "0"}), 90)

    def test_extra_time_is_added(self):
        self.assertEqual(model.match_length({"matchTime": "90", "extraTime": "30"}), 120)

    def test_missing_fields_fall_back(self):
        self.assertEqual(model.match_length({}), 90)
        self.assertEqual(model.match_length({"matchTime": None, "extraTime": ""}), 90)


class Appearances(unittest.TestCase):
    def setUp(self):
        self.home, self.away = fixtures.GAME["gameRecords"]

    def rows(self, record):
        return {row["player_id"]: row for row in model.appearances(record, 90)}

    def test_every_starter_and_used_substitute_is_present(self):
        rows = self.rows(self.home)
        self.assertEqual(len(rows), 13)
        self.assertNotIn("a14", rows, "an unused substitute did not play")

    def test_untouched_starter_plays_the_full_match(self):
        self.assertEqual(self.rows(self.home)["a1"]["minutes"], 90)

    def test_substituted_starter_stops_at_the_change(self):
        row = self.rows(self.home)["a2"]
        self.assertEqual((row["on"], row["off"], row["minutes"]), (0, 70, 70))

    def test_substitute_starts_when_they_come_on(self):
        row = self.rows(self.home)["a13"]
        self.assertEqual((row["role"], row["on"], row["minutes"]), ("bench", 70, 20))

    def test_half_time_substitution(self):
        self.assertEqual(self.rows(self.home)["a12"]["minutes"], 45)

    def test_dismissal_ends_the_match_for_that_player(self):
        row = self.rows(self.away)["b5"]
        self.assertEqual((row["off"], row["minutes"]), (30, 30))

    def test_a_yellow_card_does_not_end_the_match(self):
        self.assertEqual(self.rows(self.home)["a3"]["minutes"], 90)

    def test_unparseable_substitution_time_is_skipped_not_guessed(self):
        record = dict(self.away)
        record["substitutions"] = [
            {"value": {"outPlayerId": "b4", "inPlayerId": "b12", "time": "sometime"}}
        ]
        rows = {row["player_id"]: row for row in model.appearances(record, 90)}
        self.assertEqual(rows["b4"]["minutes"], 90)
        self.assertNotIn("b12", rows)


class Shots(unittest.TestCase):
    def test_periods_are_totalled(self):
        rows = {row["player_id"]: row for row in model.shots(fixtures.GAME["gameRecords"][0])}
        self.assertEqual(rows["a2"]["total"], 3)
        self.assertEqual(rows["a2"]["periods"], [0, 3, 0, 0])

    def test_blank_periods_count_as_zero(self):
        record = {"shoots": [{"value": {"playerId": "x", "first": "", "second": None}}]}
        self.assertEqual(model.shots(record)[0]["total"], 0)


class Events(unittest.TestCase):
    def test_goals_cards_and_dismissals_are_separated(self):
        home = model.events(fixtures.GAME["gameRecords"][0], 90)
        away = model.events(fixtures.GAME["gameRecords"][1], 90)
        self.assertEqual(sum(1 for e in home if e["type"] == "goal"), 2)
        self.assertEqual(sum(1 for e in home if e["type"] == "yellow"), 1)
        self.assertEqual([e["type"] for e in away], ["red"])

    def test_stoppage_time_goal_keeps_its_minute(self):
        goals = [e for e in model.events(fixtures.GAME["gameRecords"][0], 90) if e["type"] == "goal"]
        self.assertEqual(sorted(goal["minute"] for goal in goals), [12, 92])


class Roster(unittest.TestCase):
    def test_members_are_flattened(self):
        rows = model.roster(fixtures.TEAMS[0])
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[0]["grade"], "2")

    def test_standings_are_read_from_the_cms_table(self):
        self.assertEqual(model.standings(fixtures.TEAMS[0])["points"], 3)
        self.assertIsNone(model.standings({"rankingData": {}}))
