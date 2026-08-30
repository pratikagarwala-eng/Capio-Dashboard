# Capio International — Account Intelligence Dashboard

A single self-contained page over Capio International's Singapore enterprise
portfolio: **241 account rows**, scored on how close each one looks to a
workplace-hardware decision — devices, AI PCs, deployment and lifecycle services.

One HTML file, no database and no build step. **No data is stored in this repo** —
the page reads the Google Sheet on load, derives the whole board in the browser,
and re-reads every 60 seconds. What is committed here is the rules, not the rows.

## Files

| File | What it is |
|---|---|
| `index.html` | the whole dashboard — markup, styles, charts and the derivation, no data |
| `build_data.py` | the reference derivation — run it to check the browser port still agrees |
| `api/sheet.js` | Vercel edge proxy that keeps the spreadsheet id server-side |
| `serve.py` | local static server |
| `vercel.json` | security headers and cache policy |
| `.vercelignore` | keeps the build tooling — and the spreadsheet id it contains — out of the deployment |
| `robots.txt` | keeps the deployment out of search indexes |
| `capio-mark.png`, `capio-logo.png` | brand mark taken from capiointl.com |

## Where the data lives

Nowhere in this repo. `index.html` is ~110 KB of markup, styles and logic with an
empty `SNAPSHOT`; every figure on the page comes from the sheet at run time. The
cost is a boot panel for the second or two it takes to pull the tab — the benefit
is that no part of Capio's target list is committed to git, and the page can never
show a stale figure it inherited from whenever someone last ran a build.

`build_data.py --embed` can bake a snapshot in for a private deployment that must
paint before its first network round trip. Clear it again with `--clear` before
pushing. It is not the default, for the reason in **Before you make this public**.

## Running it

Locally:

```bash
python3 serve.py 8078
```

Then open the URL it prints. The `?sheet=` parameter makes the page read Google
directly, which is what you want without the serverless proxy in front.

Checking the derivation:

```bash
python3 build_data.py
```

That reads the sheet, applies the same rules the browser applies, and prints the
tier spread, coverage and signal prevalence — without touching `index.html`.
Compare it against what the page shows; they agree exactly.

| Flag | Effect |
|---|---|
| *(none)* | derive and report, write nothing |
| `--embed` | also bake the result into `index.html` (publishes the account list) |
| `--clear` | strip any baked-in snapshot back out |

## How the 60-second refresh works

On load the page shows a boot panel and reads the sheet. From then on it re-reads
every 60 seconds, re-derives everything in the browser, and repaints only if the
result actually differs from what is on screen. The pill in the filter rail
reports which of those happened:

| Pill | Meaning |
|---|---|
| **Syncing** | a read is in flight |
| **Live** | the last read succeeded; hover for `No change` or the re-read time |
| **Update ready** | a filter panel is open, so the repaint is held until it closes |
| **Stale** | the last read failed; the figures on screen are the last good ones |

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
3. Deploy. Confirm `https://<project>.vercel.app/api/sheet?tab=accounts` returns
   CSV and the live pill on the page reads **Live**.

There is no required environment variable. `api/sheet.js` reads the workbook named
by `DEFAULT_SHEET_ID` in that file, so a fresh import deploys and works. Setting
`SHEET_ID` in the project's environment variables overrides it, which is how you
point a deployment at a different workbook.

The sheet must stay link-viewable for the proxy to read it. If sharing is switched
off, `api/sheet.js` returns a 502 with a plain explanation rather than passing
Google's sign-in page through as if it were data, and the page shows the boot
panel with the reason.

`.vercelignore` keeps `build_data.py`, `serve.py` and this README out of the
deployment. All three carry the spreadsheet id in plain text, and a static host
serves whatever sits in the project root — leaving them in would defeat the point
of the proxy.

## Before you make this public

The page renders Capio's live target list: **241 named companies** with revenue,
headcount, IT headcount, buying signals and the third-party topics each one is
researching. That is commercially sensitive — it is the shape of Capio's pipeline.

- **Keep the Vercel deployment behind Deployment Protection.** `robots.txt` and
  the `x-robots-tag` header keep it out of search engines, but neither is access
  control — anyone with the URL can read everything.
- **Do not commit a snapshot.** `--embed` writes all 241 accounts into
  `index.html`, and git does not forget. Once that reaches a public remote it is
  permanently and searchably public: rewriting history does not reliably remove it
  from forks, caches or the GitHub API.
- **The sheet's own sharing is the real perimeter.** `api/sheet.js` reads it with
  no credentials, which only works because the sheet is link-viewable. The
  spreadsheet id is in this repo in plain text — in `build_data.py`, in
  `api/sheet.js` and in this file — so anyone who can read the repo can read the
  sheet. **Keep the repo private**, or restrict the sheet's sharing.

## How the two transforms stay in agreement

`build_data.py` is the canonical statement of the rules; the `buildData()` function
inside `index.html` is a direct port of it and is what actually feeds the page.
Run the Python and compare its report against the dashboard — they agree exactly,
row for row and label for label.

If you change a rule, change it in both. Two subtleties already handled:

- Python rounds halves to even and JavaScript rounds them toward +infinity, so
  `growth_pct()` uses `floor(x + 0.5)` on both sides.
- Sixteen of the sheet's own column headers carry a **trailing space**
  (`Copilot Deployment Status `, `Singapore Office Activity `, and fourteen more).
  Both loaders trim the header row before looking anything up.

## What the priority tiers mean

Capio sells enterprise hardware — business laptops, workstations, servers and
peripherals — plus deployment, maintenance and lifecycle services, and through LGA
International the networking, cloud, security and managed-IT wrap around them.

Each account is scored on four independent tests:

| Test | True when |
|---|---|
| **Device intent** | a third-party intent topic names a device, an OS or a desktop delivery model |
| **Fleet demand** | hiring in Singapore, a workforce or office change, or an IT team of 50+ |
| **AI programme** | any AI or Copilot activity live in Singapore |
| **Modernisation** | automation, transformation, cloud, network, security or resilience work |

and tiered on how many hold together:

| Tier | Rule |
|---|---|
| **P0** | all four — they are pricing devices, they have a fleet and a reason to move it, and there is a programme paying for it |
| **P1** | device intent and fleet demand alongside a programme, or a full programme with a workplace rollout already announced |
| **P2** | device intent, or a programme paired with fleet demand or a workplace rollout |
| **P3** | at least one signal, but nothing yet that points at a purchase |
| **Unranked** | no signal detected |

Spread as at 2026-08-31: **P0 42 · P1 42 · P2 74 · P3 66 · Unranked 17**. It drifts
as the sheet is enriched, and the dashboard always shows the current split.

The check that this is ranking rather than reshuffling is printed on the
Prioritization card itself: mean signal count per tier, which currently runs
**11.2 → 5.7 → 4.1 → 1.8 → 0.0**. If a future sheet breaks that ordering the card
says so in place of claiming it holds.

### Why device intent carries the most weight

Most enrichment signals say a company is *busy*. Third-party intent on **Laptop**,
**Workstations**, **Windows 10**, **Windows 11**, **AI PC**, **DaaS**, or a named
ThinkPad / ThinkCentre / ThinkBook / ThinkStation / EliteBook / MacBook SKU says
somebody is costing out a fleet right now. It is the only signal in this sheet
that names Capio's own line card. 109 of 241 accounts carry one.

`Dell Technologies` and `Hewlett Packard Enterprise (HPE)` are deliberately *not*
in that set even though both are common topics here. They are vendor-brand
interest that could equally be servers, storage or services; `HP EliteBook` is
unambiguously a laptop. The line is drawn at topics that name an endpoint.

Windows 10 left support in October 2025, so the Windows and AI PC topics carry a
date the customer does not control. Those 73 accounts are flagged separately.

## What is in this sheet

**25 enrichment signals**, grouped on the page into the four families Capio sells
to — AI & Copilot Readiness (6), Workplace & Office (5), IT Modernisation (8),
Growth & Funding (6). The dashboard reports each family's *reach* (accounts
carrying at least one of its signals) as well as each individual signal.

Three things worth knowing about the source:

- **This is an enterprise portfolio, not an SMB one.** Headcount runs from 2 to
  150,832, median 519, 75th percentile 5,328; median revenue is $322M. The
  headcount and IT-headcount bands step by order of magnitude rather than evenly,
  because even bands would put nine accounts in ten in the first bucket.
- **`AI Adoption In Singapore Sentiment` carries no information.** It is `Direct`
  for exactly the 82 rows that have an `AI Adoption In Singapore` narrative and
  blank for the other 159 — it restates the presence of that column and nothing
  more, so the dashboard does not draw a card on it.
- **241 rows are 236 companies.** Five domains appear twice, each the same company
  entered under two legal names with identical headcount — `ktcgroup.com.sg`,
  `okp.listedcompany.com`, `peceng.com`, `rotaryeng.com.sg`, `wohhup.com`. The
  masthead reports accounts and companies as two separate figures rather than
  quietly counting five companies twice, and the coverage card says so in words.
  Every other figure on the page counts rows. `python3 build_data.py` prints the
  five pairs by name, which is where to go when the source list gets deduplicated.

One row — `CATLIN SINGAPORE PTE. LTD.` — has no domain at all. It still counts as
its own company, and its name is not linked in the tables because there is nothing
to link it to.
