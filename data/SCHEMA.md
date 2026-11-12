# Entry schema (`data/internships.json`)

Each entry is one object. `README.md` is generated from this file — never edit the table by hand.

| Field | Required | Values / format |
|---|---|---|
| `company` | ✅ | Company name |
| `role` | ✅ | Role title as posted |
| `category` | ✅ | `SWE` · `Quant` · `AI/ML` · `Data` · `Hardware` · `Product` |
| `locations` | ✅ | List, e.g. `["Hong Kong"]`, `["Singapore", "Remote"]` |
| `country` | ✅ | `HK` · `SG` · `KR` (first location's country, used for grouping) |
| `season` | ✅ | e.g. `Summer 2027`, `Winter 2026`, `Off-cycle` |
| `url` | ✅ | Direct link to the posting (not a generic careers page if avoidable) |
| `deadline` | | `YYYY-MM-DD`, or omit if rolling |
| `visa` | | `yes` (sponsors / no restriction stated) · `no` (citizens/PR only) · omit if unknown |
| `languages` | | Required languages beyond English, e.g. `["Korean"]`, `["Cantonese"]` |
| `oa` | | Assessment type if known, e.g. `HackerRank`, `CodeSignal`, `Game`, `Take-home` |
| `status` | ✅ | `open` · `closed` |
| `added` | ✅ | `YYYY-MM-DD` |
