import json
import re
import sys
from pathlib import Path

from fetch_2023 import api_get

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "wiki2026_candidates.json"
PAGE = "Candidates in the 2026 New Zealand general election by electorate"


def clean(raw):
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", raw, flags=re.S)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    return re.sub(r"\{\{[^}]*\}\}", "", text).strip()


def main():
    text = api_get({"action": "parse", "page": PAGE, "prop": "wikitext"})["parse"]["wikitext"]
    electorates = {}
    sections = re.split(r"^===\s*([^=]+?)\s*===\s*$", text, flags=re.M)
    for name, body in zip(sections[1::2], sections[2::2]):
        candidates = []
        for block in re.findall(r"\{\{NZ election box (?:candidate|incumbent)(.*?)\n\}\}", body, re.S):
            party = re.search(r"\|\s*party\s*=\s*([^\n]*)", block)
            candidate = re.search(r"\|\s*candidate\s*=\s*([^\n]*)", block)
            if candidate:
                candidates.append({
                    "name": clean(candidate.group(1)),
                    "party_full": clean(party.group(1)) if party else "Independent",
                })
        electorates[name] = candidates
    OUT.write_text(json.dumps(electorates, ensure_ascii=False, indent=1))
    print(f"{len(electorates)} electorates, {sum(len(c) for c in electorates.values())} candidates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
