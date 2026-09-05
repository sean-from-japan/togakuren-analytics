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


class Figures(unittest.TestCase):
    """The two language sets are separate files and drift apart silently.

    A missing English figure is a broken image on GitHub and nothing else here
    notices, because the link checker only sees the files a document happens to
    reference.
    """

    def test_both_language_sets_hold_the_same_figures(self):
        english = {path.name for path in (ROOT / "docs" / "figures" / "en").glob("*.png")}
        japanese = {path.name for path in (ROOT / "docs" / "figures" / "ja").glob("*.png")}
        self.assertTrue(english)
        self.assertEqual(english, japanese)

    def test_no_figure_sits_outside_a_language_folder(self):
        stray = sorted(path.name for path in (ROOT / "docs" / "figures").glob("*.png"))
        self.assertEqual(stray, [])

    def test_each_document_points_at_its_own_language(self):
        for suffix, wrong in (("en", "/figures/ja/"), ("ja", "/figures/en/")):
            for path in ROOT.rglob(f"*.{suffix}.md"):
                if ".git" in path.parts or path.name.startswith("FIGURES"):
                    continue
                with self.subTest(document=path.name):
                    self.assertNotIn(wrong, path.read_text(encoding="utf-8"))


POLITE = re.compile(
    r"(です|ます|ません|でした|ました|ませんでした|でしょう|ください|ましょう)$"
)
#: Plain verb endings: dictionary form, plain past, and the copula.
PLAIN_VERB = re.compile(
    r"(?:である|であった|だった|でない|ではない|ではなかった"
    r"|[ぁ-んァ-ヶ一-龥][うくぐすずつぬぶむる]"
    r"|[ぁ-んァ-ヶ一-龥][た])$"
)
#: い-adjectives, listed rather than matched by shape: a noun ending in い
#: (狙い, 扱い) is 体言止め and must not be flagged.
PLAIN_ADJECTIVE = re.compile(
    r"(?:しい|たい|ない|よい|良い|悪い|多い|少ない|高い|低い|強い|弱い"
    r"|大きい|小さい|長い|短い|早い|速い|遅い|近い|遠い|重い|軽い|薄い|濃い"
    r"|にくい|やすい|づらい|らしい|正しい|新しい|古い|無い)$"
)
#: Nouns ending in a character the verb pattern would otherwise claim.
NOUN_TAIL = re.compile(
    r"(?:ひとつ|一つ|二つ|三つ|四つ|五つ|いくつ|[0-9０-９]つ"
    r"|こと|もの|ため|とおり|通り|はず|まま|うち|ほう|方)$"
)
SKIP_LINE = re.compile(r"^\s*(#|\||```|>|!\[|\*\[|---|\d+\.\s*$)")
TAIL = re.compile(r"(?:[（(][^）)]*[)）]|\[[^\]]*\]\([^)]*\)|\*+|`[^`]*`|\s)+$")


def japanese_sentences(text):
    """(line number, sentence) for prose sentences ending in 。"""
    in_fence = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip() or SKIP_LINE.match(line):
            continue
        prose = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line.strip())
        prose = prose.replace("**", "").replace("`", "")
        for sentence in re.split(r"(?<=[。])", prose):
            sentence = sentence.strip()
            if sentence.endswith("。") and len(sentence) > 4:
                yield number, sentence


def plain_form(sentence):
    """True when a sentence ends in plain-form だ・である rather than です・ます.

    体言止め — ending in a noun — returns False. Used consistently for captions
    and labels it is fine; it is only the plain **verbs and adjectives** that
    clash with surrounding です・ます.
    """
    core = sentence.rstrip()
    core = core[:-1] if core.endswith(("。", "．")) else core
    previous = None
    while core != previous:
        previous = core
        core = TAIL.sub("", core)
    if POLITE.search(core) or NOUN_TAIL.search(core):
        return False
    return bool(PLAIN_VERB.search(core) or PLAIN_ADJECTIVE.search(core))


class JapaneseRegister(unittest.TestCase):
    """Every Japanese document holds one sentence register from top to bottom.

    Drifting out of です・ます for a sentence or two — usually the summarising
    one at the end of a section, because plain form sounds punchier there — is
    the single correction Shion has had to make by hand most often. It reads as
    content-farm Japanese, which is the last impression a research document
    should give. 体言止め is not the problem and is not flagged.
    """

    def test_every_japanese_document_is_written_in_one_register(self):
        for path in ROOT.rglob("*.ja.md"):
            if ".git" in path.parts:
                continue
            departures = [
                (number, sentence)
                for number, sentence in japanese_sentences(path.read_text(encoding="utf-8"))
                if plain_form(sentence)
            ]
            with self.subTest(document=str(path.relative_to(ROOT))):
                self.assertEqual(
                    departures, [],
                    "plain-form sentences inside です・ます prose:\n"
                    + "\n".join(f"  L{n}: {s}" for n, s in departures),
                )

    def test_the_generated_japanese_labels_are_polite_too(self):
        """The documents above are only as consistent as the strings they carry."""
        from togakuren import dashboard, markdown, trends

        tables = [("markdown", markdown.LABELS["ja"]),
                  ("trends", trends.TEXT["ja"]),
                  ("dashboard", dashboard.TEXT["ja"])]
        for name, table in tables:
            for key, value in table.items():
                if not isinstance(value, str):
                    continue
                for sentence in re.split(r"(?<=[。])", value):
                    sentence = sentence.strip()
                    if not sentence.endswith("。") or len(sentence) <= 4:
                        continue
                    with self.subTest(table=name, key=key):
                        self.assertFalse(plain_form(sentence), sentence)


class JapaneseCopy(unittest.TestCase):
    """Keep previously corrected literal translations out of public output."""

    def test_known_translationese_does_not_return(self):
        banned = ("線を引く", "シュート量", "撃つが", "per試合", "部の移動",
                  "効く", "効き", "効か", "効い")
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
