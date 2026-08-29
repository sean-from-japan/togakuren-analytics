"""Interactive single-file dashboard.

A season is too much for one static page: twelve teams, up to twenty-two
matchdays and thirty players each. So the page carries the whole series as JSON
and draws on demand — pick a team with a button, and the squad, the minutes grid
and the club's history across divisions redraw in place.

Still one self-contained file with no external assets, because the interesting
version of it contains names and must never need uploading to render.
"""

import html
import json
from datetime import datetime, timezone

from . import analysis, metrics, privacy

CSS = """
:root { color-scheme: light dark;
  --bg:#fff; --fg:#16191d; --muted:#5c6470; --line:#dfe3e8; --panel:#f7f8fa;
  --accent:#2f6f9f; --warm:#c96a3f; --cool:#4c8b6b; --plum:#8a6bb0; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#14171b; --fg:#e6e9ed; --muted:#9aa3af; --line:#2a2f36; --panel:#1b1f24;
  --accent:#6aa8d8; --warm:#e08a5f; --cool:#6fb391; --plum:#a98cd0; } }
* { box-sizing:border-box; }
body { margin:0; padding:1.75rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:1.55rem; margin:0 0 .2rem; letter-spacing:-.01em; }
h2 { font-size:1.02rem; margin:2.4rem 0 .5rem; padding-bottom:.35rem; border-bottom:1px solid var(--line); }
h3 { font-size:.85rem; margin:1.4rem 0 .4rem; color:var(--muted); font-weight:600;
  text-transform:uppercase; letter-spacing:.05em; }
.sub { color:var(--muted); font-size:.85rem; margin:0 0 1.2rem; }
.note { color:var(--muted); font-size:.8rem; margin:.35rem 0 0; }
.banner { background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--accent);
  padding:.7rem .95rem; border-radius:4px; font-size:.85rem; margin:1rem 0; }
.tabs { display:flex; flex-wrap:wrap; gap:.4rem; margin:.9rem 0 1.2rem; }
.tabs button { font:inherit; font-size:.82rem; padding:.35rem .75rem; cursor:pointer;
  border:1px solid var(--line); background:var(--panel); color:var(--fg); border-radius:999px; }
.tabs button:hover { border-color:var(--accent); }
.tabs button[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; }
.scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table { border-collapse:collapse; width:100%; font-size:.83rem; }
th,td { padding:.35rem .55rem; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }
th:first-child,td:first-child,th.l,td.l { text-align:left; }
th { color:var(--muted); font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.04em; }
tbody tr:hover { background:var(--panel); }
svg { display:block; max-width:100%; height:auto; }
#bubbles svg, #curve svg, #opponents svg, #grades svg,
#goals-line svg, #shots-line svg, #conv-line svg, #trajectory svg, #moves svg
  { width:100%; max-width:640px; }
#radar-big svg { width:100%; max-width:320px; }
.grid { display:grid; gap:1.4rem; grid-template-columns:repeat(auto-fit,minmax(290px,1fr)); }
.cards { display:grid; gap:.7rem; grid-template-columns:repeat(auto-fit,minmax(118px,1fr)); margin:.8rem 0; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:6px; padding:.6rem .7rem; }
.card b { display:block; font-size:1.28rem; font-weight:650; letter-spacing:-.02em; }
.card span { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.05em; }
.radars { display:grid; gap:.5rem; grid-template-columns:repeat(auto-fit,minmax(148px,1fr)); }
.radars figure { margin:0; text-align:center; }
.radars figcaption { font-size:.73rem; color:var(--muted); margin-top:-.3rem; }
.radars figure.on { outline:2px solid var(--accent); outline-offset:3px; border-radius:6px; }
.heat td { padding:0; border:none; }
.heat .cell { width:19px; height:17px; border-radius:2px; }
.heat th { font-size:.68rem; padding:.2rem .25rem; }
.heat td.l { padding:.1rem .5rem .1rem 0; font-size:.78rem; max-width:190px;
  overflow:hidden; text-overflow:ellipsis; }
.legend { display:flex; gap:.5rem; align-items:center; font-size:.75rem; color:var(--muted); margin-top:.5rem; }
.legend i { width:15px; height:11px; border-radius:2px; display:inline-block; }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line);
  color:var(--muted); font-size:.79rem; }
"""

SCRIPT = r"""
const DATA = JSON.parse(document.getElementById("payload").textContent);
const NS = "http://www.w3.org/2000/svg";
const AXES = DATA.axes;
const fmt = (v, d = 1) => (v == null ? "-" : Number(v).toFixed(d));

function el(name, attrs, text) {
  const node = document.createElementNS(NS, name);
  for (const key in attrs) node.setAttribute(key, attrs[key]);
  if (text != null) node.textContent = text;
  return node;
}
function svg(width, height, label) {
  const node = el("svg", { viewBox: `0 0 ${width} ${height}`, role: "img" });
  if (label) node.appendChild(el("title", {}, label));
  return node;
}

/* Rank on x, shot volume on y, goals as area. Three axes at once, so a side
   that shoots a lot without scoring separates from one that does not shoot. */
function bubbles(host, teams, selected) {
  const W = 620, H = 330, L = 72, R = 18, T = 26, B = 42;
  const node = svg(W, H, "順位とシュート量");
  const maxRank = teams.length;
  const maxY = Math.max(...teams.map(t => t.shots_per_game)) * 1.12 || 1;
  const maxGoals = Math.max(...teams.map(t => t.goals_for)) || 1;
  const x = r => L + (W - L - R) * (r - 1) / Math.max(1, maxRank - 1);
  const y = v => T + (H - T - B) * (1 - v / maxY);

  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, fill: "currentColor",
    "fill-opacity": .6 }, "シュート/試合"));
  const ticks = [];
  for (let i = 0; i <= 4; i++) {
    const value = maxY * i / 4;
    node.appendChild(el("line", { x1: L, x2: W - R, y1: y(value), y2: y(value),
      stroke: "currentColor", "stroke-opacity": .12 }));
    ticks.push([value, y(value)]);
  }
  for (const team of teams) {
    const radius = 5 + 20 * Math.sqrt(team.goals_for / maxGoals);
    const on = team.team_pk === selected;
    const circle = el("circle", { cx: x(team.rank), cy: y(team.shots_per_game), r: radius,
      fill: on ? "var(--warm)" : "var(--accent)", "fill-opacity": on ? .55 : .3,
      stroke: on ? "var(--warm)" : "var(--accent)", "stroke-width": on ? 2 : 1, cursor: "pointer" });
    circle.appendChild(el("title", {}, `${team.team} — ${team.rank}位 / シュート${fmt(team.shots_per_game)}本per試合 / ${team.goals_for}得点`));
    circle.addEventListener("click", () => select(team.team_pk));
    node.appendChild(circle);
    node.appendChild(el("text", { x: x(team.rank), y: y(team.shots_per_game) + 3.5,
      "font-size": 9.5, "text-anchor": "middle", fill: "currentColor", "fill-opacity": .8 }, team.rank));
  }
  /* Drawn last so a bubble sitting on the axis cannot hide its own scale. */
  for (const [value, ty] of ticks) {
    node.appendChild(el("text", { x: L - 7, y: ty + 4, "font-size": 10,
      "text-anchor": "end", fill: "currentColor", "fill-opacity": .55 }, fmt(value)));
  }
  node.appendChild(el("text", { x: (L + W - R) / 2, y: H - 8, "font-size": 11,
    "text-anchor": "middle", fill: "currentColor", "fill-opacity": .6 }, "順位 →"));
  node.appendChild(el("text", { x: W - R, y: H - 8, "font-size": 10, "text-anchor": "end",
    fill: "currentColor", "fill-opacity": .5 }, "円の面積 = 総得点"));
  host.replaceChildren(node);
}

function radar(team, size, selected) {
  const c = size / 2, radius = size * 0.34;
  const node = svg(size, size, `${team.team} の個性`);
  const points = AXES.map((axis, i) => {
    const angle = -Math.PI / 2 + i * 2 * Math.PI / AXES.length;
    const value = team.axes[axis.key] / 100;
    return [c + radius * value * Math.cos(angle), c + radius * value * Math.sin(angle),
            c + radius * Math.cos(angle), c + radius * Math.sin(angle), axis];
  });
  for (const ring of [.34, .67, 1]) {
    node.appendChild(el("polygon", {
      points: AXES.map((_, i) => {
        const angle = -Math.PI / 2 + i * 2 * Math.PI / AXES.length;
        return `${c + radius * ring * Math.cos(angle)},${c + radius * ring * Math.sin(angle)}`;
      }).join(" "),
      fill: "none", stroke: "currentColor", "stroke-opacity": .13 }));
  }
  for (const p of points) {
    node.appendChild(el("line", { x1: c, y1: c, x2: p[2], y2: p[3],
      stroke: "currentColor", "stroke-opacity": .1 }));
  }
  const on = team.team_pk === selected;
  node.appendChild(el("polygon", { points: points.map(p => `${p[0]},${p[1]}`).join(" "),
    fill: on ? "var(--warm)" : "var(--accent)", "fill-opacity": .28,
    stroke: on ? "var(--warm)" : "var(--accent)", "stroke-width": 1.6 }));
  if (size > 200) {
    points.forEach((p, i) => {
      const angle = -Math.PI / 2 + i * 2 * Math.PI / AXES.length;
      node.appendChild(el("text", {
        x: c + (radius + 16) * Math.cos(angle), y: c + (radius + 16) * Math.sin(angle) + 4,
        "font-size": 10.5, "text-anchor": "middle", fill: "currentColor", "fill-opacity": .7,
      }, `${AXES[i].label} ${Math.round(team.axes[AXES[i].key])}`));
    });
  }
  return node;
}

function radarGrid(host, teams, selected) {
  host.replaceChildren();
  for (const team of teams) {
    const figure = document.createElement("figure");
    if (team.team_pk === selected) figure.className = "on";
    figure.appendChild(radar(team, 150, selected));
    const caption = document.createElement("figcaption");
    caption.textContent = `${team.rank}. ${team.team}`;
    figure.appendChild(caption);
    figure.style.cursor = "pointer";
    figure.addEventListener("click", () => select(team.team_pk));
    host.appendChild(figure);
  }
}

function curve(host, selected) {
  const W = 620, H = 300, L = 34, R = 96, T = 20, B = 32;
  const node = svg(W, H, "節ごとの勝点の積み上がり");
  const maxSection = Math.max(...DATA.curve.flatMap(t => t.points.map(p => p[0])));
  const maxPoints = Math.max(...DATA.curve.flatMap(t => t.points.map(p => p[1]))) || 1;
  const x = s => L + (W - L - R) * (s - 1) / Math.max(1, maxSection - 1);
  const y = p => T + (H - T - B) * (1 - p / maxPoints);

  node.appendChild(el("line", { x1: L, x2: W - R, y1: y(0), y2: y(0),
    stroke: "currentColor", "stroke-opacity": .2 }));
  const ends = [];
  for (const team of DATA.curve) {
    const on = team.team_pk === selected;
    node.appendChild(el("polyline", {
      points: team.points.map(p => `${x(p[0])},${y(p[1])}`).join(" "),
      fill: "none", stroke: on ? "var(--warm)" : "currentColor",
      "stroke-opacity": on ? 1 : .22, "stroke-width": on ? 2.4 : 1.2 }));
    const last = team.points[team.points.length - 1];
    ends.push({ team, on, x: x(last[0]), y: y(last[1]) });
  }
  /* Teams that finish level land on the same pixel; push the labels apart so
     every one stays readable. */
  ends.sort((a, b) => a.y - b.y);
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].y - ends[i - 1].y < 11) ends[i].y = ends[i - 1].y + 11;
  }
  for (const end of ends) {
    node.appendChild(el("text", { x: end.x + 5, y: end.y + 3.5, "font-size": 9.5,
      fill: "currentColor", "fill-opacity": end.on ? .95 : .4 }, end.team.team.slice(0, 8)));
  }
  node.appendChild(el("text", { x: (L + W - R) / 2, y: H - 6, "font-size": 11,
    "text-anchor": "middle", fill: "currentColor", "fill-opacity": .6 }, "節 →"));
  host.replaceChildren(node);
}

function stacked(host, rows, selected) {
  const rowH = 21, L = 118, W = 560, T = 8;
  const node = svg(W, T + rows.length * rowH + 6, "上位陣・下位陣から奪った得点");
  const peak = Math.max(...rows.map(r => r.vs_top + r.vs_bottom)) || 1;
  const span = W - L - 96;
  rows.forEach((row, i) => {
    const y = T + i * rowH;
    const on = row.team_pk === selected;
    node.appendChild(el("text", { x: L - 6, y: y + 12, "font-size": 10.5, "text-anchor": "end",
      fill: "currentColor", "fill-opacity": on ? 1 : .7 }, row.team.slice(0, 9)));
    const topW = span * row.vs_top / peak, bottomW = span * row.vs_bottom / peak;
    node.appendChild(el("rect", { x: L, y: y + 3, width: Math.max(topW, .5), height: 13, rx: 2,
      fill: "var(--accent)", "fill-opacity": on ? .95 : .65 }));
    node.appendChild(el("rect", { x: L + topW, y: y + 3, width: Math.max(bottomW, .5), height: 13, rx: 2,
      fill: "var(--warm)", "fill-opacity": on ? .95 : .55 }));
    node.appendChild(el("text", { x: L + topW + bottomW + 6, y: y + 13, "font-size": 10,
      fill: "currentColor", "fill-opacity": .6 },
      `${row.vs_top}+${row.vs_bottom}  ${Math.round(row.bottom_share * 100)}% 下位`));
  });
  host.replaceChildren(node);
}

function heat(host, team) {
  const matrix = DATA.matrix[team.team_pk];
  if (!matrix || !matrix.players.length) { host.replaceChildren(); return; }
  const table = document.createElement("table");
  table.className = "heat";
  const head = table.createTHead().insertRow();
  head.appendChild(document.createElement("th")).className = "l";
  for (const section of matrix.sections) {
    const cell = document.createElement("th");
    cell.textContent = section;
    head.appendChild(cell);
  }
  const total = document.createElement("th");
  total.textContent = "計";
  head.appendChild(total);

  const body = table.createTBody();
  for (const player of matrix.players) {
    const row = body.insertRow();
    const name = row.insertCell();
    name.className = "l";
    name.textContent = `${player.label}${player.grade ? " " + player.grade + "年" : ""}${player.position ? " " + player.position : ""}`;
    for (const section of matrix.sections) {
      const minutes = player.minutes[section] || 0;
      const cell = row.insertCell();
      const box = document.createElement("div");
      box.className = "cell";
      box.style.background = minutes
        ? `color-mix(in srgb, var(--accent) ${18 + 72 * minutes / 90}%, transparent)`
        : "var(--panel)";
      box.title = `第${section}節 ${minutes}分`;
      cell.appendChild(box);
    }
    const sum = row.insertCell();
    sum.textContent = player.total;
    sum.style.fontSize = ".76rem";
  }
  host.replaceChildren(table);
}

function grades(host, team) {
  const W = 380, H = 128, L = 30, T = 24, B = 26;
  const node = svg(W, H, "学年別の出場時間と得点");
  const entries = ["1", "2", "3", "4"].map(g => [g, team.grades[g] || { minutes: 0, goals: 0, players: 0 }]);
  const peak = Math.max(...entries.map(e => e[1].minutes)) || 1;
  const slot = (W - L - 12) / entries.length;
  const plot = H - T - B;
  entries.forEach(([grade, value], i) => {
    const barH = plot * value.minutes / peak;
    const x = L + i * slot;
    node.appendChild(el("rect", { x: x + slot * .18, y: T + plot - barH, width: slot * .64,
      height: Math.max(barH, 1), rx: 2, fill: "var(--plum)", "fill-opacity": .75 }));
    node.appendChild(el("text", { x: x + slot / 2, y: T + plot - barH - 4, "font-size": 9.5,
      "text-anchor": "middle", fill: "currentColor", "fill-opacity": .65 },
      `${value.minutes}分 / ${value.goals}G`));
    node.appendChild(el("text", { x: x + slot / 2, y: T + plot + 14, "font-size": 10.5,
      "text-anchor": "middle", fill: "currentColor", "fill-opacity": .6 },
      `${grade}年 (${value.players})`));
  });
  node.appendChild(el("text", { x: 0, y: 12, "font-size": 11, "font-weight": 600,
    fill: "currentColor" }, "学年別の出場時間"));
  host.replaceChildren(node);
}

function table(host, headers, rows, leftColumns = 1) {
  const node = document.createElement("table");
  const head = node.createTHead().insertRow();
  headers.forEach((label, i) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    if (i < leftColumns) cell.className = "l";
    head.appendChild(cell);
  });
  const body = node.createTBody();
  for (const row of rows) {
    const line = body.insertRow();
    row.forEach((value, i) => {
      const cell = line.insertCell();
      cell.textContent = value == null ? "-" : value;
      if (i < leftColumns) cell.className = "l";
    });
  }
  const wrap = document.createElement("div");
  wrap.className = "scroll";
  wrap.appendChild(node);
  host.replaceChildren(wrap);
}

function cards(host, items) {
  host.replaceChildren();
  for (const [label, value] of items) {
    const card = document.createElement("div");
    card.className = "card";
    const strong = document.createElement("b");
    strong.textContent = value;
    const span = document.createElement("span");
    span.textContent = label;
    card.append(strong, span);
    host.appendChild(card);
  }
}

let current = DATA.teams[0].team_pk;

function select(teamPk) {
  current = teamPk;
  const team = DATA.teams.find(t => t.team_pk === teamPk);
  for (const button of document.querySelectorAll(".tabs button")) {
    button.setAttribute("aria-pressed", String(button.dataset.team === teamPk));
  }
  document.getElementById("team-name").textContent = `${team.rank}. ${team.team}`;

  bubbles(document.getElementById("bubbles"), DATA.teams, teamPk);
  radarGrid(document.getElementById("radars"), DATA.teams, teamPk);
  curve(document.getElementById("curve"), teamPk);
  stacked(document.getElementById("opponents"), DATA.opponents, teamPk);

  document.getElementById("radar-big").replaceChildren(radar(team, 300, teamPk));
  cards(document.getElementById("team-cards"), [
    ["勝点", team.points], ["得点", team.goals_for], ["失点", team.goals_against],
    ["シュート/試合", fmt(team.shots_per_game)], ["決定率", fmt(team.conversion, 3)],
    ["起用人数", team.players_used], ["主力11人の出場時間比率", Math.round(team.core_share * 100) + "%"],
    ["平均学年", fmt(team.mean_grade, 2)],
  ]);
  grades(document.getElementById("grades"), team);
  heat(document.getElementById("heat"), team);

  table(document.getElementById("history"),
    ["年度", "ディビジョン", "試合", "勝-分-敗", "勝点", "1試合平均"],
    (DATA.history[team.team_id] || []).map(h =>
      [h.year, h.division, h.played, `${h.win}-${h.draw}-${h.lose}`, h.points, fmt(h.points_per_game, 2)]),
    2);

  const squad = DATA.squads[teamPk] || [];
  table(document.getElementById("squad"),
    ["選手", "学年", "Pos", "出場", "先発", "分", "S", "G", "S/90", "決定率"],
    squad.map(p => [p.label, p.grade ? p.grade + "年" : "-", p.position || "-",
      p.apps, p.starts, p.minutes, p.shots, p.goals, fmt(p.shots_per_90, 2), fmt(p.conversion, 3)]), 3);
}

for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => select(button.dataset.team));
}
select(current);
"""


def _e(value):
    return html.escape("" if value is None else str(value))


def build(conn, series_id, mode="full", salt=None, min_minutes=0):
    """Render the dashboard for one series and return the HTML source."""
    series = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    if series is None:
        raise ValueError(f"series {series_id!r} is not in this database")

    profile = analysis.team_profile(conn, series_id)
    if not profile:
        raise ValueError(f"series {series_id!r} has no completed fixtures")
    prints = {row["team_pk"]: row["axes"] for row in analysis.fingerprints(conn, series_id, profile)}
    names = dict(conn.execute("SELECT player_id, name FROM players"))
    per_player = metrics.player_season(conn, series_id, min_minutes=min_minutes, order_by="minutes")
    grades = {
        row[0]: row[1]
        for row in conn.execute(
            "SELECT player_id, grade FROM squad_members WHERE series_id = ?", (series_id,)
        )
    }

    show_players = mode != "aggregate"

    def label(player_id):
        return privacy.label(player_id, names.get(player_id), mode, salt)

    teams = []
    for row in profile:
        teams.append(
            {
                "team_pk": row["team_pk"], "team_id": row["team_id"], "team": row["team"],
                "rank": row["rank"], "points": row["points"], "played": row["played"],
                "goals_for": row["goals_for"], "goals_against": row["goals_against"],
                "shots": row["shots"], "shots_per_game": round(row["shots_per_game"], 2),
                "conversion": round(row["conversion"], 4),
                "conceded_per_game": round(row["conceded_per_game"], 2),
                "players_used": row["players_used"], "regulars": row["regulars"],
                "core_share": round(row["core_share"], 4),
                "youth_share": round(row["youth_share"], 4),
                "mean_grade": round(row["mean_grade"], 3),
                "second_half_share": round(row["second_half_share"], 4),
                "grades": row["grades"],
                "axes": prints.get(row["team_pk"], {}),
            }
        )

    matrix, squads = {}, {}
    if show_players:
        for row in profile:
            grid = analysis.minutes_matrix(conn, series_id, row["team_pk"])
            matrix[row["team_pk"]] = {
                "sections": grid["sections"],
                "players": [
                    {
                        "label": label(player["player_id"]), "grade": player["grade"],
                        "position": player["position"], "total": player["total"],
                        "starts": player["starts"],
                        "minutes": {str(k): v for k, v in player["minutes"].items()},
                    }
                    for player in grid["players"]
                ],
            }
        by_team = {row["team"]: row["team_pk"] for row in profile}
        for player in per_player:
            team_pk = by_team.get(player["team"])
            if not team_pk:
                continue
            squads.setdefault(team_pk, []).append(
                {
                    "label": label(player["player_id"]),
                    "grade": grades.get(player["player_id"]),
                    "position": player["position"], "apps": player["apps"],
                    "starts": player["starts"], "minutes": player["minutes"],
                    "shots": player["shots"], "goals": player["goals"],
                    "shots_per_90": player["shots_per_90"], "conversion": player["conversion"],
                }
            )

    history = {}
    for row in profile:
        if row["team_id"]:
            history[row["team_id"]] = analysis.team_history(conn, row["team_id"])

    payload = {
        # The page is Japanese, so the radar reads in Japanese too.
        "axes": [
            {"key": key, "label": analysis.FINGERPRINT_AXES_JA[key][0],
             "hint": analysis.FINGERPRINT_AXES_JA[key][1]}
            for key, _, _ in analysis.FINGERPRINT_AXES
        ],
        "teams": teams,
        "curve": analysis.points_curve(conn, series_id),
        "opponents": analysis.goals_by_opponent(conn, series_id, profile),
        "matrix": matrix,
        "squads": squads,
        "history": history,
    }

    banner = ""
    if mode == "aggregate":
        banner = (
            '<div class="banner"><strong>Aggregate mode.</strong> Squad and minutes views are '
            "omitted; what remains describes groups, not individuals.</div>"
        )
    elif mode != "full":
        anonymity = privacy.k_anonymity(
            [{"team": p["team"], "position": p["position"]} for p in per_player],
            ["team", "position"],
        )
        banner = (
            f'<div class="banner"><strong>Privacy mode: {_e(mode)}.</strong> Names are replaced, '
            f"but {anonymity['unique']} of {anonymity['total']} rows are still unique on team and "
            "position alone. Pseudonymised, not anonymous.</div>"
        )

    buttons = "".join(
        f'<button type="button" data-team="{_e(row["team_pk"])}" aria-pressed="false">'
        f'{row["rank"]}. {_e(row["team"])}</button>'
        for row in profile
    )
    axis_list = "".join(
        f"<li><b>{_e(analysis.FINGERPRINT_AXES_JA[key][0])}</b> — "
        f"{_e(analysis.FINGERPRINT_AXES_JA[key][1])}</li>"
        for key, _, _ in analysis.FINGERPRINT_AXES
    )
    player_sections = (
        """
<h3>出場時間マトリクス（節 × 選手）</h3>
<div class="scroll" id="heat"></div>
<div class="legend"><span>出場時間</span><i style="background:var(--panel)"></i>0分
  <i style="background:color-mix(in srgb, var(--accent) 54%, transparent)"></i>45分
  <i style="background:color-mix(in srgb, var(--accent) 90%, transparent)"></i>90分</div>
<p class="note">上ほど出場時間が長い選手。固定メンバーのチームは縦に濃く揃い、ターンオーバーの多いチームはまだらになる。</p>

<h3>選手一覧</h3>
<div id="squad"></div>
"""
        if show_players
        else ""
    )

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(series['short_name'] or series['name'])} {_e(series['year'])} — dashboard</title>
<style>{CSS}</style>
</head><body><main>
<h1>{_e(series['name'])}</h1>
<p class="sub">{_e(series['year'])} · {len(profile)}チーム · 生成 {_e(generated)} · togakuren-analytics</p>
{banner}

<div class="tabs">{buttons}</div>

<h2>リーグ全体</h2>
<h3>順位 × シュート数 × 得点</h3>
<div id="bubbles"></div>
<p class="note">横軸が最終順位、縦軸が1試合あたりシュート数、円の面積が総得点。
順位の割にシュートが多いチームと、少ない本数で決めているチームが同じ図の中で分かれる。</p>

<div class="grid">
  <div><h3>勝点の積み上がり</h3><div id="curve"></div></div>
  <div><h3>得点した相手（上位/下位）</h3><div id="opponents"></div>
  <p class="note">青が上位陣から、橙が下位陣から奪った得点。</p></div>
</div>

<h3>チームの個性（6指標）</h3>
<div class="radars" id="radars"></div>
<p class="note">各指標はこのリーグ内での相対値（0〜100）。クリックでそのチームに切り替わる。</p>
<ul class="note">{axis_list}</ul>

<h2 id="team-name"></h2>
<div class="grid">
  <div id="radar-big"></div>
  <div><div class="cards" id="team-cards"></div><div id="grades"></div></div>
</div>

<h3>過去シーズン（部をまたいで追跡）</h3>
<div id="history"></div>
{player_sections}

<footer>
出典: 東京都大学サッカー連盟 公開コンテンツAPI。ローカル生成のファイルであり、
連盟サイトが公開している以上の情報は含まない。
</footer>
</main>
<script id="payload" type="application/json">{json.dumps(payload, ensure_ascii=False).replace('<', chr(92) + 'u003c')}</script>
<script>{SCRIPT}</script>
</body></html>
"""
