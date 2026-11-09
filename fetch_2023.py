import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "wiki2023"
API = "https://en.wikipedia.org/w/api.php"
UA = "nz-stv-hobby-analysis/0.1 (personal research script)"


def api_get(params):
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    request = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            time.sleep(int(error.headers.get("Retry-After") or 10 * (attempt + 1)))
    raise RuntimeError("rate limited")


def wikitexts(titles):
    found = {}
    for start in range(0, len(titles), 50):
        chunk = titles[start:start + 50]
        data = api_get({
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "redirects": 1,
            "titles": "|".join(chunk),
        })
        query = data["query"]
        aliases = {}
        for step in query.get("normalized", []) + query.get("redirects", []):
            aliases[step["to"]] = aliases.get(step["from"], step["from"])
        for page in query["pages"]:
            revisions = page.get("revisions")
            if not revisions:
                continue
            text = revisions[0]["slots"]["main"]["content"]
            original = page["title"]
            while original in aliases:
                original = aliases[original]
            found[original] = (page["title"], text)
            found[page["title"]] = (page["title"], text)
        time.sleep(1)
    return found


def electorate_names():
    data = api_get({
        "action": "parse",
        "page": "Candidates in the 2023 New Zealand general election by electorate",
        "prop": "wikitext",
    })
    return re.findall(r"^===\s*([^=]+?)\s*===\s*$", data["parse"]["wikitext"], re.M)


def has_2023_box(text):
    return bool(text) and "2023 New Zealand general election" in text and "MMP election box" in text


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = [n for n in electorate_names() if not (OUT / f"{n}.json").exists()]
    primary = wikitexts([f"{n} (New Zealand electorate)" for n in names])
    fallback = wikitexts(names)
    missing = []
    for name in names:
        hit = primary.get(f"{name} (New Zealand electorate)")
        if not (hit and has_2023_box(hit[1])):
            hit = fallback.get(name)
        if not (hit and has_2023_box(hit[1])):
            missing.append(name)
            continue
        title, text = hit
        (OUT / f"{name}.json").write_text(
            json.dumps({"electorate": name, "title": title, "wikitext": text}, ensure_ascii=False))
    print(f"fetched {len(names) - len(missing)}, missing: {missing}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
