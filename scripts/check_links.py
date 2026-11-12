#!/usr/bin/env python3
"""Report open postings whose URL no longer resolves. Exits 1 if any are dead."""
import json
import pathlib
import sys
import urllib.error
import urllib.request

DATA = pathlib.Path(__file__).resolve().parent.parent / "data" / "internships.json"
UA = "Mozilla/5.0 (compatible; asia-tech-internships-linkcheck)"


def alive(url):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status < 400
        except urllib.error.HTTPError as err:
            if err.code in (403, 405, 429):  # bot-blocked or HEAD unsupported: try GET / give benefit of doubt
                if method == "GET":
                    return True
                continue
            if method == "GET":
                return False
        except Exception:
            if method == "GET":
                return False
    return False


def main():
    entries = [e for e in json.loads(DATA.read_text(encoding="utf-8")) if e["status"] == "open"]
    dead = [e for e in entries if not alive(e["url"])]
    for e in dead:
        print(f"- [ ] **{e['company']}** — {e['role']}: {e['url']}")
    print(f"\nChecked {len(entries)} open postings, {len(dead)} dead.", file=sys.stderr)
    sys.exit(1 if dead else 0)


if __name__ == "__main__":
    main()
