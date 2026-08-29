"""Self-contained HTML report with inline SVG charts.

No plotting library and no network assets: the output is one file that opens
anywhere, which matters because the interesting version of this report contains
personal data and should never be uploaded to render.
"""

import html
from datetime import datetime, timezone

from . import metrics, privacy

PALETTE = ["#2f6f9f", "#c96a3f", "#4c8b6b", "#8a6bb0", "#b0873f", "#7a7f88"]

CSS = """
:root { color-scheme: light dark;
  --bg:#ffffff; --fg:#16191d; --muted:#5c6470; --line:#dfe3e8; --panel:#f7f8fa; --accent:#2f6f9f; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#14171b; --fg:#e6e9ed; --muted:#9aa3af; --line:#2a2f36; --panel:#1b1f24; --accent:#6aa8d8; } }
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
  font:15px/1.6 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif; }
main { max-width:960px; margin:0 auto; }
h1 { font-size:1.6rem; margin:0 0 .25rem; letter-spacing:-.01em; }
h2 { font-size:1.05rem; margin:2.5rem 0 .5rem; padding-bottom:.4rem; border-bottom:1px solid var(--line); }
.sub { color:var(--muted); font-size:.86rem; margin:0 0 1.5rem; }
.note { color:var(--muted); font-size:.82rem; margin:.4rem 0 0; }
.banner { background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--accent);
  padding:.75rem 1rem; border-radius:4px; font-size:.86rem; margin:1rem 0; }
.scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table { border-collapse:collapse; width:100%; font-size:.85rem; min-width:600px; }
th,td { padding:.4rem .6rem; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) { text-align:left; }
th { color:var(--muted); font-weight:600; font-size:.78rem; text-transform:uppercase; letter-spacing:.04em; }
tbody tr:hover { background:var(--panel); }
svg { display:block; max-width:100%; height:auto; }
.grid { display:grid; gap:1.5rem; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); }
footer { margin-top:3rem; padding-top:1rem; border-top:1px solid var(--line); color:var(--muted); font-size:.8rem; }
"""


def _e(value):
    return html.escape("" if value is None else str(value))


def _shorten(text, limit=9):
    text = "" if text is None else str(text)
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _bar_chart(rows, value_key, label_key, title, width=460, colour=PALETTE[0], fmt="{:.1f}"):
    """Horizontal bars. ``rows`` is a list of dicts, already ordered."""
    if not rows:
        return ""
    row_h, pad_left, pad_right, top = 22, 112, 52, 26
    height = top + len(rows) * row_h + 8
    peak = max((row.get(value_key) or 0) for row in rows) or 1
    span = width - pad_left - pad_right

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{_e(title)}">',
        f'<text x="0" y="14" font-size="12" font-weight="600" fill="currentColor">{_e(title)}</text>',
    ]
    for index, row in enumerate(rows):
        value = row.get(value_key) or 0
        y = top + index * row_h
        bar = max(1, span * value / peak)
        parts.append(
            f'<text x="{pad_left - 6}" y="{y + 12}" font-size="11" text-anchor="end" '
            f'fill="currentColor" opacity=".75">{_e(_shorten(row.get(label_key)))}'
            f'<title>{_e(row.get(label_key))}</title></text>'
        )
        parts.append(
            f'<rect x="{pad_left}" y="{y + 3}" width="{bar:.1f}" height="13" rx="2" fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{pad_left + bar + 5:.1f}" y="{y + 13}" font-size="10.5" '
            f'fill="currentColor" opacity=".6">{_e(fmt.format(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _column_chart(pairs, title, width=460, height=200, colour=PALETTE[1]):
    """Vertical columns from ``(label, value)`` pairs."""
    if not pairs:
        return ""
    pad_left, pad_bottom, top = 34, 26, 26
    peak = max(value for _, value in pairs) or 1
    span = width - pad_left - 10
    slot = span / len(pairs)
    plot = height - top - pad_bottom

    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{_e(title)}">',
        f'<text x="0" y="14" font-size="12" font-weight="600" fill="currentColor">{_e(title)}</text>',
        f'<line x1="{pad_left}" y1="{top + plot}" x2="{width - 6}" y2="{top + plot}" '
        f'stroke="currentColor" opacity=".2"/>',
    ]
    for index, (name, value) in enumerate(pairs):
        bar = plot * value / peak
        x = pad_left + index * slot
        parts.append(
            f'<rect x="{x + slot * .15:.1f}" y="{top + plot - bar:.1f}" '
            f'width="{slot * .7:.1f}" height="{bar:.1f}" rx="2" fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{x + slot / 2:.1f}" y="{top + plot - bar - 4:.1f}" font-size="10" '
            f'text-anchor="middle" fill="currentColor" opacity=".6">{value}</text>'
        )
        parts.append(
            f'<text x="{x + slot / 2:.1f}" y="{top + plot + 15:.1f}" font-size="10" '
            f'text-anchor="middle" fill="currentColor" opacity=".55">{_e(name)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def _table(headers, rows):
    head = "".join(f"<th>{_e(header)}</th>" for header in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(cell)}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def build(conn, series_id, mode="full", salt=None, min_minutes=270, top=20):
    """Render the report for one series and return the HTML source."""
    series = conn.execute("SELECT * FROM series WHERE id = ?", (series_id,)).fetchone()
    if series is None:
        raise ValueError(f"series {series_id!r} is not in this database")

    teams = metrics.team_season(conn, series_id)
    players = metrics.player_season(conn, series_id, min_minutes=min_minutes)
    halves = metrics.shot_periods(conn, series_id)
    timeline = metrics.goal_minutes(conn, series_id)
    subs = metrics.substitution_profile(conn, series_id)

    names = dict(conn.execute("SELECT player_id, name FROM players"))
    banner = ""
    if mode == "aggregate":
        banner = (
            '<div class="banner"><strong>集計モード。</strong> 選手単位の行は出力していない。'
            "残っているのは集団についての統計情報であり、個人情報保護法の適用範囲外にあたる。</div>"
        )
        player_section = ""
    else:
        anonymity = privacy.k_anonymity(players, ["team", "position"])
        if mode != "full":
            banner = (
                f'<div class="banner"><strong>プライバシーモード: {_e(mode)}。</strong> '
                f"名前は置き換えてあるが、{anonymity['total']}行のうち{anonymity['unique']}行は"
                "チームとポジションだけで一意のままであり、どちらも連盟が公開している。"
                "匿名ではなく仮名化として扱うこと。</div>"
            )
        rows = []
        for player in players[:top]:
            rows.append(
                [
                    privacy.label(player["player_id"], names.get(player["player_id"]), mode, salt),
                    player["team"],
                    f"{player['grade']}年" if player["grade"] else "-",
                    player["position"],
                    player["apps"],
                    player["starts"],
                    player["minutes"],
                    player["shots"],
                    player["goals"],
                    f"{player['shots_per_90']:.2f}",
                    f"{player['conversion']:.3f}",
                ]
            )
        player_section = (
            f"<h2>90分あたりのシュート数 &mdash; 上位{min(top, len(players))}人</h2>"
            f'<p class="sub">出場時間{min_minutes}分以上。出場時間は先発11人・時刻つきの交代・退場から'
            "復元した値で、連盟はいずれも直接記録していない。</p>"
            + _table(
                ["選手", "チーム", "学年", "ポジション", "出場", "先発", "出場時間", "シュート", "得点", "90分あたり", "決定率"],
                rows,
            )
        )

    by_volume = sorted(teams, key=lambda team: team["shots_per_game"], reverse=True)
    by_conversion = sorted(teams, key=lambda team: team["conversion"], reverse=True)

    table_rows = [
        [
            team["team"], team["played"], team["points"],
            f"{team['win']}-{team['draw']}-{team['lose']}",
            team["goals_for"], team["goal_difference"], team["shots"],
            f"{team['shots_per_game']:.1f}", f"{team['conversion']:.3f}",
        ]
        for team in teams
    ]

    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    half_pairs = [("前半", halves[0]), ("後半", halves[1])]
    if halves[2] or halves[3]:
        half_pairs += [("延長前半", halves[2]), ("延長後半", halves[3])]

    return f"""<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(series['short_name'] or series['name'])} {_e(series['year'])} &mdash; togakuren-analytics</title>
<style>{CSS}</style>
</head><body><main>
<h1>{_e(series['name'])}</h1>
<p class="sub">{_e(series['year'])} &middot; 生成 {_e(generated)} &middot; togakuren-analytics</p>
{banner}

<h2>順位表とシュート</h2>
{_table(["チーム", "試合", "勝点", "勝-分-敗", "得点", "得失点", "シュート", "1試合平均", "決定率"], table_rows)}
<p class="note">決定率は得点をシュート数で割った値。順位表と得点ランキングは連盟が公開しているが、
シュート関連の列はここで算出したもの。</p>

<div class="grid">
  <div>{_bar_chart(by_volume, 'shots_per_game', 'team', '1試合あたりのシュート数', colour=PALETTE[0])}</div>
  <div>{_bar_chart(by_conversion, 'conversion', 'team', '決定率', colour=PALETTE[2], fmt='{:.3f}')}</div>
</div>

<h2>時間帯</h2>
<div class="grid">
  <div>{_column_chart(timeline, '15分ごとの得点', colour=PALETTE[1])}
    <p class="note">最後の区分にはアディショナルタイムが含まれる。</p></div>
  <div>{_column_chart(half_pairs, '時間帯別のシュート', colour=PALETTE[3])}</div>
</div>

{player_section}

<h2>交代のタイミング</h2>
{_table(["チーム", "交代", "平均時刻", "起用人数"],
        [[row["team"], row["subs"], row["mean_minute"], row["players_used"]] for row in subs])}

<footer>
出典: 東京都大学サッカー連盟 公開コンテンツAPI。
このレポートはローカルで生成されたもので、同サイトが公開している以上の情報は含まない。
</footer>
</main></body></html>
"""
