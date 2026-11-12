#!/usr/bin/env python3
"""Validate data/internships.json and regenerate the tables in README.md."""
import datetime as dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "internships.json"
README = ROOT / "README.md"
START, END = "<!-- TABLE:START -->", "<!-- TABLE:END -->"

REQUIRED = ["company", "role", "category", "locations", "countries", "season", "url", "status", "added"]
CATEGORIES = {"SWE", "Quant", "AI/ML", "Data", "Hardware", "Product"}
COUNTRIES = {"HK": "🇭🇰 Hong Kong", "SG": "🇸🇬 Singapore", "KR": "🇰🇷 South Korea"}
STATUSES = {"open", "closed"}
VISA = {"yes": "✅", "no": "❌"}


def validate(entries):
    errors = []
    seen = set()
    for i, e in enumerate(entries):
        where = f"entry {i} ({e.get('company', '?')} / {e.get('role', '?')})"
        for f in REQUIRED:
            if not e.get(f):
                errors.append(f"{where}: missing '{f}'")
        if e.get("category") and e["category"] not in CATEGORIES:
            errors.append(f"{where}: bad category '{e['category']}'")
        bad = [c for c in e.get("countries", []) if c not in COUNTRIES]
        if bad or not isinstance(e.get("countries", []), list):
            errors.append(f"{where}: bad countries {e.get('countries')}")
        if e.get("status") and e["status"] not in STATUSES:
            errors.append(f"{where}: bad status '{e['status']}'")
        if e.get("visa") and e["visa"] not in VISA:
            errors.append(f"{where}: bad visa '{e['visa']}'")
        if not str(e.get("url", "")).startswith("https://"):
            errors.append(f"{where}: url must start with https://")
        for f in ("deadline", "added"):
            if e.get(f):
                try:
                    dt.date.fromisoformat(e[f])
                except ValueError:
                    errors.append(f"{where}: '{f}' must be YYYY-MM-DD")
        key = (e.get("url"),)
        if key in seen:
            errors.append(f"{where}: duplicate url")
        seen.add(key)
    return errors


def cell(s):
    return str(s).replace("|", "\\|")


def row(e, today):
    deadline = e.get("deadline") or "—"
    if e.get("deadline") and e["status"] == "open":
        days = (dt.date.fromisoformat(e["deadline"]) - today).days
        if 0 <= days <= 7:
            deadline += " 🔥"
    new = " 🆕" if (today - dt.date.fromisoformat(e["added"])).days <= 7 else ""
    link = f"[Apply]({e['url']})" if e["status"] == "open" else "🔒 Closed"
    return "| " + " | ".join([
        f"**{cell(e['company'])}**{new}",
        cell(e["role"]),
        e["category"],
        cell(", ".join(e["locations"])),
        cell(e["season"]),
        deadline,
        VISA.get(e.get("visa"), "❔"),
        cell(", ".join(e.get("languages", [])) or "—"),
        link,
    ]) + " |"


HEADER = ("| Company | Role | Track | Location | Season | Deadline | Visa | Extra language | Link |\n"
          "|---|---|---|---|---|---|---|---|---|")


def render(entries, today):
    def sort_key(e):
        return (e.get("deadline") or "9999-12-31", e["company"].lower())

    out = []
    open_count = sum(e["status"] == "open" for e in entries)
    out.append(f"**{open_count} open** · {len(entries)} total · last updated {today.isoformat()}\n")
    for code, name in COUNTRIES.items():
        rows = [e for e in entries if code in e["countries"] and e["status"] == "open"]
        out.append(f"### {name} ({len(rows)})\n")
        if rows:
            out.append(HEADER)
            out.extend(row(e, today) for e in sorted(rows, key=sort_key))
        else:
            out.append("_No open postings yet — [add one](../../issues/new?template=new-posting.yml)!_")
        out.append("")
    closed = [e for e in entries if e["status"] == "closed"]
    if closed:
        out.append(f"<details><summary>🔒 Closed postings ({len(closed)})</summary>\n")
        out.append(HEADER)
        out.extend(row(e, today) for e in sorted(closed, key=sort_key))
        out.append("\n</details>\n")
    return "\n".join(out)


def main():
    entries = json.loads(DATA.read_text(encoding="utf-8"))
    errors = validate(entries)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    today = dt.date.today()
    # Auto-close postings whose deadline has passed.
    for e in entries:
        if e["status"] == "open" and e.get("deadline") and dt.date.fromisoformat(e["deadline"]) < today:
            e["status"] = "closed"
    DATA.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text = README.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{START}\n{render(entries, today)}\n{END}{tail}", encoding="utf-8")
    print(f"OK: {len(entries)} entries")


if __name__ == "__main__":
    main()
