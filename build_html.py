import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PARTY_COLOURS = {
    "National": "#1f5fbf",
    "Labour": "#d82c20",
    "Green": "#2e9e44",
    "ACT": "#e0a500",
    "Te Pāti Māori": "#a8323e",
    "NZ First": "#3a3a3a",
    "TOP": "#0aa5a8",
}

ORDER = ["National", "Labour", "Green", "ACT", "Te Pāti Māori", "NZ First"]

CHEVRON = ('<svg class="chev" viewBox="0 0 16 16" aria-hidden="true">'
           '<path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" '
           'stroke-linecap="round" stroke-linejoin="round"/></svg>')

ARROW = ('<svg class="arrow" viewBox="0 0 16 16" aria-hidden="true">'
         '<path d="M2.5 8h10M9 4.5 12.5 8 9 11.5" fill="none" stroke="currentColor" stroke-width="1.6" '
         'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def esc(value):
    return html.escape(str(value))


def colour(party):
    return PARTY_COLOURS.get(party, "#8a8f98")


SHORT_PARTY = {
    "Aotearoa Legalise Cannabis Party": "Legalise Cannabis",
    "NZ Outdoors & Freedom Party": "Outdoors & Freedom",
    "Animal Justice Party Aotearoa New Zealand": "Animal Justice",
    "New Zealand Loyal": "NZ Loyal",
    "Women’s Rights Party": "Women's Rights",
    "Women's Rights Party": "Women's Rights",
}


def short_party(party):
    party = SHORT_PARTY.get(party, party)
    return re.sub(r"\s*\(.*?\)\s*$", "", party)


def chip(party):
    return f'<span class="chip" style="--c:{colour(party)}">{esc(short_party(party))}</span>'


def candidate_cell(name, party):
    return (f'<span class="cand"><span class="dot" style="--c:{colour(party)}"></span>'
            f'<span><span class="cn">{esc(name)}</span><small>{esc(short_party(party))}</small></span></span>')


def n(value):
    return f"{value:,}"


def totals(electorates, pick):
    counts = {}
    for e in electorates:
        party = pick(e)["party"]
        counts[party] = counts.get(party, 0) + 1
    return counts


def seat_bar(counts, total):
    parties = [p for p in ORDER if p in counts] + sorted(p for p in counts if p not in ORDER)
    segments = "".join(
        f'<span class="seg" style="--c:{colour(p)};flex:{counts[p]}" title="{esc(p)}: {counts[p]}"></span>'
        for p in parties)
    legend = "".join(f'<li>{chip(p)}<b>{counts[p]}</b></li>' for p in parties)
    return f'<div class="bar" role="img" aria-label="seat split">{segments}</div><ul class="legend">{legend}</ul>'


def rounds_table(electorate, outcome):
    names = [c["name"] for c in electorate["candidates"]]
    party_of = {c["name"]: c["party"] for c in electorate["candidates"]}
    rounds = outcome["rounds"]
    head = "".join(f"<th>{'Final' if i == len(rounds) - 1 else f'R{i + 1}'}</th>" for i in range(len(rounds)))
    rows = []
    for name in names:
        cells = []
        for r in rounds:
            value = r["tallies"].get(name)
            cells.append(f"<td>{n(value)}</td>" if value is not None else '<td class="out">out</td>')
        winner = ' class="won"' if name == outcome["winner"]["name"] else ""
        rows.append(f'<tr{winner}><th scope="row">{candidate_cell(name, party_of[name])}</th>{"".join(cells)}</tr>')
    exhausted = "".join(f"<td>{n(r['exhausted'])}</td>" for r in rounds)
    rows.append(f'<tr class="ex"><th scope="row">Exhausted</th>{exhausted}</tr>')
    return (f'<div class="scroll"><table class="rounds"><thead><tr><th>Candidate</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def flip_card(e, key="brief"):
    s = e["scenarios"][key]
    before, after = e["fpp"]["winner"], s["winner"]
    return f'''
<article class="card">
  <header>
    <h3>{esc(e["electorate"])}</h3>
    <p class="swap">{chip(before["party"])}{ARROW}{chip(after["party"])}</p>
  </header>
  <p class="detail">{esc(before["name"])} won by {n(e["fpp"]["margin"])} under first past the post.
  With transfers, {esc(after["name"])} wins by {n(s["margin"])} ({n(s["exhausted"])} votes exhausted).</p>
  {rounds_table(e, s)}
</article>'''


def electorate_row(e):
    s = e["scenarios"]["brief"]
    flipped = s["flipped"]
    note = f'<p class="note">{esc(e["source"])}</p>' if "by-election" in e["source"] else ""
    return f'''
<details class="row{" flipped" if flipped else ""}">
  <summary>
    {CHEVRON}
    <span class="name">{esc(e["electorate"])}</span>
    <span class="was">{chip(e["fpp"]["winner"]["party"])}</span>
    <span class="now">{chip(s["winner"]["party"]) if flipped else '<span class="same">no change</span>'}</span>
    <span class="margin">{n(s["margin"])}</span>
  </summary>
  <div class="body">{note}{rounds_table(e, s)}</div>
</details>'''


def method_notes(data, two_way_note):
    if data["year"] == "2023":
        notes = [
            "Candidate votes are the official 2023 electorate results, taken from each electorate's Wikipedia article.",
            "Port Waikato's general election electorate vote was cancelled after a candidate died, so the 25 November 2023 by-election is used. No Labour, Green or ACT candidate stood, so STV cannot change it.",
        ]
    else:
        notes = [
            "Candidate votes are the Electoral Commission's preliminary 2026 electorate results. They exclude special votes (about 14% of all votes), and official results are due on 27 November 2026, so close seats could still change.",
            "Candidates' parties come from Wikipedia's list of 2026 candidates by electorate. Candidates missing from that list are shown as Unlisted and their votes exhaust; none of them could change a result even if they belonged to the Green or ACT party.",
        ]
    notes += [
        "Electorate votes already include tactical voting: many Green and ACT supporters voted for the Labour or National candidate, which keeps the effect modest.",
        "In the Māori electorates the brief's assumption is strongest: many Green voters there might rank Te Pāti Māori ahead of Labour.",
        two_way_note,
    ]
    return "".join(f"<li>{esc(note)}</li>" for note in notes)


SOURCES = [
    ("2023", [
        ("Official 2023 electorate candidate votes, as transcribed in each electorate's Wikipedia article",
         "https://en.wikipedia.org/wiki/Candidates_in_the_2023_New_Zealand_general_election_by_electorate"),
        ("Original source: Electoral Commission, 2023 General Election official results",
         "https://www.electionresults.govt.nz/electionresults_2023/"),
        ("Port Waikato: 2023 by-election result, from the electorate's Wikipedia article",
         "https://en.wikipedia.org/wiki/Port_Waikato_(New_Zealand_electorate)"),
    ]),
    ("2026", [
        ("Candidate votes: Electoral Commission, 2026 General Election preliminary count, electorate spreadsheets, downloaded 9 November 2026",
         "https://electionresults.govt.nz/ge2026/"),
        ("Candidate parties: Wikipedia, Candidates in the 2026 New Zealand general election by electorate, retrieved 9 November 2026",
         "https://en.wikipedia.org/wiki/Candidates_in_the_2026_New_Zealand_general_election_by_electorate"),
    ]),
]

DISCLAIMERS = [
    "This is a hypothetical what-if model, not a prediction and not an official result.",
    "It is an independent hobby project and is not affiliated with or endorsed by the Electoral Commission or any political party.",
    "The second preferences (Green to Labour, ACT to National) are assumptions from the brief, not survey data. Real voters rank candidates in many different ways.",
    "The votes were cast under first past the post. Under a real STV system, candidates, campaigns and voters would all behave differently.",
    "2026 figures are preliminary and will change when special votes are counted. The official result is due on 27 November 2026.",
    "Figures were collected and processed automatically and may contain errors. For official results, see the Electoral Commission.",
    "Wikipedia content is used under the CC BY-SA 4.0 licence.",
]


def source_link(label, url):
    return f'<li><a href="{esc(url)}">{esc(label)}</a></li>'


def footer():
    sources = "".join(
        f'<h3>{year}</h3><ul>{"".join(source_link(label, url) for label, url in items)}</ul>'
        for year, items in SOURCES)
    disclaimers = "".join(f"<li>{esc(d)}</li>" for d in DISCLAIMERS)
    return f'''
<footer class="foot" id="sources">
  <section>
    <h2>Data sources</h2>
    {sources}
  </section>
  <section>
    <h2>Disclaimer</h2>
    <ul>{disclaimers}</ul>
  </section>
</footer>'''



DEFAULT_YEAR = "2026"


def year_toggle(years, default):
    buttons = "".join(
        f'<button type="button" class="yr{" on" if year == default else ""}" data-year="{year}" '
        f'aria-pressed="{"true" if year == default else "false"}">{year}</button>'
        for year in years)
    return f'<div class="years" role="group" aria-label="Election year">{buttons}</div>'


def year_panel(data, default):
    year = data["year"]
    electorates = sorted(data["electorates"], key=lambda e: e["electorate"])
    partial = len(electorates) < data["expected_electorates"]
    status = (f'<p class="status">Partial count: {len(electorates)} of {data["expected_electorates"]} electorates loaded.</p>'
              if partial else "")
    status += ('<p class="status">Preliminary results. Special votes and the official count (27 November 2026) are still to come.</p>'
               if data["preliminary"] else "")
    flips = sorted((e for e in electorates if e["scenarios"]["brief"]["flipped"]),
                   key=lambda e: e["scenarios"]["brief"]["margin"])
    fpp = totals(electorates, lambda e: e["fpp"]["winner"])
    stv = totals(electorates, lambda e: e["scenarios"]["brief"]["winner"])
    count = len(electorates)
    two_way_extra = sorted(
        (e for e in electorates
         if e["scenarios"]["two-way"]["winner"]["name"] != e["scenarios"]["brief"]["winner"]["name"]),
        key=lambda e: e["scenarios"]["two-way"]["margin"])
    two_way_section = ""
    if two_way_extra:
        two_way_section = (
            f'<h2>Two-way transfers: {len(two_way_extra)} more seat{"s" if len(two_way_extra) != 1 else ""} change</h2>'
            '<p class="lede">The brief only sends Green votes to Labour and ACT votes to National. '
            'If Labour votes also went to the Green candidate and National votes to the ACT candidate:</p>'
            f'<div class="cards">{"".join(flip_card(e, "two-way") for e in two_way_extra)}</div>')
    two_way_note = ("Adding the reverse transfers (Labour → Green, National → ACT) changes nothing here."
                    if not two_way_extra else
                    "Adding the reverse transfers (Labour → Green, National → ACT) changes some results.")
    hidden = "" if year == default else " hidden"
    return f'''
<section class="year" id="y{year}" data-year="{year}"{hidden}>
  <p class="lede">The {esc(data["election"])}'s {count} electorate races, recounted as single-seat STV (instant runoff).
  Green candidates' votes transfer to the Labour candidate, ACT candidates' votes transfer to the National candidate,
  and every other vote exhausts when its candidate is eliminated.</p>
  {status}

  <div class="compare">
    <div class="panel"><h2>Actual result (first past the post)</h2>{seat_bar(fpp, count)}</div>
    <div class="panel"><h2>With STV transfers</h2>{seat_bar(stv, count)}</div>
  </div>

  <h2>{len(flips)} seat{"s" if len(flips) != 1 else ""} change hands</h2>
  <div class="cards">{"".join(flip_card(e) for e in flips)}</div>

  {two_way_section}

  <h2>All electorates</h2>
  <div class="list">
    <div class="list-head"><span></span><span>Electorate</span><span>Actual</span><span>Under STV</span><span>Margin</span></div>
    {"".join(electorate_row(e) for e in electorates)}
  </div>

  <h2>Method and caveats</h2>
  <ul class="method">{method_notes(data, two_way_note)}</ul>
</section>'''


SCRIPT = """
<script>
(function () {
  var buttons = document.querySelectorAll('.yr');
  var panels = document.querySelectorAll('section.year');
  function toFinalRound(root) {
    root.querySelectorAll('.scroll').forEach(function (s) { s.scrollLeft = s.scrollWidth; });
  }
  function show(year, push) {
    var found = false;
    panels.forEach(function (p) { if (p.dataset.year === year) found = true; });
    if (!found) return;
    panels.forEach(function (p) {
      p.hidden = p.dataset.year !== year;
      if (!p.hidden) toFinalRound(p);
    });
    buttons.forEach(function (b) {
      var on = b.dataset.year === year;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (push) history.replaceState(null, '', year === DEFAULT ? location.pathname : '#' + year);
  }
  var DEFAULT = document.body.dataset.default;
  buttons.forEach(function (b) { b.addEventListener('click', function () { show(b.dataset.year, true); }); });
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.querySelectorAll('details').forEach(function (d) {
    d.addEventListener('toggle', function () { if (d.open) toFinalRound(d); });
    var summary = d.querySelector('summary');
    var body = d.querySelector('.body');
    var anim = null;
    summary.addEventListener('click', function (e) {
      if (reduceMotion.matches || !body.animate) return;
      e.preventDefault();
      var start = d.open ? body.offsetHeight : 0;
      if (anim) anim.cancel();
      var closing = d.open && d.dataset.closing !== '1';
      if (closing) {
        d.dataset.closing = '1';
        anim = body.animate([{ height: start + 'px', opacity: 1 }, { height: '0px', opacity: 0 }],
                            { duration: 200, easing: 'ease-in' });
        anim.onfinish = function () { d.open = false; d.dataset.closing = ''; anim = null; };
      } else {
        d.dataset.closing = '';
        d.open = true;
        var end = body.scrollHeight;
        anim = body.animate([{ height: (start || 0) + 'px', opacity: start ? 1 : 0 }, { height: end + 'px', opacity: 1 }],
                            { duration: 240, easing: 'cubic-bezier(.2,.7,.3,1)' });
        anim.onfinish = function () { anim = null; };
      }
    });
  });
  toFinalRound(document);
  var fromHash = location.hash.replace('#', '');
  if (fromHash) show(fromHash, false);
  window.addEventListener('hashchange', function () { show(location.hash.replace('#', '') || DEFAULT, false); });
})();
</script>
"""


def page(loaded, years, default):
    panels = "".join(year_panel(loaded[year], default) for year in years)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Electorates Under STV</title>
<style>
:root {{
  --bg: #f7f6f2; --panel: #ffffff; --ink: #1c1d21; --muted: #626672; --line: #e2e0d9;
  --hover: #efede6; --accent: #1c1d21;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #131417; --panel: #1c1d22; --ink: #ecebe6; --muted: #9a9ea8; --line: #2c2e35;
    --hover: #24262c; --accent: #ecebe6;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #131417; --panel: #1c1d22; --ink: #ecebe6; --muted: #9a9ea8; --line: #2c2e35;
  --hover: #24262c; --accent: #ecebe6;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 960px; margin: 0 auto; padding: 40px 16px 80px; }}
h1 {{ font-size: clamp(28px, 5vw, 40px); line-height: 1.1; margin: 0 0 12px; letter-spacing: -0.02em; }}
h2 {{ font-size: 20px; margin: 48px 0 12px; }}
h3 {{ font-size: 18px; margin: 0; }}
.lede {{ color: var(--muted); max-width: 64ch; margin: 0; }}
.compare {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr)); margin-top: 28px; }}
.panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; min-width: 0; }}
.panel h2 {{ margin: 0 0 12px; font-size: 15px; color: var(--muted); font-weight: 600; }}
.bar {{ display: flex; height: 18px; border-radius: 4px; overflow: hidden; gap: 2px; }}
.seg {{ background: var(--c); }}
.legend {{ list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-wrap: wrap; gap: 8px 14px; }}
.legend li {{ display: flex; align-items: center; gap: 6px; }}
.chip {{ display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 600; white-space: nowrap; }}
.chip::before {{ content: ""; width: 10px; height: 10px; border-radius: 3px; background: var(--c); }}
.cards {{ display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr); }}
.card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 18px; min-width: 0; }}
.card header {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; align-items: center; }}
.swap {{ display: flex; align-items: center; gap: 8px; margin: 0; }}
.arrow {{ width: 16px; height: 16px; color: var(--muted); }}
.detail {{ color: var(--muted); margin: 8px 0 12px; }}
.scroll {{ overflow-x: auto; }}
table.rounds {{ border-collapse: collapse; font-size: 13px; font-variant-numeric: tabular-nums; width: 100%; }}
.rounds th, .rounds td {{ padding: 6px 10px; border-bottom: 1px solid var(--line); text-align: right; white-space: nowrap; }}
.rounds th[scope="row"], .rounds thead th:first-child {{ text-align: left; font-weight: 500;
  position: sticky; left: 0; z-index: 1; background: var(--panel); white-space: normal; min-width: 140px;
  box-shadow: inset -1px 0 0 var(--line); }}
.cand {{ display: flex; align-items: flex-start; gap: 8px; }}
.dot {{ flex: none; width: 10px; height: 10px; margin-top: 4px; border-radius: 3px; background: var(--c); }}
.cn {{ display: block; }}
.cand small {{ display: block; color: var(--muted); font-size: 12px; font-weight: 400; }}
.rounds thead th {{ color: var(--muted); font-weight: 600; }}
.rounds td.out {{ color: var(--muted); opacity: .6; }}
.rounds tr.won th, .rounds tr.won td:last-child {{ font-weight: 700; }}
.rounds tr.ex th, .rounds tr.ex td {{ color: var(--muted); }}
.list {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
.list-head, summary {{ display: grid; grid-template-columns: 18px 1fr 110px 110px 70px; gap: 10px; align-items: center; padding: 10px 14px; }}
.list-head {{ color: var(--muted); font-size: 13px; font-weight: 600; border-bottom: 1px solid var(--line); }}
.list-head span:last-child, .margin {{ text-align: right; font-variant-numeric: tabular-nums; }}
details {{ border-bottom: 1px solid var(--line); }}
details:last-child {{ border-bottom: 0; }}
summary {{ cursor: pointer; list-style: none; }}
summary::-webkit-details-marker {{ display: none; }}
summary:hover {{ background: var(--hover); }}
summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
.chev {{ width: 14px; height: 14px; color: var(--muted); transition: transform .15s; }}
details[open]:not([data-closing="1"]) .chev {{ transform: rotate(90deg); }}
.chev {{ transition: transform .2s ease; }}
details.flipped .name {{ font-weight: 700; }}
.same {{ color: var(--muted); font-size: 13px; }}
.body {{ padding: 4px 14px 16px 42px; overflow: hidden; }}
.note {{ color: var(--muted); font-size: 13px; margin: 0 0 8px; }}
.method {{ color: var(--muted); max-width: 70ch; }}
.method li {{ margin-bottom: 6px; }}
.years {{ display: inline-flex; gap: 4px; padding: 4px; margin: 8px 0 24px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel); }}
.yr {{ border: 0; background: none; cursor: pointer; font-family: inherit; padding: 6px 14px; border-radius: 7px; font-weight: 600; font-size: 14px; color: var(--muted); text-decoration: none; }}
.yr:hover {{ background: var(--hover); color: var(--ink); }}
.yr:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
.yr.on, .yr.on:hover {{ background: var(--ink); color: var(--bg); }}
.foot {{ margin-top: 56px; padding-top: 24px; border-top: 1px solid var(--line); color: var(--muted); font-size: 14px;
  display: grid; gap: 8px 40px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }}
.foot h2 {{ font-size: 15px; margin: 0 0 8px; color: var(--ink); }}
.foot h3 {{ font-size: 13px; margin: 12px 0 4px; color: var(--ink); }}
.foot ul {{ margin: 0; padding-left: 18px; }}
.foot li {{ margin-bottom: 6px; }}
.foot a {{ color: inherit; text-decoration: underline; text-decoration-color: var(--line); text-underline-offset: 3px; overflow-wrap: anywhere; }}
.foot a:hover {{ color: var(--ink); text-decoration-color: currentColor; }}
.foot a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.status {{ margin: 12px 0 0; padding: 10px 14px; border-radius: 8px; background: var(--hover); font-size: 14px; max-width: 64ch; }}
@media (max-width: 560px) {{
  main {{ padding-top: 28px; }}
  h2 {{ font-size: 18px; margin-top: 36px; }}
  .card, .panel {{ padding: 14px; }}
  .detail {{ font-size: 15px; }}
  .rounds th, .rounds td {{ padding: 6px 8px; }}
  .list-head, summary {{ grid-template-columns: 14px minmax(0, 1fr) 100px 100px; gap: 8px; padding: 10px 12px; }}
  .list-head span:last-child, .margin {{ display: none; }}
  summary .chip {{ font-size: 12px; }}
  .body {{ padding: 4px 12px 14px; }}
}}
</style>
</head>
<body data-default="{default}">
<main>
  <h1>What if electorates used STV?</h1>
  {year_toggle(years, default)}
  {panels}
  {footer()}
</main>
{SCRIPT}
</body>
</html>
'''


def main():
    loaded = {}
    for path in sorted((ROOT / "data").glob("results_*.json")):
        data = json.loads(path.read_text())
        loaded[data["year"]] = data
    years = sorted(loaded, reverse=True)
    default = DEFAULT_YEAR if DEFAULT_YEAR in loaded else years[0]
    (ROOT / "index.html").write_text(page(loaded, years, default))
    print(f"wrote index.html with {', '.join(years)}; loads on {default}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
