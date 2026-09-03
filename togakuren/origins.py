"""Where the players came from, and how much of that survives normalisation.

``squad_members.former_team`` is free text typed by club managers. One column
holds three different things: a high school, a club youth side, or a club youth
side with the school the player actually attended in brackets. 97% of squad rows
carry a value, and there are 2,212 distinct strings behind roughly 1,500 real
schools, so the whole column is worthless until the spellings are collapsed.

The collapsing is where the mistakes live, and one of them is worth naming
because it survived a first pass of this analysis: stripping ``市立``/``県立``
merges 市立船橋 (a national power, 87 rows) with 県立船橋 (an academic school in
the same city, 10 rows). The founding authority is part of the name. What is
written inconsistently is the *place* in front of it — 船橋市立船橋 and 市立船橋
are the same school, 東京都立本所 and 都立本所 are the same school.
"""

import re

# Full-width and half-width brackets both appear, sometimes in the same season.
BRACKET = re.compile(r"[（(]([^）)]*)[）)]")
# A club side names itself: a youth suffix, or the club-name markers FC/SC.
YOUTH = re.compile(r"(ユース|U-?18|Ｕ-?18|・?Y$|ジュニアユース|SC|FC|F\.C|アカデミー)")
SCHOOL_TAIL = re.compile(r"(高等学校|高校|高級学校|高等科|高等部|中等教育学校|学園高|高)$")

#: Old-form characters appear in the squad lists and modern forms in every
#: external source, so 國學院大學久我山 and 国学院久我山 have to meet somewhere.
OLD_NEW = {"學": "学", "國": "国", "廣": "広", "澤": "沢", "眞": "真",
           "惠": "恵", "榮": "栄", "圓": "円", "寶": "宝", "縣": "県"}

#: Schools are written long in squad lists and short everywhere else. Applied in
#: order: the general contractions first, then the few names that have to be put
#: back together afterwards.
CONTRACTIONS = [
    ("高等学校", ""), ("高校", ""),
    ("大学付属", "大"), ("大学附属", "大"), ("大附属", "大"), ("大付属", "大"),
    ("大学", "大"), ("附属", "附"), ("付属", "附"),
    ("商業", "商"), ("工業", "工"), ("農業", "農"), ("実業", "実"),
    ("日本大", "日大"), ("東京都市大", "都市大"),
    ("国学院大久我山", "国学院久我山"),
    ("専修大", "専大"), ("流通経済大附柏", "流通経済大柏"),
]


def normalise_school(name):
    """Canonical school name, with the founding authority kept.

    ``国立高校`` is a school in Kunitachi rather than a national school, so the
    ``私立``/``国立`` prefix only comes off when something follows it. A name
    that *ends* at the authority (``富士市立高等学校``) is a real name and is
    left alone, because removing the place would remove the school.
    """
    s = (name or "").strip().replace("　", "").replace(" ", "")
    s = s.replace("ヶ", "ケ").replace("ヵ", "カ")
    s = re.sub(r"(高等学校|高級学校|高等部|高校)$", "", s)
    s = re.sub(r"^(私立|国立)(?=.)", "", s)
    s = re.sub(r"^.*?(都立|府立|県立|道立|市立|区立|町立|村立|組合立)(?=.)", r"\1", s)
    if not s:
        return s
    return s if s.endswith(("高等科", "中等教育学校")) else s + "高校"


def split_origin(raw):
    """``(club_youth, school)`` from one free-text value. Either may be None."""
    raw = (raw or "").strip()
    if not raw:
        return None, None
    found = BRACKET.search(raw)
    if found:
        outside = BRACKET.sub("", raw).strip()
        inside = found.group(1).strip()
        # 多摩大学目黒高校(多摩大学目黒高校) is somebody typing twice, not a club.
        if normalise_school(outside) == normalise_school(inside):
            return None, normalise_school(outside)
        # Whichever half looks like a school is the school.
        if SCHOOL_TAIL.search(inside) and not SCHOOL_TAIL.search(outside):
            return outside, normalise_school(inside)
        if SCHOOL_TAIL.search(outside) and not SCHOOL_TAIL.search(inside):
            return inside, normalise_school(outside)
        return outside, normalise_school(inside) if inside else None
    if YOUTH.search(raw) and not SCHOOL_TAIL.search(raw):
        return raw, None
    return None, normalise_school(raw)


def match_key(name):
    """Reduce a school name to the form an external list would write it in."""
    s = (name or "").strip().replace("　", "").replace(" ", "")
    s = s.replace("ヶ", "ケ").replace("ヵ", "カ")
    s = "".join(OLD_NEW.get(c, c) for c in s)
    for long_form, short_form in CONTRACTIONS:
        s = s.replace(long_form, short_form)
    return s
