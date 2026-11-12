#!/usr/bin/env python3
"""Pull early-career tech postings in HK / SG / KR from public ATS job-board APIs
(Greenhouse, Lever, Ashby, SmartRecruiters, Workday) listed in data/sources.json, and merge them into
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
import urllib.parse
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
                  r"infrastructure|security|hardware|fpga|systems|\bsre\b|devops|product manag|technolog|algorithm|"
                  r"개발|엔지니어|연구|데이터|보안|인프라|서버|백엔드|프론트|모델|\bAI\b", re.I)
EXCLUDE = re.compile(r"recruit|audit|accounting|\bsales\b|marketing|legal|counsel|\btax\b|compliance|human resources|"
                     r"\bpeople\b|talent|designer|\bvip\b|customer|business development|economist|"
                     r"상담|영업|마케팅|디자인|비서|채용|인사|총무|회계|법무|어시스턴트", re.I)
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


def smartrecruiters(slug):
    offset = 0
    while True:
        d = get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}")
        for j in d.get("content", []):
            loc = j.get("location", {})
            where = ", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country")) if x)
            yield j["name"], where, f"https://jobs.smartrecruiters.com/{slug}/{j['id']}"
        offset += 100
        if offset >= d.get("totalFound", 0) or offset >= 2000:
            break


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**UA, "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def workday(slug):
    """slug = "tenant|wdN|site", e.g. "nvidia|5|NVIDIAExternalCareerSite"."""
    tenant, n, site = slug.split("|")
    host = f"https://{tenant}.wd{n}.myworkdayjobs.com"
    api = f"{host}/wday/cxs/{tenant}/{site}"
    seen = set()
    for query in ("intern", "graduate", "new grad"):
        for offset in range(0, 400, 20):
            d = post(f"{api}/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": query})
            posts = d.get("jobPostings", [])
            for j in posts:
                path = j.get("externalPath")
                if not path or path in seen:
                    continue
                seen.add(path)
                title, loc = j.get("title", ""), j.get("locationsText", "")
                # "3 Locations" hides the real list: look it up, but only for plausible matches
                if re.match(r"\d+ Locations", loc) and EARLY.search(title) and TECH.search(title):
                    try:
                        info = get(f"{api}{path}").get("jobPostingInfo", {})
                        loc = "; ".join([info.get("location", "")] + info.get("additionalLocations", []))
                    except Exception:
                        pass
                yield title, loc, f"{host}/{site}{path}"
            if len(posts) < 20:
                break


BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"}


def get_browser(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=30) as r:
        return json.load(r)


def janestreet(_):
    cities = {"HKG": "Hong Kong", "SGP": "Singapore"}
    for j in get_browser("https://www.janestreet.com/jobs/main.json"):
        if j["city"] in cities and "Experienced" not in j["availability"]:
            kind = "Intern" if "Intern" in j["availability"] else "New Grad"
            yield (f"{j['position']} ({j['availability'].replace('Full-Time: ', '')})" if kind == "New Grad"
                   else f"{j['position']} ({j['availability']})"), cities[j["city"]], \
                f"https://www.janestreet.com/join-jane-street/position/{j['id']}/"


def amazon(_):
    for country in ("SGP", "HKG", "KOR"):
        for q in ("intern", "graduate"):
            d = get_browser("https://www.amazon.jobs/en/search.json?" + urllib.parse.urlencode(
                {"base_query": q, "country": country, "result_limit": 100}))
            for j in d.get("jobs", []):
                if j.get("country_code") == country:
                    names = {"SGP": "Singapore", "HKG": "Hong Kong", "KOR": "Seoul, Korea"}
                    where = j.get("city") or names[country]
                    yield j["title"], f"{where}, {names[country]}" if where != names[country] else where, \
                        f"https://www.amazon.jobs{j['job_path']}"


def toss(_):
    for j in get_browser("https://api-public.toss.im/api/v3/ipd-eggnog/career/jobs")["success"]:
        yield j["title"], (j.get("location") or {}).get("name") or "Seoul", j["absolute_url"]


def ymd(s):
    digits = re.sub(r"\D", "", str(s or ""))[:8]
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) == 8 else None


def naver(_):
    for first in range(0, 500, 10):
        d = get_browser("https://recruit.navercorp.com/rcrt/loadJobList.do?annoId=&sw=&subJobCdArr=&sysCompanyCdArr="
                        f"&empTypeCdArr=&entTypeCdArr=&workAreaCdArr=&firstIndex={first}")
        for j in d.get("list", []):
            title = j["annoSubject"]
            if j.get("entTypeCdNm") == "신입" and "신입" not in title and "인턴" not in title:
                title += " (신입)"
            yield title, "Seongnam (Pangyo), Korea", j["jobDetailLink"], ymd(j.get("endYmd"))
        if len(d.get("list", [])) < 10:
            break


def kakao(_):
    for page in range(1, 30):
        d = get_browser(f"https://careers.kakao.com/public/api/job-list?part=TECHNOLOGY&company=ALL&page={page}")
        for j in d.get("jobList", []):
            title = j["jobOfferTitle"]
            emp = j.get("employeeTypeName") or ""
            if ("인턴" in emp or "신입" in emp) and emp not in title:
                title += f" ({emp})"
            yield title, j.get("locationName") or "Korea", f"https://careers.kakao.com/jobs/{j['realId']}", ymd(j.get("endDate"))
        if page >= d.get("totalPage", 1):
            break


CUSTOM = {"janestreet": janestreet, "amazon": amazon, "toss": toss, "naver": naver, "kakao": kakao}

ATS = {**CUSTOM, "greenhouse": greenhouse, "lever": lever, "ashby": ashby, "smartrecruiters": smartrecruiters, "workday": workday}


def category(title, company_type):
    t = title.lower()
    if re.search(r"product manag", t):
        return "Product"
    if re.search(r"quant|trad(er|ing)", t):
        return "Quant"
    if re.search(r"machine learning|\bml\b|\bai\b|research scien|deep learning|llm|robotic|computer vision|"
                 r"생성형|모델|멀티모달|번역|음성", t):
        return "AI/ML"
    if company_type == "quant" and re.search(r"research", t):
        return "Quant"
    if re.search(r"hardware|fpga|asic|chip|embedded|firmware|mechanical|electrical|semiconductor|package|equipment|"
                 r"data cent(er|re)|commissioning|control engineer|"
                 r"process engineer|\bfab\b|reliability|installation", t):
        return "Hardware"
    if re.search(r"\bdata\b", t) and not re.search(r"data cent(er|re)", t):
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
    for item in ATS[src["ats"]](src["slug"]):
        title, loc, url = item[:3]
        deadline = item[3] if len(item) > 3 else None
        title = " ".join(title.split())
        countries = [c for c, p in COUNTRY_PATTERNS.items() if p.search(loc)]
        if not countries or not EARLY.search(title) or not TECH.search(title) or EXCLUDE.search(title):
            continue
        locs = [l.strip() for l in re.split(r"[;|]", loc) if l.strip()]
        entry = {
            "company": src["company"],
            "role": title,
            "category": category(title, src.get("type")),
            "locations": locs,
            "countries": countries,
            "season": season(title),
            "url": url,
            "status": "open",
            "source": "auto",
        }
        if deadline:
            entry["deadline"] = deadline
        out.append(entry)
    return out


def main():
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    entries = json.loads(DATA.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()

    found, ok_companies, seen_roles = {}, set(), set()
    with cf.ThreadPoolExecutor(12) as ex:
        futures = {ex.submit(collect, s): s for s in sources}
        for f in cf.as_completed(futures):
            s = futures[f]
            try:
                for e in f.result():
                    # same role posted several times (one per office / req) -> keep one
                    role_key = (e["company"], e["role"].lower(), tuple(e["countries"]))
                    if role_key in seen_roles:
                        continue
                    seen_roles.add(role_key)
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
