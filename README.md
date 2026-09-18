# Capio International — Account Intelligence Dashboard

A single self-contained page over Capio International's two Singapore account
sets, each on its own tab:

| Board | Sheet | Rows | What it is |
|---|---|---|---|
| **Existing** | `1MJHjM6u…` | ~237 | the enterprise portfolio — median 519 staff, third-party intent on roughly half |
| **Net new** | `1NNFcCsa…` | ~499 | net-new Singapore prospects — median 51 staff, intent on one account |

Both are scored on how close each account looks to a workplace-hardware decision,
but **not on the same tests** — see *What the priority tiers mean* below, which is
the most important thing to understand about this dashboard.

One HTML file, no database and no build step. **No data is stored in this repo** —
the page reads both sheets on load, derives each board in the browser, and
re-reads every 60 seconds. What is committed here is the rules, not the rows.

## Files

| File | What it is |
|---|---|
| `index.html` | the whole dashboard — markup, styles, charts and the derivation, no data |
| `build_data.py` | the reference derivation — run it to check the browser port still agrees |
| `api/sheet.js` | Vercel edge proxy that keeps both spreadsheet ids server-side |
| `serve.py` | local static server |
| `vercel.json` | security headers and cache policy |
| `.vercelignore` | keeps the build tooling — and the spreadsheet id it contains — out of the deployment |
| `robots.txt` | keeps the deployment out of search indexes |
| `capio-mark.png`, `capio-logo.png` | brand mark taken from capiointl.com |

## Where the data lives

Nowhere in this repo. `index.html` is ~130 KB of markup, styles and logic with an
empty `SNAPSHOT`; every figure on the page comes from the sheets at run time. The
cost is a boot panel for the second or two it takes to pull them — the benefit is
that no part of Capio's target lists is committed to git, and the page can never
show a stale figure it inherited from whenever someone last ran a build.

Each board is fetched and applied independently, so one sheet being unreachable
leaves the other board working rather than blanking the page.

`build_data.py --embed` can bake a snapshot in for a private deployment that must
paint before its first network round trip. Clear it again with `--clear` before
pushing. It is not the default, for the reason in **Before you make this public**.

## Running it

Locally:

```bash
python3 serve.py 8078
```

Then open the URL it prints. The `?existing=` and `?netnew=` parameters make the
page read Google directly, which is what you want without the serverless proxy in
front. (`?sheet=` is still accepted as an alias for `?existing=`.)

Checking the derivation:

```bash
python3 build_data.py
```

That reads both sheets, applies the same rules the browser applies, and prints the
tier spread, test pass-rates, coverage and signal prevalence for each board —
without touching `index.html`. Compare it against what the page shows; they agree
exactly, row for row and label for label.

It also asserts the one property that makes a ranking a ranking: mean signal count
has to fall with every tier. The report prints `ordering holds` or
`*** ORDERING BROKEN ***` rather than leaving you to eyeball it.

| Flag | Effect |
|---|---|
| *(none)* | derive and report both boards, write nothing |
| `--board existing` / `--board netnew` | just one of them |
| `--embed` | also bake both boards into `index.html` (publishes the account lists) |
| `--clear` | strip any baked-in snapshot back out |

## How the 60-second refresh works

On load the page shows a boot panel and reads both sheets. From then on it
re-reads every 60 seconds, re-derives each board in the browser, and repaints only
if the result actually differs from what is on screen. A board that is not on
screen is updated in the background without disturbing the one that is. The pill
in the filter rail reports which of those happened:

| Pill | Meaning |
|---|---|
| **Syncing** | a read is in flight |
| **Live** | the last read succeeded; hover for `No change` or the re-read time |
| **Update ready** | a filter panel is open, so the repaint is held until it closes |
| **Stale** | a read failed; the figures on screen are the last good ones, and the pill names which board |

Click the pill to force a read. `?refresh=<seconds>` overrides the interval
(clamped to 15–3600). Reads pause while the tab is hidden and resume on focus, so
a dashboard left open in a background tab costs nothing.

If the very first read fails there is no earlier reading to fall back on, so the
boot panel says so plainly rather than showing a grid of zeros — and it quotes the
reason the proxy gave, so the failure names what to go and fix.

## Deploying to Vercel

The repo is a static site plus one edge function; there is no build step.

1. **Import the repo** at vercel.com → New Project. Leave the framework preset as
   *Other*, build command empty, output directory empty.
2. **Turn on Deployment Protection** (Settings → Deployment Protection). See the
   warning below — without it the URL is world-readable.
3. Deploy. Confirm `https://<project>.vercel.app/api/sheet?tab=existing` and
   `?tab=netnew` both return CSV, and the live pill on the page reads **Live**.

There are no required environment variables. `api/sheet.js` carries both workbook
ids in its `SOURCES` map, so a fresh import deploys and works. `SHEET_ID_EXISTING`
and `SHEET_ID_NETNEW` override them, which is how you point a deployment at
different workbooks.

Both sheets must stay link-viewable for the proxy to read them. If sharing is
switched off, `api/sheet.js` returns a 502 with a plain explanation rather than
passing Google's sign-in page through as if it were data, and the pill names which
board failed.

`.vercelignore` keeps `build_data.py`, `serve.py` and this README out of the
deployment. All three carry the spreadsheet id in plain text, and a static host
serves whatever sits in the project root — leaving them in would defeat the point
of the proxy.

## Before you make this public

The page renders Capio's live target lists: **roughly 740 named companies** across
the two boards, with revenue, headcount, IT headcount, buying signals and the
third-party topics each one is researching. That is commercially sensitive — it is
the shape of Capio's pipeline, including who they have not approached yet.

- **Keep the Vercel deployment behind Deployment Protection.** `robots.txt` and
  the `x-robots-tag` header keep it out of search engines, but neither is access
  control — anyone with the URL can read everything.
- **Do not commit a snapshot.** `--embed` writes every account of both boards into
  `index.html`, and git does not forget. Once that reaches a public remote it is
  permanently and searchably public: rewriting history does not reliably remove it
  from forks, caches or the GitHub API.
- **The sheets' own sharing is the real perimeter.** `api/sheet.js` reads them with
  no credentials, which only works because they are link-viewable. Both spreadsheet
  ids are in this repo in plain text — in `build_data.py`, in `api/sheet.js` and in
  this file — so anyone who can read the repo can read both sheets. **Keep the repo
  private**, or restrict the sheets' sharing.

## How the two transforms stay in agreement

`build_data.py` is the canonical statement of the rules; the `buildData()` function
inside `index.html` is a direct port of it and is what actually feeds the page.
Run the Python and compare its report against the dashboard — they agree exactly,
row for row and label for label.

If you change a rule, change it in both. Two subtleties already handled:

- Python rounds halves to even and JavaScript rounds them toward +infinity, so
  `growth_pct()` uses `floor(x + 0.5)` on both sides.
- Some column headers carry a **trailing space** (`Copilot Deployment Status `
  among them). Both loaders trim the header row before looking anything up.

## What the priority tiers mean

Capio sells enterprise hardware — business laptops, workstations, servers and
peripherals — plus deployment, maintenance and lifecycle services, and through LGA
International the networking, cloud, security and managed-IT wrap around them.

Both boards score each account on **five independent tests** and tier it on which
combination holds, evaluated top down so every account lands in exactly one tier:

| Tier | Rule |
|---|---|
| **P0** | tests 1–4, all at once |
| **P1** | tests 1 and 2 plus at least one of 3, 4 or 5 — or test 2 with 3, 4 and 5 together |
| **P2** | test 1 alongside any one other — or test 2 or 5 alongside test 3 or 4 |
| **P3** | at least one enrichment signal of any kind, or test 1 on its own |
| **Unranked** | no signal detected |

**The two boards do not use the same five tests, and this is deliberate.**

### Existing — the enterprise portfolio

| # | Test | True when |
|---|---|---|
| 1 | **Device intent** | a third-party intent topic names a laptop, workstation, Windows release, AI PC or desktop service |
| 2 | **Fleet demand** | hiring in Singapore, a workforce or office change, or an IT team of 50 or more |
| 3 | **AI programme** | any AI or Copilot activity live in Singapore |
| 4 | **Modernisation** | automation, transformation, cloud, network, security or resilience work |
| 5 | **Rollout announced** | a workplace-technology programme, or technology already deployed |

Spread as at 2026-09-18: **P0 38 · P1 42 · P2 74 · P3 66 · Unranked 17**.

### Net new — Singapore prospects

| # | Test | True when |
|---|---|---|
| 1 | **Workplace moment** | a new or expanded Singapore office, a hybrid-work policy, or technology recently deployed |
| 2 | **Growing** | a Singapore hiring trend, an open role anywhere, or headcount up 5%+ over twelve months |
| 3 | **AI programme** | *(same definition as the existing board)* |
| 4 | **Modernisation** | *(same definition as the existing board)* |
| 5 | **Fleet worth serving** | fifty staff or more |

Spread as at 2026-09-18: **P0 70 · P1 67 · P2 131 · P3 150 · Unranked 81**.

### Why net new cannot use the existing board's tests

The net-new sheet carries third-party intent on **1 of 499 accounts** and IT
headcount on 45. Device intent is the heaviest-weighted test on the existing
board, and running that model over net-new data puts **one account in P0** and
calls the ranking done — a tier holding 0.2% of a list ranks nothing.

So net new is scored on what its data actually carries. Tests 3 and 4 are defined
identically on both boards, which is what makes any cross-board comparison
meaningful; tests 1, 2 and 5 are not, and figures that depend on them are not
comparable between tabs. The dashboard never puts the two side by side for that
reason — the tab switch replaces the board rather than adding a column to it.

Both boards print the one check that a ranking is ordering something real: mean
signal count per tier, which must fall at every step. Existing currently runs
**11.8 → 5.9 → 4.3 → 2.0 → 0.0** and net new **9.0 → 5.3 → 4.8 → 2.2 → 0.0**.
`build_data.py` asserts it; the Prioritization card says so in place of claiming
it holds if a future sheet breaks it.

All of this is on the page itself, in the **How Accounts Are Ranked** card — the
five tests with live pass rates and the five tier rules, recomputed against
whatever the filters currently select. The tests and the tiering live in one place
per implementation (`BOARDS[].tests` + `tier_with()` in `build_data.py`,
`BOARDS[].tests` + `tierWith()` in `index.html`) and the card renders the same
descriptions the scoring uses, so the page cannot describe a rule it does not
apply.

### Why device intent carries the most weight on the existing board

Most enrichment signals say a company is *busy*. Third-party intent on **Laptop**,
**Workstations**, **Windows 10**, **Windows 11**, **AI PC**, **DaaS**, or a named
ThinkPad, EliteBook or MacBook SKU says somebody is costing out a fleet right now.
It is the only signal in either sheet that names Capio's own line card.

`Dell Technologies` and `Hewlett Packard Enterprise (HPE)` are deliberately *not*
in that set even though both are common topics. They are vendor-brand interest
that could equally be servers, storage or services; `HP EliteBook` is unambiguously
a laptop. The line is drawn at topics that name an endpoint.

Windows 10 left support in October 2025, so the Windows and AI PC topics carry a
date the customer does not control. Those accounts are flagged separately.

## What is in these sheets

**26 enrichment signals**, shared by both workbooks and grouped on the page into
the four families Capio sells to — AI & Copilot Readiness (6), Workplace & Office
(6), IT Modernisation (8), Growth & Funding (6). The dashboard reports each
family's *reach* (accounts carrying at least one of its signals) as well as each
individual signal. Several signals are populated in one sheet and empty in the
other; they are still drawn, at zero, because an absent signal is a fact about
that portfolio rather than a reason to hide the row.

The two workbooks differ in three columns: the existing sheet has `Linkedin URL`
and `AI Adoption In Singapore Sentiment`, the net-new one has
`Company Linkedin URL`. Both loaders resolve the LinkedIn and company-name columns
by trying each name they have gone by, because the existing sheet's first column
has already been renamed once (from `Existing Accounts - If any — …` to
`Company Name`) mid-project.

Things worth knowing about the sources:

- **They are two different populations.** Existing runs 2 to 150,832 staff, median
  519, median revenue $322M. Net new runs to 497 staff, median 51, median revenue
  $15.3M, and is 84% Singapore-headquartered against 57% for existing. Each board
  bands headcount and revenue on its own scale — shared bands would put nine
  net-new accounts in ten into a single bucket.
- **`AI Adoption In Singapore Sentiment` carries no information.** In the existing
  sheet it is `Direct` for exactly the rows that have an `AI Adoption In Singapore`
  narrative and blank for the rest — it restates the presence of that column and
  nothing more, so no card is drawn on it. It is absent from the net-new sheet.
- **Rows are not companies.** A handful of domains appear twice in each sheet, the
  same company entered under two legal names. The coverage card says so and
  `build_data.py` prints the pairs by name; every figure on the page counts rows.
