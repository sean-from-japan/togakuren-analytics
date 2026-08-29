import unittest

from togakuren import privacy


class Labels(unittest.TestCase):
    def test_full_mode_returns_the_name(self):
        self.assertEqual(privacy.label("x1", "Alpha Player", "full"), "Alpha Player")

    def test_full_mode_falls_back_to_the_id(self):
        self.assertEqual(privacy.label("x1", None, "full"), "x1")

    def test_initials_handle_ascii_and_ideographic_spaces(self):
        self.assertEqual(privacy.label("x1", "Alpha Player", "initials"), "A.P.")
        self.assertEqual(privacy.label("x1", "山田　太郎", "initials"), "山.太.")

    def test_pseudonyms_are_stable_for_one_salt(self):
        salt = privacy.new_salt()
        first = privacy.label("x1", "Alpha", "pseudonym", salt)
        self.assertEqual(first, privacy.label("x1", "Different Name", "pseudonym", salt))
        self.assertTrue(first.startswith("P-"))

    def test_pseudonyms_differ_between_salts(self):
        self.assertNotEqual(
            privacy.label("x1", None, "pseudonym", "a" * 32),
            privacy.label("x1", None, "pseudonym", "b" * 32),
        )

    def test_pseudonym_without_a_salt_is_refused(self):
        with self.assertRaises(privacy.PrivacyError):
            privacy.label("x1", None, "pseudonym")

    def test_aggregate_mode_emits_nothing_per_person(self):
        with self.assertRaises(privacy.PrivacyError):
            privacy.label("x1", "Alpha", "aggregate")

    def test_unknown_mode(self):
        with self.assertRaises(privacy.PrivacyError):
            privacy.label("x1", "Alpha", "redacted")


class KAnonymity(unittest.TestCase):
    ROWS = [
        {"team": "Alpha", "position": "MF", "apps": 10},
        {"team": "Alpha", "position": "MF", "apps": 10},
        {"team": "Alpha", "position": "DF", "apps": 3},
        {"team": "Beta", "position": "MF", "apps": 10},
    ]

    def test_smallest_group_sets_k(self):
        result = privacy.k_anonymity(self.ROWS, ["team", "position"])
        self.assertEqual(result["k"], 1)
        self.assertEqual(result["unique"], 2)
        self.assertEqual(result["total"], 4)

    def test_coarser_identifiers_raise_k(self):
        self.assertEqual(privacy.k_anonymity(self.ROWS, ["team"])["k"], 1)
        self.assertEqual(privacy.k_anonymity(self.ROWS, ["position"])["k"], 1)

    def test_adding_a_column_can_only_lower_k(self):
        coarse = privacy.k_anonymity(self.ROWS, ["team"])
        fine = privacy.k_anonymity(self.ROWS, ["team", "position", "apps"])
        self.assertLessEqual(fine["k"], coarse["k"])

    def test_empty_input(self):
        self.assertEqual(privacy.k_anonymity([], ["team"])["total"], 0)


class PublicSafety(unittest.TestCase):
    def test_names_and_initials_are_refused(self):
        for mode in ("full", "initials"):
            with self.assertRaises(privacy.PrivacyError, msg=mode):
                privacy.check_public_safe(mode)

    def test_pseudonym_and_aggregate_are_allowed(self):
        self.assertIsNone(privacy.check_public_safe("aggregate"))
        self.assertIsNone(privacy.check_public_safe("pseudonym"))

    def test_pseudonym_still_reports_residual_identifiability(self):
        result = privacy.check_public_safe("pseudonym", KAnonymity.ROWS)
        self.assertEqual(result["k"], 1)


class DataLocation(unittest.TestCase):
    def test_override_is_honoured(self):
        import os
        from importlib import reload
        from pathlib import Path

        from togakuren import paths

        root = Path("example-togakuren").resolve()
        os.environ["TOGAKUREN_HOME"] = str(root)
        try:
            reload(paths)
            self.assertEqual(paths.database(), root / "togakuren.sqlite3")
            self.assertEqual(paths.cache(), root / "cache")
        finally:
            del os.environ["TOGAKUREN_HOME"]
            reload(paths)

    def test_default_is_outside_the_working_directory(self):
        from pathlib import Path

        from togakuren import paths

        self.assertFalse(str(paths.database()).startswith(str(Path.cwd())))
