#!/usr/bin/env python3
"""Pull early-career tech postings in HK / SG / KR from public ATS job-board APIs
(Greenhouse, Lever, Ashby) listed in data/sources.json, and merge them into
data/internships.json.

- New matching postings are added with "source": "auto".
- Auto postings that disappear from the company's board are marked closed.
- Manually added entries (no "source": "auto") are never touched.
"""
import concurrent.futures as cf
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources.json"
DATA = ROOT / "data" / "internships.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; asia-tech-internships; +https://github.com/mck0124/asia-tech-internships)"}

COUNTRY_PATTERNS = {
    "HK": re.compile(r"hong\s*kong|\bHK\b", re.I),
    "SG": re.compile(r"singapore|\bSG\b", re.I),
    "KR": re.compile(r"seoul|korea|pangyo|seongnam|busan|서울|판교", re.I),
}
EARLY = re.compile(r"\bintern(s|ship)?\b|\bgraduate\b|new[\s-]?grad|\bcampus\b|summer analyst|\bco-?op\b|\bplacement\b|인턴|신입", re.I)
TECH = re.compile(r"software|engineer|developer|quant|research|trad(er|ing)|data|machine learning|\bml\b|\bai\b|scien|"
                  r"infrastructure|security|hardware|fpga|systems|\bsre\b|devops|product manag|technolog|algorithm", re.I)
EXCLUDE = re.compile(r"recruit|audit|accounting|\bsales\b|marketing|legal|counsel|\btax\b|compliance|human resources|"
                     r"\bpeople\b|talent|designer|\bvip\b|customer|business development|economist", re.I)
SEASON = re.compile(r"(summer|winter|spring|fall|autumn|off[\s-]?cycle)[^\d]{0,12}(20\d\d)|(20\d\d)\s*(summer|winter|spring|fall|autumn)"
                    r"|\(?(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(to|-|–)\s*[a-z]+\s*(20\d\d)", re.I)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


def greenhouse(slug):
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")["jobs"]:
        yield j["title"], j["location"]["name"] or "", j["absolute_url"]


def lever(slug):
    for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        c = j.get("categories", {})
        locs = c.get("allLocations") or [c.get("location", "")]
        yield j["text"], "; ".join(l for l in locs if l), j["hostedUrl"]


def ashby(slug):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", [])]
        yield j["title"], "; ".join(l for l in locs if l), j["jobUrl"]


ATS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


def category(title, company_type):
    t = title.lower()
    if re.search(r"product manag", t):
        return "Product"
    if re.search(r"quant|trad(er|ing)", t) or (company_type == "quant" and re.search(r"research", t)):
        return "Quant"
    if re.search(r"machine learning|\bml\b|\bai\b|research scien|deep learning|llm", t):
        return "AI/ML"
    if re.search(r"hardware|fpga|asic|chip|embedded", t):
        return "Hardware"
    if re.search(r"\bdata\b", t):
        return "Data"
    return "SWE"


def season(title):
    m = SEASON.search(title)
    if m:
        if m.group(1):
            return f"{m.group(1).title()} {m.group(2)}"
        if m.group(3):
            return f"{m.group(4).title()} {m.group(3)}"
        return m.group(0).strip("() ")
    if re.search(r"new[\s-]?grad|\bgraduate\b|신입", title, re.I):
        y = re.search(r"20\d\d", title)
        return f"New Grad {y.group(0)}" if y else "New Grad"
    y = re.search(r"20\d\d", title)
    return y.group(0) if y else "—"


def collect(src):
    out = []
    for title, loc, url in ATS[src["ats"]](src["slug"]):
        title = " ".join(title.split())
        countries = [c for c, p in COUNTRY_PATTERNS.items() if p.search(loc)]
        if not countries or not EARLY.search(title) or not TECH.search(title) or EXCLUDE.search(title):
            continue
        locs = [l.strip() for l in re.split(r"[;|/]", loc) if l.strip()]
        out.append({
            "company": src["company"],
            "role": title,
            "category": category(title, src.get("type")),
            "locations": locs,
            "countries": countries,
            "season": season(title),
            "url": url,
            "status": "open",
            "source": "auto",
        })
    return out


def main():
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = json.loads(DATA.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()

    found, ok_companies = {}, set()
    with cf.ThreadPoolExecutor(12) as ex:
        futures = {ex.submit(collect, s): s for s in sources}
        for f in cf.as_completed(futures):
            s = futures[f]
            try:
                for e in f.result():
                    found[e["url"]] = e
                ok_companies.add(s["company"])
            except Exception as err:  # one broken board must not break the run
                print(f"warn: {s['company']} ({s['ats']}:{s['slug']}): {err}", file=sys.stderr)

    by_url = {e["url"]: e for e in entries}
    added = closed = 0
    for url, e in found.items():
        if url in by_url:
            old = by_url[url]
            if old.get("source") == "auto" and old["status"] == "closed" and not old.get("deadline"):
                old["status"] = "open"  # reposted
        else:
            e["added"] = today
            entries.append(e)
            added += 1
    for e in entries:
        # only close if that company's board was fetched successfully this run
        if e.get("source") == "auto" and e["status"] == "open" and e["url"] not in found and e["company"] in ok_companies:
            e["status"] = "closed"
            closed += 1

    DATA.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"fetch: {len(ok_companies)}/{len(sources)} boards ok, +{added} new, {closed} closed, "
          f"{sum(e['status'] == 'open' for e in entries)} open total")


if __name__ == "__main__":
    main()
