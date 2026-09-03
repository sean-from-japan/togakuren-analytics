"""Cross-season view: everything that only becomes visible over several years.

One season answers "who is good now". Several answer the questions that made
the backfill worth doing — whether a year group's scoring rate is a real pattern
or one season's noise, what promotion actually costs a squad, and how a club
climbed.

Contains no per-player rows by construction, so unlike the dashboard this page
is statistical information throughout and safe to publish as it stands.

The page comes in English and Japanese. Both are written rather than translated,
and every string the charts draw arrives in the JSON payload as ``DATA.t``, so
the drawing code holds no language of its own — which is what makes a committed
figure reproducible in either language from the same command.
"""

import html
import json
from datetime import datetime, timezone

from . import analysis
from .dashboard import CSS, DIVISIONS, division_label

TEXT = {
    "en": {
        "html_lang": "en",
        "title": "Across seasons — togakuren-analytics",
        "heading": "Across seasons",
        "subtitle": "{first}–{last} · {seasons} seasons · {clubs} clubs · generated {when}",
        "banner": "Aggregates only. No individual appears anywhere on this page.",
        "h_seasons": "Every season",
        "cols_seasons": ["Season", "Division", "Teams", "Fixtures", "Played", "Goals/game",
                         "Shots/game", "Conv", "Yellows/game", "Reds"],
        "done": "final",
        "seasons_note": ("Player-level records begin in 2022. 2021 holds results only, so "
                         "shots and conversion are not computed for it."),
        "h_level": "League level over time",
        "level_note": "Faint dots are seasons still being played.",
        "goals_line": "Goals per fixture",
        "shots_line": "Shots per fixture",
        "conversion_line": "Conversion",
        "in_progress": "season in progress",
        "h_grades": "Academic year",
        "grades_title": "Share of minutes (bars) and goals per 90 (dotted)",
        "grades_key": "colour = 1st / 2nd / 3rd / 4th year",
        "grades_tip": "{year}, year {grade} — {share} of the minutes / {players} players / {goals} goals",
        "grades_note": ("Bars are the share of minutes, stacked to 100%; the dotted lines are "
                        "goals per 90. Year groups turn over annually, so one season's movement "
                        "is a cohort rather than a trend."),
        "all_divisions": "all",
        "h_trajectory": "A club across divisions",
        "trajectory_title": "{club}: division by season",
        "trajectory_key": "circle size = points per game",
        "tier_label": "level {n}",
        "trajectory_note": ("The axis is league level, not division name. A division does not keep its level here: the Challenge League was the third level from 2022 and the fourth from 2025, so a club can move level while its division name stays put."),
        "trajectory_tip": "{year} {division} — {w}-{d}-{l}, {points} points ({ppg} per game)",
        "cols_club": ["Season", "Division", "P", "W-D-L", "Pts", "Pts/game", "GF", "GD"],
        "h_moves": "What a division change does",
        "moves_title": "Points per game either side of a division change",
        "moves_x": "the season before the move →",
        "moves_y": "after the move ↑   orange = promoted / blue = relegated",
        "moves_tip": "{club} {from_year} {from_division} → {to_year} {to_division} ({direction}) {before} → {after}",
        "promoted": "promoted",
        "relegated": "relegated",
        "part_season": " (season in progress)",
        "card_promoted": "points per game the season after promotion ({n} cases)",
        "card_relegated": "points per game the season after relegation ({n} cases)",
        "moves_note": ("Above the diagonal means the club took more points per game after the "
                       "move than before it. Faint dots are seasons still being played and are "
                       "left out of the two averages."),
        "footer": ("Source: the Tokyo University Football Association's public content API. "
                   "Aggregates only."),
    },
    "ja": {
        "html_lang": "ja",
        "title": "シーズン横断 — togakuren-analytics",
        "heading": "シーズン横断分析",
        "subtitle": "{first}–{last} · {seasons}シーズン · {clubs}クラブ · 生成 {when}",
        "banner": "このページは集計値のみで構成されており、選手個人の行を一切含まない。",
        "h_seasons": "シーズン一覧",
        "cols_seasons": ["年度", "部", "チーム", "試合", "消化", "得点/試合",
                         "シュート/試合", "決定率", "警告/試合", "退場"],
        "done": "完了",
        "seasons_note": ("選手単位の記録は2022年から。2021年は結果のみのため、"
                         "シュート数と決定率は算出していない。"),
        "h_level": "リーグ水準の推移",
        "level_note": "薄い点は消化途中のシーズン。",
        "goals_line": "1試合あたりの得点",
        "shots_line": "1試合あたりのシュート数",
        "conversion_line": "決定率",
        "in_progress": "シーズン途中",
        "h_grades": "学年別の出場と得点",
        "grades_title": "出場時間の割合（棒）と90分あたり得点（点線）",
        "grades_key": "色 = 学年 1 / 2 / 3 / 4",
        "grades_tip": "{year} {grade}年 — 出場時間 {share} / {players}人 / {goals}得点",
        "grades_note": ("棒が出場時間の割合（積み上げで100%）、点線が90分あたり得点。"
                        "学年構成は毎年入れ替わるため、1シーズンだけの上下は世代差であって"
                        "傾向ではない。"),
        "all_divisions": "全部",
        "h_trajectory": "クラブの所属部推移",
        "trajectory_title": "{club}の所属部推移",
        "trajectory_key": "円の大きさ = 1試合平均勝点",
        "tier_label": "レベル{n}",
        "trajectory_note": ("縦軸は部の名前ではなくリーグの階層。この期間は部の名前と階層が一致しない。チャレンジリーグは2022年から3層目、2025年から4層目で、部の名前が変わらないまま階層だけ動いたクラブがある。"),
        "trajectory_tip": "{year} {division} — {w}勝{d}分{l}敗、勝点{points}（1試合 {ppg}）",
        "cols_club": ["年度", "部", "試合", "勝-分-敗", "勝点", "1試合平均", "得点", "得失"],
        "h_moves": "昇降格の影響",
        "moves_title": "昇降格前後の1試合平均勝点",
        "moves_x": "昇降格前シーズンの1試合平均勝点 →",
        "moves_y": "縦軸: 昇降格後　橙=昇格 / 青=降格",
        "moves_tip": "{club} {from_year}{from_division} → {to_year}{to_division}（{direction}）{before} → {after}",
        "promoted": "昇格",
        "relegated": "降格",
        "part_season": "　※シーズン途中",
        "card_promoted": "昇格した翌シーズンの1試合あたり勝点（{n}件）",
        "card_relegated": "降格した翌シーズンの1試合あたり勝点（{n}件）",
        "moves_note": ("対角線より上なら、昇降格後に1試合あたりの勝点が伸びたということ。"
                       "薄い点は消化途中のシーズンで、上の平均には入れていない。"),
        "footer": "出典: 東京都大学サッカー連盟 公開コンテンツAPI。集計値のみを掲載している。",
    },
}

SCRIPT = r"""
const DATA = JSON.parse(document.getElementById("payload").textContent);
const T = DATA.t;
const NS = "http://www.w3.org/2000/svg";
const TIER_COLOURS = ["var(--accent)", "var(--warm)", "var(--cool)", "var(--plum)", "#8a8f98"];
const fmt = (v, d = 2) => (v == null ? "-" : Number(v).toFixed(d));
const fill = (template, values) =>
  template.replace(/\{(\w+)\}/g, (_, key) => values[key] == null ? "" : values[key]);

function el(name, attrs, text) {
  const node = document.createElementNS(NS, name);
  for (const key in attrs) node.setAttribute(key, attrs[key]);
  if (text != null) node.textContent = text;
  return node;
}
function svg(w, h, label) {
  const node = el("svg", { viewBox: `0 0 ${w} ${h}`, role: "img" });
  if (label) node.appendChild(el("title", {}, label));
  return node;
}
function axes(node, L, R, top, B, W, H, ticks, labels) {
  for (const [value, y] of ticks) {
    node.appendChild(el("line", { x1: L, x2: W - R, y1: y, y2: y,
      stroke: "currentColor", "stroke-opacity": .12 }));
    node.appendChild(el("text", { x: L - 6, y: y + 4, "font-size": 10, "text-anchor": "end",
      fill: "currentColor", "fill-opacity": .55 }, value));
  }
  for (const [text, x] of labels) {
    node.appendChild(el("text", { x, y: H - B + 16, "font-size": 10, "text-anchor": "middle",
      fill: "currentColor", "fill-opacity": .55 }, text));
  }
}

/* One line per division. Divisions come and go between seasons, so a line stops
   rather than pretending a value it does not have. */
function divisionLines(host, key, title, digits) {
  const W = 560, H = 250, L = 44, R = 108, top = 26, B = 30;
  const node = svg(W, H, title);
  const years = DATA.years;
  const rows = DATA.seasons.filter(s => s[key] != null);
  if (!rows.length) { host.replaceChildren(); return; }
  const values = rows.map(s => s[key]);
  const lo = Math.min(...values) * 0.9, hi = Math.max(...values) * 1.05;
  const x = year => L + (W - L - R) * years.indexOf(year) / Math.max(1, years.length - 1);
  const y = v => top + (H - top - B) * (1 - (v - lo) / (hi - lo || 1));

  const ticks = [];
  for (let i = 0; i <= 3; i++) {
    const v = lo + (hi - lo) * i / 3;
    ticks.push([fmt(v, digits), y(v)]);
  }
  axes(node, L, R, top, B, W, H, ticks, years.map(yr => [yr, x(yr)]));
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, "font-weight": 600,
    fill: "currentColor" }, title));

  const byDivision = {};
  for (const season of rows) (byDivision[season.division] ||= []).push(season);
  const labels = [];
  /* Colour by division, not by the level it happened to start on: the third
     division and the Challenge League both began life at level three, and
     colouring by level drew them as the same green line. */
  Object.entries(byDivision).forEach(([division, seasons]) => {
    seasons.sort((a, b) => a.year.localeCompare(b.year));
    const colour = TIER_COLOURS[(DATA.division_colours[division] || 0) % TIER_COLOURS.length];
    node.appendChild(el("polyline", {
      points: seasons.map(s => `${x(s.year)},${y(s[key])}`).join(" "),
      fill: "none", stroke: colour, "stroke-width": 1.8, "stroke-opacity": .9 }));
    for (const season of seasons) {
      const dot = el("circle", { cx: x(season.year), cy: y(season[key]), r: season.complete < .95 ? 3 : 4,
        fill: colour, "fill-opacity": season.complete < .95 ? .35 : 1 });
      dot.appendChild(el("title", {},
        `${season.year} ${season.label} — ${fmt(season[key], digits)}` +
        (season.complete < .95 ? ` (${T.in_progress})` : "")));
      node.appendChild(dot);
    }
    const last = seasons[seasons.length - 1];
    labels.push({ label: last.label, colour, x: x(last.year) + 7, y: y(last[key]) + 3.5 });
  });
  /* Divisions that end a season on the same value collide; nudge them apart. */
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].y - labels[i - 1].y < 12) labels[i].y = labels[i - 1].y + 12;
  }
  for (const label of labels) {
    node.appendChild(el("text", { x: label.x, y: label.y, "font-size": 10,
      fill: label.colour }, label.label));
  }
  host.replaceChildren(node);
}

/* Minutes share as stacked columns, scoring rate as a line over the top: the
   question is whether a year group plays more *and* scores more. */
function gradeChart(host, tier) {
  const rows = DATA.grades[tier] || [];
  const W = 560, H = 280, L = 40, R = 40, top = 28, B = 42;
  const node = svg(W, H, T.grades_title);
  if (!rows.length) { host.replaceChildren(node); return; }
  const years = [...new Set(rows.map(r => r.year))].sort();
  const slot = (W - L - R) / years.length;
  const plot = H - top - B;
  const maxRate = Math.max(...rows.map(r => r.goals_per_90)) * 1.15 || 1;

  years.forEach((year, i) => {
    const yearRows = rows.filter(r => r.year === year).sort((a, b) => a.grade.localeCompare(b.grade));
    let offset = 0;
    yearRows.forEach(row => {
      const height = plot * row.minutes_share;
      const rect = el("rect", { x: L + i * slot + slot * .18, y: top + plot - offset - height,
        width: slot * .44, height: Math.max(height, .6),
        fill: TIER_COLOURS[(Number(row.grade) - 1) % TIER_COLOURS.length], "fill-opacity": .75 });
      rect.appendChild(el("title", {}, fill(T.grades_tip, {
        year, grade: row.grade, share: (row.minutes_share * 100).toFixed(1) + "%",
        players: row.players, goals: row.goals })));
      node.appendChild(rect);
      offset += height;
    });
    node.appendChild(el("text", { x: L + i * slot + slot / 2, y: H - B + 16, "font-size": 10,
      "text-anchor": "middle", fill: "currentColor", "fill-opacity": .55 }, year));
  });

  for (const grade of ["1", "2", "3", "4"]) {
    const points = years.map(year => {
      const row = rows.find(r => r.year === year && r.grade === grade);
      return row ? `${L + years.indexOf(year) * slot + slot * .72},${top + plot * (1 - row.goals_per_90 / maxRate)}` : null;
    }).filter(Boolean);
    if (points.length < 2) continue;
    node.appendChild(el("polyline", { points: points.join(" "), fill: "none",
      stroke: TIER_COLOURS[(Number(grade) - 1) % TIER_COLOURS.length],
      "stroke-width": 1.6, "stroke-dasharray": "3 2" }));
  }
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, "font-weight": 600,
    fill: "currentColor" }, T.grades_title));
  node.appendChild(el("text", { x: W, y: H - 6, "font-size": 9.5, "text-anchor": "end",
    fill: "currentColor", "fill-opacity": .5 }, T.grades_key));
  host.replaceChildren(node);
}

/* Tier on an inverted axis so promotion reads as the line going up. */
function trajectory(host, club) {
  const W = 560, H = 210, L = 62, R = 30, top = 26, B = 34;
  const node = svg(W, H, fill(T.trajectory_title, { club: club.name }));
  const years = DATA.years;
  const maxTier = DATA.tiers.length;
  const x = year => L + (W - L - R) * years.indexOf(year) / Math.max(1, years.length - 1);
  const y = tier => top + (H - top - B) * (tier - 1) / (maxTier - 1);

  DATA.tiers.forEach((name, i) => {
    node.appendChild(el("line", { x1: L, x2: W - R, y1: y(i + 1), y2: y(i + 1),
      stroke: "currentColor", "stroke-opacity": .12 }));
    node.appendChild(el("text", { x: L - 6, y: y(i + 1) + 4, "font-size": 10, "text-anchor": "end",
      fill: "currentColor", "fill-opacity": .55 }, name));
  });
  for (const year of years) {
    node.appendChild(el("text", { x: x(year), y: H - B + 16, "font-size": 10, "text-anchor": "middle",
      fill: "currentColor", "fill-opacity": .55 }, year));
  }
  const seasons = club.seasons;
  node.appendChild(el("polyline", { points: seasons.map(s => `${x(s.year)},${y(s.tier)}`).join(" "),
    fill: "none", stroke: "var(--warm)", "stroke-width": 2 }));
  for (const season of seasons) {
    const dot = el("circle", { cx: x(season.year), cy: y(season.tier),
      r: 4 + 5 * season.points_per_game / 3, fill: "var(--warm)", "fill-opacity": .45,
      stroke: "var(--warm)" });
    dot.appendChild(el("title", {}, fill(T.trajectory_tip, {
      year: season.year, division: season.label, w: season.win, d: season.draw,
      l: season.lose, points: season.points, ppg: fmt(season.points_per_game) })));
    node.appendChild(dot);
  }
  node.appendChild(el("text", { x: W - R, y: 12, "font-size": 9.5, "text-anchor": "end",
    fill: "currentColor", "fill-opacity": .5 }, T.trajectory_key));
  host.replaceChildren(node);
}

/* Before against after. The diagonal is "nothing changed"; distance from it is
   what the division change cost or gave. */
function moves(host) {
  const W = 500, H = 330, P = 44;
  const node = svg(W, H, T.moves_title);
  const span = W - P * 2;
  const x = v => P + span * v / 3;
  const y = v => H - P - (H - P * 2) * v / 3;

  node.appendChild(el("line", { x1: x(0), y1: y(0), x2: x(3), y2: y(3),
    stroke: "currentColor", "stroke-opacity": .25, "stroke-dasharray": "4 3" }));
  for (let v = 0; v <= 3; v++) {
    node.appendChild(el("text", { x: x(v), y: H - P + 15, "font-size": 10, "text-anchor": "middle",
      fill: "currentColor", "fill-opacity": .55 }, v));
    node.appendChild(el("text", { x: P - 8, y: y(v) + 4, "font-size": 10, "text-anchor": "end",
      fill: "currentColor", "fill-opacity": .55 }, v));
  }
  for (const move of DATA.moves) {
    const up = move.direction === "promoted";
    const dot = el("circle", { cx: x(move.ppg_before), cy: y(move.ppg_after), r: 5,
      fill: up ? "var(--warm)" : "var(--accent)", "fill-opacity": move.complete_after < .95 ? .3 : .7,
      stroke: up ? "var(--warm)" : "var(--accent)" });
    dot.appendChild(el("title", {}, fill(T.moves_tip, {
      club: move.name, from_year: move.from_year, from_division: move.from_label,
      to_year: move.to_year, to_division: move.to_label,
      direction: up ? T.promoted : T.relegated,
      before: fmt(move.ppg_before), after: fmt(move.ppg_after),
    }) + (move.complete_after < .95 ? T.part_season : "")));
    node.appendChild(dot);
  }
  /* The two captions carry the meaning of both axes, and at the tick labels'
     opacity they were faint enough to disappear from a screenshot of this
     element. They are drawn at full strength instead. */
  node.appendChild(el("text", { x: W / 2, y: H - 6, "font-size": 11, "text-anchor": "middle",
    fill: "currentColor" }, T.moves_x));
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11,
    fill: "currentColor" }, T.moves_y));
  host.replaceChildren(node);
}

divisionLines(document.getElementById("goals-line"), "goals_per_game", T.goals_line, 2);
divisionLines(document.getElementById("shots-line"), "shots_per_game", T.shots_line, 1);
divisionLines(document.getElementById("conv-line"), "conversion", T.conversion_line, 3);
moves(document.getElementById("moves"));

let tier = DATA.default_tier;
function selectTier(value) {
  tier = value;
  for (const button of document.querySelectorAll("#tiers button")) {
    button.setAttribute("aria-pressed", String(button.dataset.tier === value));
  }
  gradeChart(document.getElementById("grades"), value);
}
for (const button of document.querySelectorAll("#tiers button")) {
  button.addEventListener("click", () => selectTier(button.dataset.tier));
}
selectTier(tier);

const picker = document.getElementById("club");
function selectClub(teamId) {
  const club = DATA.clubs.find(c => c.team_id === teamId);
  trajectory(document.getElementById("trajectory"), club);
  const body = document.getElementById("club-rows");
  body.replaceChildren();
  for (const season of club.seasons) {
    const row = body.insertRow();
    for (const [value, left] of [[season.year, 1], [season.label, 1], [season.played, 0],
        [`${season.win}-${season.draw}-${season.lose}`, 0], [season.points, 0],
        [fmt(season.points_per_game), 0], [season.goals_for, 0], [season.goal_difference, 0]]) {
      const cell = row.insertCell();
      cell.textContent = value;
      if (left) cell.className = "l";
    }
  }
}
picker.addEventListener("change", () => selectClub(picker.value));
selectClub(picker.value);
"""


def _e(value):
    return html.escape("" if value is None else str(value))


def build(conn, focus_team_id=None, lang="en"):
    """Render the cross-season page and return the HTML source."""
    if lang not in TEXT:
        raise ValueError(f"unsupported language: {lang}")
    text = TEXT[lang]
    seasons = analysis.season_summary(conn)
    if not seasons:
        raise ValueError("no league seasons in this database")
    clubs = [club for club in analysis.club_trajectories(conn) if club["seasons"]]
    # A club whose division stayed the same while the ladder moved under it
    # (the 2025 reorganisation) has not changed division, so it belongs in
    # neither column. See analysis.season_ladder.
    moves = [m for m in analysis.division_moves(conn, clubs) if m["moved"]]
    years = sorted({season["year"] for season in seasons})

    for season in seasons:
        season["label"] = division_label(season["division"], lang)
    for club in clubs:
        for season in club["seasons"]:
            season["label"] = division_label(season["division"], lang)
    for move in moves:
        move["from_label"] = division_label(move["from_division"], lang)
        move["to_label"] = division_label(move["to_division"], lang)

    grades = {}
    for division in DIVISIONS:
        rows = analysis.grade_trend(conn, division=division)
        if rows:
            grades[division] = rows
    grades["all"] = analysis.grade_trend(conn)

    payload = {
        "years": years, "seasons": seasons, "clubs": clubs, "moves": moves, "grades": grades,
        "tiers": [text["tier_label"].format(n=i + 1) for i in range(len(DIVISIONS))],
        "division_colours": {name: index for index, name in enumerate(DIVISIONS)},
        "default_tier": next((d for d in DIVISIONS if d in grades), "all"),
        "t": text,
    }

    default_club = None
    if focus_team_id:
        default_club = next((c for c in clubs if c["team_id"] == focus_team_id), None)
    default_club = default_club or max(clubs, key=lambda c: len(c["seasons"]))

    seasons_word = "季" if lang == "ja" else " seasons"
    options = "".join(
        f'<option value="{_e(club["team_id"])}"'
        f'{" selected" if club is default_club else ""}>'
        f'{_e(club["name"])} ({len(club["seasons"])}{seasons_word})</option>'
        for club in sorted(clubs, key=lambda c: (c["seasons"][-1]["tier"], c["name"] or ""))
    )
    tier_buttons = "".join(
        f'<button type="button" data-tier="{_e(key)}" aria-pressed="false">'
        f'{_e(text["all_divisions"] if key == "all" else division_label(key, lang))}</button>'
        for key in list(DIVISIONS) + ["all"]
        if key in grades
    )

    season_row_parts = []
    for row in seasons:
        played = text["done"] if row["complete"] > 0.95 else "{:.0%}".format(row["complete"])
        shots = "-" if row["shots_per_game"] is None else "{:.1f}".format(row["shots_per_game"])
        conversion = "-" if row["conversion"] is None else "{:.3f}".format(row["conversion"])
        season_row_parts.append(
            "<tr>"
            f'<td class="l">{_e(row["year"])}</td><td class="l">{_e(row["label"])}</td>'
            f'<td>{row["teams"]}</td><td>{row["games"]}</td><td>{played}</td>'
            f'<td>{row["goals_per_game"]:.2f}</td><td>{shots}</td><td>{conversion}</td>'
            f'<td>{row["yellows_per_game"]:.2f}</td><td>{row["reds"]}</td>'
            "</tr>"
        )
    season_rows = "".join(season_row_parts)

    done = [m for m in moves if m["complete_after"] > 0.95]
    summary = ""
    for key, direction in (("card_promoted", "promoted"), ("card_relegated", "relegated")):
        group = [m for m in done if m["direction"] == direction]
        if not group:
            continue
        mean = sum(m["delta"] for m in group) / len(group)
        summary += (f'<div class="card"><b>{mean:+.2f}</b>'
                    f'<span>{_e(text[key].format(n=len(group)))}</span></div>')

    def head(columns):
        cells = []
        for index, column in enumerate(columns):
            cells.append(f'<th class="l">{_e(column)}</th>' if index < 2
                         else f"<th>{_e(column)}</th>")
        return "".join(cells)

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    subtitle = text["subtitle"].format(
        first=years[0], last=years[-1], seasons=len(seasons), clubs=len(clubs), when=generated)
    return f"""<!doctype html>
<html lang="{text['html_lang']}"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(text['title'])}</title>
<style>{CSS}</style>
</head><body><main>
<h1>{_e(text['heading'])}</h1>
<p class="sub">{_e(subtitle)} · togakuren-analytics</p>
<div class="banner">{_e(text['banner'])}</div>

<h2>{_e(text['h_seasons'])}</h2>
<div class="scroll"><table>
<thead><tr>{head(text['cols_seasons'])}</tr></thead>
<tbody>{season_rows}</tbody></table></div>
<p class="note">{_e(text['seasons_note'])}</p>

<h2>{_e(text['h_level'])}</h2>
<div class="grid">
  <div id="goals-line"></div>
  <div id="shots-line"></div>
</div>
<div id="conv-line"></div>
<p class="note">{_e(text['level_note'])}</p>

<h2>{_e(text['h_grades'])}</h2>
<div class="tabs" id="tiers">{tier_buttons}</div>
<div id="grades"></div>
<p class="note">{_e(text['grades_note'])}</p>

<h2>{_e(text['h_trajectory'])}</h2>
<p class="sub"><select id="club">{options}</select></p>
<div id="trajectory"></div>
<p class="note">{_e(text['trajectory_note'])}</p>
<div class="scroll"><table>
<thead><tr>{head(text['cols_club'])}</tr></thead>
<tbody id="club-rows"></tbody></table></div>

<h2>{_e(text['h_moves'])}</h2>
<div class="cards">{summary}</div>
<div id="moves"></div>
<p class="note">{_e(text['moves_note'])}</p>

<footer>{_e(text['footer'])}</footer>
</main>
<script id="payload" type="application/json">{json.dumps(payload, ensure_ascii=False).replace('<', chr(92) + 'u003c')}</script>
<script>{SCRIPT}</script>
</body></html>
"""
