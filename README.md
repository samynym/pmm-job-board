# Product Marketing Job Board

A self-contained HTML job board of Product Marketing roles, sourced by Google-dorking
15 different ATS (applicant tracking system) platforms rather than relying on a
hardcoded company list.

**Live board: <https://samynym.github.io/pmm-job-board/>** — refreshed automatically
every day at 5:00 SAST. You can also open `index.html` (or its alias
`product-marketing-jobs.html`) directly in any browser — no server, no build step.
It has a live search box (filters every column) and clickable column headers to
sort (defaults to newest-posted-first).

## Daily automation

`.github/workflows/refresh.yml` runs `refresh.py` every day at 03:00 UTC (05:00 SAST):
it enumerates every company board already in `unique_urls.txt` through each ATS's
public list API (no Google involved), re-verifies known postings, drops delisted
roles, rebuilds the HTML, commits the result, and emails the roles first seen in the
last 24 hours (via Resend; recipients live in the `NOTIFY_EMAILS` repo variable).
New-role discovery covers every platform except iCIMS, which has no public list
endpoint — new iCIMS roles still require a manual dork pass into `raw/`.
State lives in `jobs_seen.json` (first-seen date per posting).

## Applied tags (private)

Opening the board with a private `#k=<secret>&me=<name>` link reveals an
"Applied" toggle per role, shared between holders of the link (state in a
Supabase table reachable only through two secret-checked RPCs — see
`docs/superpowers/specs/2026-07-15-applied-tags-design.md`). The plain public
URL shows no tag UI. The layout is responsive: stacked cards on mobile.

## Platforms covered

Ashby, Lever, SmartRecruiters, Jobvite, Greenhouse, Breezy, Workable, Recruitee,
Teamtailor, Workday, iCIMS, BambooHR, JazzHR, Rippling, Personio.

## How it works

1. **`config.py`** — editable list of ATS domains + search keywords ("product marketing",
   "product marketer"). Add more of either here.
2. **Search phase (manual/browser-driven)** — for each (domain, keyword) pair, run the
   Google dork `site:<domain> "<keyword>"` through a real browser (Google blocks
   automated/headless requests) and page through results, saving job URLs to
   `raw/<tag>.txt`. This step isn't a single script because it needs a real browser
   session and occasionally a CAPTCHA solved by hand.
3. **`dedupe.py`** — reads everything in `raw/`, canonicalizes URLs per-ATS, and writes
   `unique_urls.txt`.
4. **`scrape.py`** — for every unique URL, pulls structured data (title, company,
   location, remote/hybrid/on-site, posted date, salary, apply link) directly from each
   ATS's own API or embedded schema.org JSON-LD — no scraping of rendered HTML text.
   Also correctly detects delisted/expired postings and drops them. Writes
   `scraped_jobs.json` + `scrape_errors.json`.
5. **`finalize.py`** — filters to genuinely product-marketing titled roles, dedupes once
   more, sorts newest-first, writes `final_jobs_sorted.json`.
6. **`build_html.py`** — renders `product-marketing-jobs.html` from
   `final_jobs_sorted.json`.

## Re-running / extending

To add more roles later:
1. Edit `config.py` with new ATS domains or keywords.
2. Re-run the search phase (step 2 above) for the new combos, saving to `raw/`.
3. Run `python3 dedupe.py && python3 scrape.py && python3 finalize.py && python3 build_html.py`.

## Data notes

- Posted dates come from each ATS's own system (API timestamp or the JSON-LD it
  publishes for Google Jobs) — never guessed. Where no date is available (e.g.
  Rippling's public board API), the row shows "date unknown" and sorts to the bottom.
- Remote/Hybrid/On-site is read from structured ATS fields where available, and
  inferred from location/description text as a fallback.
