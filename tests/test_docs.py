"""The documents are most of what this repository is, so they get checked too.

A dead link in a README is not caught by anything else here, and this project
has shipped one before: an anchor renamed in a heading while the link that
pointed at it stayed behind.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HEADING = re.compile(r"^#{1,6}\s+(.*)$")
ANCHOR_LINK = re.compile(r"\]\(#([^)]+)\)")
FILE_LINK = re.compile(r"\]\(([^)#:]+\.(?:md|png|svg))(?:#[^)]*)?\)")


def slug(text):
    """GitHub's heading slug: lowercased, spaces to hyphens, punctuation gone."""
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    return "".join("-" if character in " \t"
                   else character if character in "-_" or character.isalnum()
                   else ""
                   for character in text)


def anchors(text):
    """Every anchor the document defines, with GitHub's duplicate suffixes."""
    seen = set()
    for line in text.splitlines():
        found = HEADING.match(line)
        if not found:
            continue
        base = name = slug(found.group(1))
        index = 0
        while name in seen:
            index += 1
            name = f"{base}-{index}"
        seen.add(name)
    return seen


def documents():
    return sorted(path for path in ROOT.rglob("*.md")
                  if ".git" not in path.parts)


class Links(unittest.TestCase):
    def test_every_anchor_link_points_at_a_heading(self):
        for path in documents():
            text = path.read_text(encoding="utf-8")
            defined = anchors(text)
            for found in ANCHOR_LINK.finditer(text):
                with self.subTest(document=path.name, anchor=found.group(1)):
                    self.assertIn(found.group(1), defined)

    def test_every_relative_link_points_at_a_file(self):
        for path in documents():
            text = path.read_text(encoding="utf-8")
            for found in FILE_LINK.finditer(text):
                target = (path.parent / found.group(1)).resolve()
                with self.subTest(document=path.name, link=found.group(1)):
                    self.assertTrue(target.exists())

    def test_the_english_and_japanese_pairs_both_exist(self):
        for path in documents():
            if path.name.endswith(".ja.md"):
                counterpart = path.with_name(path.name[:-len(".ja.md")] + ".en.md")
            elif path.name.endswith(".en.md"):
                counterpart = path.with_name(path.name[:-len(".en.md")] + ".ja.md")
            else:
                continue
            with self.subTest(document=path.name):
                self.assertTrue(counterpart.exists())

    def test_unsuffixed_markdown_is_not_one_side_of_a_language_pair(self):
        for path in documents():
            if path.name.endswith((".en.md", ".ja.md")):
                continue
            if path == ROOT / "README.md":
                text = path.read_text(encoding="utf-8")
                self.assertIn("README.en.md", text)
                self.assertIn("README.ja.md", text)
                continue
            stem = path.with_suffix("")
            with self.subTest(document=path.name):
                self.assertFalse(stem.with_name(stem.name + ".en.md").exists())
                self.assertFalse(stem.with_name(stem.name + ".ja.md").exists())


class JapaneseCopy(unittest.TestCase):
    """Keep previously corrected literal translations out of public output."""

    def test_known_translationese_does_not_return(self):
        banned = ("線を引く", "シュート量", "撃つが", "per試合", "部の移動")
        paths = [ROOT / "README.ja.md", ROOT / "FINDINGS.ja.md"]
        paths += list((ROOT / "docs").glob("*.ja.md"))
        paths += [ROOT / "togakuren" / name
                  for name in ("dashboard.py", "markdown.py", "report.py", "trends.py")]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for phrase in banned:
                with self.subTest(document=path.name, phrase=phrase):
                    self.assertNotIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
