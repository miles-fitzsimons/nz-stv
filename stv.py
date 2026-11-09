import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

import xlsx

ROOT = Path(__file__).resolve().parent

PARTY_KEYS = {
    "New Zealand National Party": "National",
    "New Zealand Labour Party": "Labour",
    "Green Party of Aotearoa New Zealand": "Green",
    "ACT New Zealand": "ACT",
    "New Zealand First": "NZ First",
    "Te Pāti Māori": "Te Pāti Māori",
    "The Opportunity Party": "TOP",
    "The Opportunities Party": "TOP",
}

SCENARIOS = {
    "brief": {
        "label": "As briefed: Green → Labour, ACT → National",
        "transfers": {"Green": "Labour", "ACT": "National"},
    },
    "two-way": {
        "label": "Two-way: also Labour → Green, National → ACT",
        "transfers": {"Green": "Labour", "ACT": "National", "Labour": "Green", "National": "ACT"},
    },
}

EXCLUDED_TEMPLATES = ("begin", "party only", "informal", "total", "majority", "turnout", "end")


def split_templates(segment):
    templates, depth, start = [], 0, None
    i = 0
    while i < len(segment) - 1:
        pair = segment[i:i + 2]
        if pair == "{{":
            if depth == 0:
                start = i
            depth += 1
            i += 2
        elif pair == "}}":
            depth -= 1
            if depth == 0 and start is not None:
                templates.append(segment[start + 2:i])
            i += 2
        else:
            i += 1
    return templates


def top_level_fields(body):
    fields, depth, current = [], 0, []
    i = 0
    while i < len(body):
        pair = body[i:i + 2]
        if pair in ("{{", "[["):
            depth += 1
            current.append(pair)
            i += 2
        elif pair in ("}}", "]]"):
            depth -= 1
            current.append(pair)
            i += 2
        elif body[i] == "|" and depth == 0:
            fields.append("".join(current))
            current = []
            i += 1
        else:
            current.append(body[i])
            i += 1
    fields.append("".join(current))
    name = fields[0].strip()
    values = {}
    for field in fields[1:]:
        if "=" in field:
            key, value = field.split("=", 1)
            values[key.strip()] = value.strip()
    return name, values


def clean_name(raw):
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", raw, flags=re.S)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    return text.strip()


def parse_votes(raw):
    digits = re.sub(r"[^\d]", "", re.sub(r"<ref.*", "", raw, flags=re.S))
    return int(digits) if digits else None


def candidates_in(segment, prefix):
    found = []
    for body in split_templates(segment):
        name, values = top_level_fields(body)
        if not name.startswith(prefix):
            continue
        variant = name[len(prefix):].strip()
        if any(word in variant for word in EXCLUDED_TEMPLATES):
            continue
        if "candidate" not in values or "votes" not in values:
            continue
        votes = parse_votes(values["votes"])
        if votes is None:
            continue
        party_full = clean_name(values.get("party", "")) or "Independent"
        found.append({
            "name": clean_name(values["candidate"]),
            "party_full": party_full,
            "party": PARTY_KEYS.get(party_full, party_full),
            "votes": votes,
        })
    return sorted(found, key=lambda c: -c["votes"])


def electorate_2023(record):
    text = record["wikitext"]
    match = re.search(r"\{\{\s*MMP election box begin[^\n]*2023 (?:New Zealand )?general election", text)
    if match:
        end = text.find("MMP election box begin", match.end())
        candidates = candidates_in(text[match.start():end if end > 0 else None], "MMP election box")
        if candidates:
            return {"source": "2023 general election (official)", "candidates": candidates}
    match = re.search(r"\{\{\s*MMP by-election box begin\s*\|\s*electorate\s*=[^|]*\|\s*year\s*=\s*2023", text)
    if match:
        end = text.find("box begin", match.end())
        candidates = candidates_in(text[match.start():end if end > 0 else None], "MMP by-election box")
        return {"source": "2023 by-election (general election electorate vote cancelled)", "candidates": candidates}
    raise ValueError(f"no 2023 result for {record['electorate']}")


def run_stv(candidates, transfers):
    by_party = {}
    for index, candidate in enumerate(candidates):
        by_party.setdefault(candidate["party"], index)
    piles = [[[index], candidate["votes"]] for index, candidate in enumerate(candidates)]
    for pile in piles:
        party = candidates[pile[0][0]]["party"]
        if party in transfers and transfers[party] in by_party:
            pile[0].append(by_party[transfers[party]])
    continuing = set(range(len(candidates)))
    rounds = []
    exhausted = 0
    while True:
        tallies = {index: 0 for index in continuing}
        exhausted = 0
        for preferences, votes in piles:
            current = next((p for p in preferences if p in continuing), None)
            if current is None:
                exhausted += votes
            else:
                tallies[current] += votes
        active = sum(tallies.values())
        leader = max(tallies, key=lambda i: (tallies[i], -i))
        rounds.append({
            "tallies": {candidates[i]["name"]: tallies[i] for i in sorted(tallies, key=lambda i: -tallies[i])},
            "exhausted": exhausted,
        })
        if tallies[leader] * 2 > active or len(continuing) <= 1:
            ordered = sorted(tallies, key=lambda i: -tallies[i])
            runner_up = ordered[1] if len(ordered) > 1 else None
            return {
                "winner": candidates[leader],
                "runner_up": candidates[runner_up] if runner_up is not None else None,
                "winner_votes": tallies[leader],
                "runner_up_votes": tallies[runner_up] if runner_up is not None else 0,
                "active": active,
                "exhausted": exhausted,
                "rounds": rounds,
            }
        lowest = min(tallies, key=lambda i: (tallies[i], -i))
        continuing.remove(lowest)


def summarise(name, info):
    candidates = info["candidates"]
    first_past = candidates[0]
    result = {
        "electorate": name,
        "source": info["source"],
        "candidates": candidates,
        "fpp": {"winner": first_past, "margin": first_past["votes"] - (candidates[1]["votes"] if len(candidates) > 1 else 0)},
        "scenarios": {},
    }
    for key, scenario in SCENARIOS.items():
        outcome = run_stv(candidates, scenario["transfers"])
        outcome["flipped"] = outcome["winner"]["name"] != first_past["name"]
        outcome["margin"] = outcome["winner_votes"] - outcome["runner_up_votes"]
        result["scenarios"][key] = outcome
    return result


def name_key(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    return re.sub(r"[^a-z ]", "", plain.replace("-", " ")).split()


ELECTORATE_ALIASES = {"Mt Albert": "Mount Albert", "Mt Maunganui": "Mount Maunganui", "Mt Roskill": "Mount Roskill"}


def match_candidate(sheet_name, wiki_candidates):
    surname, _, given = sheet_name.partition(",")
    target = name_key(f"{given} {surname}")
    for candidate in wiki_candidates:
        if name_key(candidate["name"]) == target:
            return candidate
    surname_tokens = set(name_key(surname))
    given_tokens = name_key(given)
    first_given = given_tokens[0] if given_tokens else None
    strong = [c for c in wiki_candidates
              if surname_tokens & set(name_key(c["name"])) and first_given in name_key(c["name"])]
    if len(strong) == 1:
        return strong[0]
    weak = [c for c in wiki_candidates if surname_tokens & set(name_key(c["name"]))]
    if len(weak) == 1:
        return weak[0]
    return None


def match_party(sheet_name, wiki_candidates, overrides=None):
    if overrides and sheet_name in overrides:
        return overrides[sheet_name]
    candidate = match_candidate(sheet_name, wiki_candidates)
    if candidate:
        return candidate["party_full"]
    raise ValueError(f"no party match for {sheet_name!r} among {[c['name'] for c in wiki_candidates]}")


def display_name(sheet_name):
    surname, _, given = sheet_name.partition(",")
    return f"{given.strip()} {surname.strip().title()}"


def load_2026():
    wiki = json.loads((ROOT / "data" / "wiki2026_candidates.json").read_text())
    overrides = json.loads((ROOT / "data" / "party_overrides_2026.json").read_text())
    electorates = []
    for path in sorted(glob.glob(str(ROOT / "data" / "ec2026" / "*.xlsx"))):
        rows = xlsx.sheets(path)["Candidate"]
        header = rows[0]
        name = re.match(r"\d+\s+(.*?)\s+-\s+Candidate", header[0]).group(1)
        name = ELECTORATE_ALIASES.get(name, name)
        total = next(r for r in rows if r[0].strip().endswith("TOTAL"))
        candidates = []
        for column, sheet_name in enumerate(header[1:], start=1):
            if not sheet_name or sheet_name.startswith(("Total", "Informal")):
                continue
            try:
                party_full = match_party(sheet_name, wiki[name], overrides)
            except ValueError:
                party_full = "Unlisted"
            wiki_candidate = match_candidate(sheet_name, wiki[name])
            candidates.append({
                "name": wiki_candidate["name"] if wiki_candidate else display_name(sheet_name),
                "party_full": party_full,
                "party": PARTY_KEYS.get(party_full, party_full),
                "votes": int(total[column]),
            })
        electorates.append((name, {
            "source": "2026 general election (preliminary)",
            "candidates": sorted(candidates, key=lambda c: -c["votes"]),
        }))
    return electorates, len(wiki)


def load_2023():
    records = [json.loads(Path(f).read_text()) for f in sorted(glob.glob(str(ROOT / "data" / "wiki2023" / "*.json")))]
    return [(r["electorate"], electorate_2023(r)) for r in records], 72


def main():
    year = sys.argv[1] if len(sys.argv) > 1 else "2023"
    loaded, expected = {"2023": load_2023, "2026": load_2026}[year]()
    results = [summarise(name, info) for name, info in loaded]
    output = {
        "year": year,
        "election": f"{year} New Zealand general election",
        "preliminary": year == "2026",
        "expected_electorates": expected,
        "scenarios": {k: v["label"] for k, v in SCENARIOS.items()},
        "electorates": results,
    }
    (ROOT / "data" / f"results_{year}.json").write_text(json.dumps(output, ensure_ascii=False, indent=1))
    print(f"{len(results)} of {expected} electorates")
    for key in SCENARIOS:
        flips = [r for r in results if r["scenarios"][key]["flipped"]]
        print(f"\n== {SCENARIOS[key]['label']}: {len(flips)} flips")
        for r in flips:
            s = r["scenarios"][key]
            print(f"  {r['electorate']}: {r['fpp']['winner']['party']} ({r['fpp']['winner']['name']}, FPP margin {r['fpp']['margin']})"
                  f" -> {s['winner']['party']} ({s['winner']['name']}) by {s['margin']}, exhausted {s['exhausted']}")
    tally = {}
    for r in results:
        tally.setdefault("FPP", {}).setdefault(r["fpp"]["winner"]["party"], 0)
        tally["FPP"][r["fpp"]["winner"]["party"]] += 1
        for key in SCENARIOS:
            party = r["scenarios"][key]["winner"]["party"]
            tally.setdefault(key, {}).setdefault(party, 0)
            tally[key][party] += 1
    print("\nseat totals:", json.dumps(tally, ensure_ascii=False, indent=1))
    print("candidate counts per electorate:", sorted({len(r["candidates"]) for r in results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
