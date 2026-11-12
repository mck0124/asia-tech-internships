# Contributing

Thanks for helping fellow students! 🙌

## Easiest: open an issue
Use the **➕ New posting** issue form. A maintainer will add it within a day or two.

## Or: open a PR
1. Add an object to `data/internships.json` (see [`data/SCHEMA.md`](data/SCHEMA.md)).
2. Run `python3 scripts/build.py` — it validates your entry and regenerates the README.
3. Commit both files and open a PR.

## Add a company to the daily auto-fetch
If a company posts on **Greenhouse, Lever or Ashby**, add it to [`data/sources.json`](data/sources.json):
```json
{"company": "IMC Trading", "ats": "greenhouse", "slug": "imc", "type": "quant"}
```
The slug is the part after `boards.greenhouse.io/`, `jobs.lever.co/` or `jobs.ashbyhq.com/`. `type` is `quant` or `tech`.
Run `python3 scripts/fetch.py && python3 scripts/build.py` to test.

## What belongs here
- ✅ Tech internships or new-grad roles (SWE, Quant, AI/ML, Data, Hardware, Product) located in **Hong Kong, Singapore or South Korea**
- ✅ A direct link to the actual posting
- ❌ Unpaid roles, referral-spam, recruiter-agency reposts, generic "join our talent pool" pages

Spotted a closed or dead posting? Open an issue or PR setting `"status": "closed"`.
