"""Cross-season view: everything that only becomes visible over several years.

One season answers "who is good now". Several answer the questions that made
the backfill worth doing — whether a year group's scoring rate is a real pattern
or one season's noise, what promotion actually costs a squad, and how a club
climbed.

Contains no per-player rows by construction, so unlike the dashboard this page
is statistical information throughout and safe to publish as it stands.
"""

import html
import json
from datetime import datetime, timezone

from . import analysis
from .dashboard import CSS

SCRIPT = r"""
const DATA = JSON.parse(document.getElementById("payload").textContent);
const NS = "http://www.w3.org/2000/svg";
const TIER_COLOURS = ["var(--accent)", "var(--warm)", "var(--cool)", "var(--plum)", "#8a8f98"];
const fmt = (v, d = 2) => (v == null ? "-" : Number(v).toFixed(d));

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
function axes(node, L, R, T, B, W, H, ticks, labels) {
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
  const W = 560, H = 250, L = 44, R = 108, T = 26, B = 30;
  const node = svg(W, H, title);
  const years = DATA.years;
  const rows = DATA.seasons.filter(s => s[key] != null);
  if (!rows.length) { host.replaceChildren(); return; }
  const values = rows.map(s => s[key]);
  const lo = Math.min(...values) * 0.9, hi = Math.max(...values) * 1.05;
  const x = year => L + (W - L - R) * years.indexOf(year) / Math.max(1, years.length - 1);
  const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));

  const ticks = [];
  for (let i = 0; i <= 3; i++) {
    const v = lo + (hi - lo) * i / 3;
    ticks.push([fmt(v, digits), y(v)]);
  }
  axes(node, L, R, T, B, W, H, ticks, years.map(yr => [yr, x(yr)]));
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, "font-weight": 600,
    fill: "currentColor" }, title));

  const byDivision = {};
  for (const season of rows) (byDivision[season.division] ||= []).push(season);
  const labels = [];
  Object.entries(byDivision).forEach(([division, seasons], i) => {
    seasons.sort((a, b) => a.year.localeCompare(b.year));
    const colour = TIER_COLOURS[(seasons[0].tier - 1) % TIER_COLOURS.length];
    node.appendChild(el("polyline", {
      points: seasons.map(s => `${x(s.year)},${y(s[key])}`).join(" "),
      fill: "none", stroke: colour, "stroke-width": 1.8, "stroke-opacity": .9 }));
    for (const season of seasons) {
      const dot = el("circle", { cx: x(season.year), cy: y(season[key]), r: season.complete < .95 ? 3 : 4,
        fill: colour, "fill-opacity": season.complete < .95 ? .35 : 1 });
      dot.appendChild(el("title", {},
        `${season.year} ${season.division} — ${fmt(season[key], digits)}${season.complete < .95 ? " (season in progress)" : ""}`));
      node.appendChild(dot);
    }
    const last = seasons[seasons.length - 1];
    labels.push({ division, colour, x: x(last.year) + 7, y: y(last[key]) + 3.5 });
  });
  /* Divisions that end a season on the same value collide; nudge them apart. */
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].y - labels[i - 1].y < 12) labels[i].y = labels[i - 1].y + 12;
  }
  for (const label of labels) {
    node.appendChild(el("text", { x: label.x, y: label.y, "font-size": 10,
      fill: label.colour }, label.division));
  }
  host.replaceChildren(node);
}

/* Minutes share as stacked columns, scoring rate as a line over the top: the
   question is whether a year group plays more *and* scores more. */
function gradeChart(host, tier) {
  const rows = DATA.grades[tier] || [];
  const W = 560, H = 280, L = 40, R = 40, T = 28, B = 42;
  const node = svg(W, H, "学年別の出場時間割合と得点率");
  if (!rows.length) { host.replaceChildren(node); return; }
  const years = [...new Set(rows.map(r => r.year))].sort();
  const slot = (W - L - R) / years.length;
  const plot = H - T - B;
  const maxRate = Math.max(...rows.map(r => r.goals_per_90)) * 1.15 || 1;

  years.forEach((year, i) => {
    const yearRows = rows.filter(r => r.year === year).sort((a, b) => a.grade.localeCompare(b.grade));
    let offset = 0;
    yearRows.forEach(row => {
      const height = plot * row.minutes_share;
      const rect = el("rect", { x: L + i * slot + slot * .18, y: T + plot - offset - height,
        width: slot * .44, height: Math.max(height, .6),
        fill: TIER_COLOURS[(Number(row.grade) - 1) % TIER_COLOURS.length], "fill-opacity": .75 });
      rect.appendChild(el("title", {},
        `${year} ${row.grade}年 — 出場時間 ${(row.minutes_share * 100).toFixed(1)}% / ${row.players}人 / ${row.goals}得点`));
      node.appendChild(rect);
      offset += height;
    });
    node.appendChild(el("text", { x: L + i * slot + slot / 2, y: H - B + 16, "font-size": 10,
      "text-anchor": "middle", fill: "currentColor", "fill-opacity": .55 }, year));
  });

  for (const grade of ["1", "2", "3", "4"]) {
    const points = years.map(year => {
      const row = rows.find(r => r.year === year && r.grade === grade);
      return row ? `${L + years.indexOf(year) * slot + slot * .72},${T + plot * (1 - row.goals_per_90 / maxRate)}` : null;
    }).filter(Boolean);
    if (points.length < 2) continue;
    node.appendChild(el("polyline", { points: points.join(" "), fill: "none",
      stroke: TIER_COLOURS[(Number(grade) - 1) % TIER_COLOURS.length],
      "stroke-width": 1.6, "stroke-dasharray": "3 2" }));
  }
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, "font-weight": 600,
    fill: "currentColor" }, "出場時間の割合（棒）と90分あたり得点（点線）"));
  node.appendChild(el("text", { x: W, y: H - 6, "font-size": 9.5, "text-anchor": "end",
    fill: "currentColor", "fill-opacity": .5 }, "色 = 学年 1 / 2 / 3 / 4"));
  host.replaceChildren(node);
}

/* Tier on an inverted axis so promotion reads as the line going up. */
function trajectory(host, club) {
  const W = 560, H = 210, L = 62, R = 30, T = 26, B = 34;
  const node = svg(W, H, `${club.name}の所属部推移`);
  const years = DATA.years;
  const maxTier = 5;
  const x = year => L + (W - L - R) * years.indexOf(year) / Math.max(1, years.length - 1);
  const y = tier => T + (H - T - B) * (tier - 1) / (maxTier - 1);

  ["1部", "2部", "3部", "4部", "チャレンジ"].forEach((name, i) => {
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
    dot.appendChild(el("title", {},
      `${season.year} ${season.division} — ${season.win}-${season.draw}-${season.lose}, 勝点${season.points} (1試合 ${fmt(season.points_per_game)})`));
    node.appendChild(dot);
  }
  node.appendChild(el("text", { x: W - R, y: 12, "font-size": 9.5, "text-anchor": "end",
    fill: "currentColor", "fill-opacity": .5 }, "円の大きさ = 1試合平均勝点"));
  host.replaceChildren(node);
}

/* Before against after. The diagonal is "nothing changed"; distance from it is
   what the division change cost or gave. */
function moves(host) {
  const W = 500, H = 330, P = 44;
  const node = svg(W, H, "昇降格前後の1試合平均勝点");
  const span = W - P * 2;
  const x = v => P + span * v / 3;
  const y = v => H - P - (H - P * 2) * v / 3;

  node.appendChild(el("line", { x1: x(0), y1: y(0), x2: x(3), y2: y(3),
    stroke: "currentColor", "stroke-opacity": .25, "stroke-dasharray": "4 3" }));
  for (let v = 0; v <= 3; v++) {
    node.appendChild(el("text", { x: x(v), y: H - P + 15, "font-size": 10, "text-anchor": "middle",
      fill: "currentColor", "fill-opacity": .5 }, v));
    node.appendChild(el("text", { x: P - 8, y: y(v) + 4, "font-size": 10, "text-anchor": "end",
      fill: "currentColor", "fill-opacity": .5 }, v));
  }
  for (const move of DATA.moves) {
    const up = move.direction === "promoted";
    const dot = el("circle", { cx: x(move.ppg_before), cy: y(move.ppg_after), r: 5,
      fill: up ? "var(--warm)" : "var(--accent)", "fill-opacity": move.complete_after < .95 ? .3 : .7,
      stroke: up ? "var(--warm)" : "var(--accent)" });
    dot.appendChild(el("title", {},
      `${move.name} ${move.from_year}${move.from_division} → ${move.to_year}${move.to_division}` +
      ` (${up ? "昇格" : "降格"}) ${fmt(move.ppg_before)} → ${fmt(move.ppg_after)}` +
      (move.complete_after < .95 ? " ※シーズン途中" : "")));
    node.appendChild(dot);
  }
  node.appendChild(el("text", { x: W / 2, y: H - 6, "font-size": 11, "text-anchor": "middle",
    fill: "currentColor", "fill-opacity": .6 }, "昇降格前シーズンの1試合平均勝点 →"));
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, fill: "currentColor",
    "fill-opacity": .6 }, "縦軸: 昇降格後   橙=昇格 / 青=降格"));
  host.replaceChildren(node);
}

divisionLines(document.getElementById("goals-line"), "goals_per_game", "1試合あたりの得点", 2);
divisionLines(document.getElementById("shots-line"), "shots_per_game", "1試合あたりのシュート数", 1);
divisionLines(document.getElementById("conv-line"), "conversion", "決定率", 3);
moves(document.getElementById("moves"));

let tier = "1部リーグ";
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
    for (const [value, left] of [[season.year, 1], [season.division, 1], [season.played, 0],
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


def build(conn, focus_team_id=None):
    """Render the cross-season page and return the HTML source."""
    seasons = analysis.season_summary(conn)
    if not seasons:
        raise ValueError("no league seasons in this database")
    clubs = [club for club in analysis.club_trajectories(conn) if club["seasons"]]
    # A club whose division stayed the same while the ladder moved under it
    # (the 2025 reorganisation) has not changed division, so it belongs in
    # neither column. See analysis.season_ladder.
    moves = [m for m in analysis.division_moves(conn, clubs) if m["moved"]]
    years = sorted({season["year"] for season in seasons})

    grades = {}
    for division in ("1部リーグ", "2部リーグ", "3部リーグ", "4部リーグ", "チャレンジリーグ"):
        rows = analysis.grade_trend(conn, division=division)
        if rows:
            grades[division] = rows
    grades["all"] = analysis.grade_trend(conn)

    payload = {
        "years": years, "seasons": seasons, "clubs": clubs, "moves": moves, "grades": grades,
    }

    default_club = None
    if focus_team_id:
        default_club = next((c for c in clubs if c["team_id"] == focus_team_id), None)
    default_club = default_club or max(clubs, key=lambda c: len(c["seasons"]))

    options = "".join(
        f'<option value="{_e(club["team_id"])}"'
        f'{" selected" if club is default_club else ""}>'
        f'{_e(club["name"])} ({len(club["seasons"])}季)</option>'
        for club in sorted(clubs, key=lambda c: (c["seasons"][-1]["tier"], c["name"] or ""))
    )
    tier_buttons = "".join(
        f'<button type="button" data-tier="{key}" aria-pressed="false">{label}</button>'
        for key, label in (("1部リーグ", "1部"), ("2部リーグ", "2部"), ("3部リーグ", "3部"),
                           ("4部リーグ", "4部"), ("チャレンジリーグ", "チャレンジ"), ("all", "全部"))
        if key in grades
    )

    season_row_parts = []
    for row in seasons:
        played = "完了" if row["complete"] > 0.95 else "{:.0%}".format(row["complete"])
        shots = "-" if row["shots_per_game"] is None else "{:.1f}".format(row["shots_per_game"])
        conversion = "-" if row["conversion"] is None else "{:.3f}".format(row["conversion"])
        season_row_parts.append(
            "<tr>"
            f'<td class="l">{_e(row["year"])}</td><td class="l">{_e(row["division"])}</td>'
            f'<td>{row["teams"]}</td><td>{row["games"]}</td><td>{played}</td>'
            f'<td>{row["goals_per_game"]:.2f}</td><td>{shots}</td><td>{conversion}</td>'
            f'<td>{row["yellows_per_game"]:.2f}</td><td>{row["reds"]}</td>'
            "</tr>"
        )
    season_rows = "".join(season_row_parts)

    done = [m for m in moves if m["complete_after"] > 0.95]
    promoted = [m for m in done if m["direction"] == "promoted"]
    relegated = [m for m in done if m["direction"] == "relegated"]
    summary = ""
    for label, group in (("昇格した翌シーズン", promoted), ("降格した翌シーズン", relegated)):
        if not group:
            continue
        mean = sum(m["delta"] for m in group) / len(group)
        summary += (
            f'<div class="card"><b>{mean:+.2f}</b><span>{_e(label)}の1試合あたり勝点 '
            f"({len(group)}件)</span></div>"
        )

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>シーズン横断 — togakuren-analytics</title>
<style>{CSS}</style>
</head><body><main>
<h1>シーズン横断分析</h1>
<p class="sub">{_e(years[0])}–{_e(years[-1])} · {len(seasons)}シーズン · {len(clubs)}クラブ ·
生成 {_e(generated)} · togakuren-analytics</p>
<div class="banner">このページは集計値のみで構成されており、選手個人の行を一切含まない。</div>

<h2>シーズン一覧</h2>
<div class="scroll"><table>
<thead><tr><th class="l">年度</th><th class="l">部</th><th>チーム</th><th>試合</th><th>消化</th>
<th>得点/試合</th><th>シュート/試合</th><th>決定率</th><th>警告/試合</th><th>退場</th></tr></thead>
<tbody>{season_rows}</tbody></table></div>
<p class="note">選手単位の記録は2022年から。2021年は結果のみのため、シュート数と決定率は算出していない。</p>

<h2>リーグ水準の推移</h2>
<div class="grid">
  <div id="goals-line"></div>
  <div id="shots-line"></div>
</div>
<div id="conv-line"></div>
<p class="note">薄い点は消化途中のシーズン。</p>

<h2>学年別の出場と得点</h2>
<div class="tabs" id="tiers">{tier_buttons}</div>
<div id="grades"></div>
<p class="note">棒が出場時間の割合（積み上げで100%）、点線が90分あたり得点。
学年構成は毎年入れ替わるため、1シーズンだけの上下は世代差であって傾向ではない。</p>

<h2>クラブの所属部推移</h2>
<p class="sub"><select id="club">{options}</select></p>
<div id="trajectory"></div>
<div class="scroll"><table>
<thead><tr><th class="l">年度</th><th class="l">部</th><th>試合</th><th>勝-分-敗</th>
<th>勝点</th><th>1試合平均</th><th>得点</th><th>得失</th></tr></thead>
<tbody id="club-rows"></tbody></table></div>

<h2>昇降格の影響</h2>
<div class="cards">{summary}</div>
<div id="moves"></div>
<p class="note">対角線より上なら、昇降格後に1試合あたりの勝点が伸びたということ。
薄い点は消化途中のシーズンで、確定値ではない。上の平均は終了済みシーズンのみで計算している。</p>

<footer>
出典: 東京都大学サッカー連盟 公開コンテンツAPI。集計値のみを掲載している。
</footer>
</main>
<script id="payload" type="application/json">{json.dumps(payload, ensure_ascii=False).replace('<', chr(92) + 'u003c')}</script>
<script>{SCRIPT}</script>
</body></html>
"""
