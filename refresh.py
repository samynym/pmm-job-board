"""Daily refresh without the manual Google-dork phase.

Enumerates every company board already present in unique_urls.txt through each
ATS's public list API (or public listing page where there is no API), collects
candidate product-marketing job URLs, re-verifies previously known postings,
and rebuilds final_jobs_sorted.json via the existing scrape.py processors.

Board enumeration now also captures (title, location, remote) for EVERY job on
each board — not just product-marketing ones — and aggregates them into
company_signals.json (via company_signals.py). Those signals feed the
company-level remote-hiring verdicts. Same API calls, no extra fetches.

Tracks when each posting was first seen in jobs_seen.json so a run can report
which roles are new since the previous run (new_jobs_latest.json, consumed by
notify.py). iCIMS has no usable public list endpoint, so those boards only get
their known URLs re-verified — new iCIMS roles still need a manual dork pass.
"""

import json, os, re, sys, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import quote, urlparse

import scrape
import company_signals
from config import KEYWORDS
from dedupe import canonicalize
from finalize import finalize, relevant

BASE = os.path.dirname(os.path.abspath(__file__))
UA = scrape.UA

MAX_WORKERS = 8
MAX_WORKDAY_RESULTS_PER_QUERY = 200
MAX_TEAMTAILOR_PAGES = 10


def http(url, data=None, headers=None, timeout=20):
    h = {"User-Agent": UA, "Accept": "application/json, text/html, application/xml"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def get_json(url):
    return json.loads(http(url))


# ---------------------------------------------------------------------------
# Board discovery: which companies do we already know, per ATS?
# ---------------------------------------------------------------------------

def boards_from_urls(urls):
    boards = {}  # ats -> set of board keys

    def add(ats, key):
        boards.setdefault(ats, set()).add(key)

    for u in urls:
        p = urlparse(u)
        host = p.netloc.lower()
        parts = [s for s in p.path.split('/') if s]
        if 'ashbyhq.com' in host:
            add('ashby', parts[0])
        elif 'lever.co' in host:
            add('lever', parts[0])
        elif 'greenhouse.io' in host:
            add('greenhouse', parts[0])
        elif 'smartrecruiters.com' in host:
            add('smartrecruiters', parts[0])
        elif 'apply.workable.com' in host:
            add('workable', parts[0])
        elif 'recruitee.com' in host:
            add('recruitee', host.split('.')[0])
        elif 'breezy.hr' in host:
            add('breezy', host.split('.')[0])
        elif 'ats.rippling.com' in host:
            add('rippling', parts[0])
        elif 'myworkdayjobs.com' in host and 'job' in parts:
            # canonical form is https://{host}/{site}/job/{req}
            add('workday', (host, parts[parts.index('job') - 1]))
        elif 'jobs.personio.de' in host:
            add('personio', host)
        elif 'teamtailor.com' in host:
            add('teamtailor', host)
        elif 'applytojob.com' in host:
            add('jazzhr', host)
        elif 'jobvite.com' in host:
            add('jobvite', parts[0])
    return boards


# ---------------------------------------------------------------------------
# Per-ATS board listers. Each returns a list of job dicts:
#   {url, title, location, remote}
# title/location may be None when the listing doesn't expose them.
# ---------------------------------------------------------------------------

def _loc_remote(loc, flag=None):
    loc = (loc or '').strip() or None
    if flag is not None:
        return loc, bool(flag)
    return loc, bool(loc and 'remote' in loc.lower())

def list_ashby(slug):
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{quote(slug, safe='')}")
    out = []
    for j in d.get('jobs', []):
        if not j.get('isListed', True):
            continue
        loc, rem = _loc_remote(j.get('location'), j.get('isRemote'))
        out.append({'url': f"https://jobs.ashbyhq.com/{slug}/{j['id']}",
                    'title': j.get('title'), 'location': loc, 'remote': rem})
    return out

def list_lever(company):
    d = get_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
    out = []
    for j in d:
        cats = j.get('categories') or {}
        loc, rem = _loc_remote(cats.get('location'),
                               (j.get('workplaceType') or '').lower() == 'remote' or None)
        out.append({'url': f"https://jobs.lever.co/{company}/{j['id']}",
                    'title': j.get('text'), 'location': loc, 'remote': rem})
    return out

def list_greenhouse(company):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs")
    out = []
    for j in d.get('jobs', []):
        loc, rem = _loc_remote((j.get('location') or {}).get('name'))
        out.append({'url': f"https://boards.greenhouse.io/{company}/jobs/{j['id']}",
                    'title': j.get('title'), 'location': loc, 'remote': rem})
    return out

def list_smartrecruiters(company):
    out, offset = [], 0
    while True:
        d = get_json(f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset={offset}")
        content = d.get('content', [])
        for p in content:
            locd = p.get('location') or {}
            loc_str = ', '.join(x for x in [locd.get('city'), locd.get('country')] if x)
            loc, rem = _loc_remote(loc_str, locd.get('remote'))
            out.append({'url': f"https://jobs.smartrecruiters.com/{company}/{p['id']}",
                        'title': p.get('name'), 'location': loc, 'remote': rem})
        offset += len(content)
        if not content or offset >= d.get('totalFound', 0):
            return out

def list_workable(account):
    d = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=false")
    out = []
    for j in d.get('jobs', []):
        loc_str = ', '.join(x for x in [j.get('city'), j.get('country')] if x)
        out.append({'url': f"https://apply.workable.com/{account}/j/{j['shortcode'].upper()}",
                    'title': j.get('title'), 'location': loc_str or None,
                    'remote': bool(j.get('telecommuting'))})
    return out

def list_recruitee(company):
    d = get_json(f"https://{company}.recruitee.com/api/offers/")
    out = []
    for o in d.get('offers', []):
        loc, rem = _loc_remote(o.get('location'), o.get('remote'))
        out.append({'url': f"https://{company}.recruitee.com/o/{o['slug']}",
                    'title': o.get('title'), 'location': loc, 'remote': rem})
    return out

def list_breezy(company):
    d = get_json(f"https://{company}.breezy.hr/json")
    out = []
    for o in d:
        if not o.get('friendly_id'):
            continue
        locd = o.get('location') or {}
        loc_str = locd.get('name') if isinstance(locd, dict) else str(locd or '')
        out.append({'url': f"https://{company}.breezy.hr/p/{o['friendly_id']}",
                    'title': o.get('name'), 'location': loc_str or None,
                    'remote': bool((locd.get('is_remote') if isinstance(locd, dict) else None)
                                   or (loc_str and 'remote' in loc_str.lower()))})
    return out

def list_rippling(board):
    d = get_json(f"https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs")
    out = []
    for j in d:
        loc, rem = _loc_remote((j.get('workLocation') or {}).get('label'))
        out.append({'url': f"https://ats.rippling.com/{board}/jobs/{j['uuid']}",
                    'title': j.get('name'), 'location': loc, 'remote': rem})
    return out

def list_workday(key):
    host, site = key
    tenant = host.split('.')[0]
    out = []
    for kw in KEYWORDS:
        offset = 0
        while offset < MAX_WORKDAY_RESULTS_PER_QUERY:
            payload = json.dumps({"appliedFacets": {}, "limit": 20, "offset": offset,
                                  "searchText": kw}).encode()
            d = json.loads(http(f"https://{host}/wday/cxs/{tenant}/{site}/jobs",
                                data=payload, headers={"Content-Type": "application/json"}))
            postings = d.get('jobPostings', [])
            for jp in postings:
                path = jp.get('externalPath') or ''
                segs = [s for s in path.split('/') if s]
                if segs and 'job' in segs:
                    loc, rem = _loc_remote(jp.get('locationsText'))
                    out.append({'url': f"https://{host}/{site}/job/{segs[-1]}",
                                'title': jp.get('title'), 'location': loc, 'remote': rem})
            offset += 20
            if not postings or offset >= d.get('total', 0):
                break
    return out

def list_personio(host):
    xml = http(f"https://{host}/xml")
    out = []
    for block in re.findall(r'<position>(.*?)</position>', xml, re.DOTALL):
        mid = re.search(r'<id>(\d+)</id>', block)
        mname = re.search(r'<name>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</name>', block, re.DOTALL)
        moffice = re.search(r'<office>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</office>', block, re.DOTALL)
        if mid:
            loc, rem = _loc_remote(moffice.group(1).strip() if moffice else None)
            out.append({'url': f"https://{host}/job/{mid.group(1)}",
                        'title': mname.group(1).strip() if mname else None,
                        'location': loc, 'remote': rem})
    return out

def list_teamtailor(host):
    seen = {}
    for page in range(1, MAX_TEAMTAILOR_PAGES + 1):
        html_page = http(f"https://{host}/jobs?page={page}")
        links = set(re.findall(r'href="(?:https?://[^"/]+)?/jobs/(\d[^"#?/]*)"', html_page))
        new = links - set(seen)
        if not new:
            break
        for slug in new:
            # slug is "{id}-{title-with-dashes}"; good enough for keyword filtering
            title = ' '.join(slug.split('-')[1:]) or None
            seen[slug] = {'url': f"https://{host}/jobs/{slug}", 'title': title,
                          'location': None, 'remote': False}
    return list(seen.values())

def _strip_tags(s):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', s)).strip()

def list_jazzhr(host):
    html_page = http(f"https://{host}/")
    out = []
    for m in re.finditer(r'<a[^>]+href="(?:https?://[^"/]+)?/apply/([A-Za-z0-9]+)[^"]*"[^>]*>(.*?)</a>',
                         html_page, re.DOTALL):
        title = _strip_tags(m.group(2))
        out.append({'url': f"https://{host}/apply/{m.group(1)}", 'title': title or None,
                    'location': None, 'remote': False})
    return out

def list_jobvite(company):
    out = []
    for kw in KEYWORDS:
        html_page = http(f"https://jobs.jobvite.com/{company}/search?q={kw.replace(' ', '+')}")
        for m in re.finditer(r'<a[^>]+href="[^"]*/job/([A-Za-z0-9]+)"[^>]*>(.*?)</a>',
                             html_page, re.DOTALL):
            title = _strip_tags(m.group(2))
            out.append({'url': f"https://jobs.jobvite.com/{company}/job/{m.group(1)}",
                        'title': title or None, 'location': None, 'remote': False})
    return out

LISTERS = {
    'ashby': list_ashby,
    'lever': list_lever,
    'greenhouse': list_greenhouse,
    'smartrecruiters': list_smartrecruiters,
    'workable': list_workable,
    'recruitee': list_recruitee,
    'breezy': list_breezy,
    'rippling': list_rippling,
    'workday': list_workday,
    'personio': list_personio,
    'teamtailor': list_teamtailor,
    'jazzhr': list_jazzhr,
    'jobvite': list_jobvite,
}

# Full-board coverage: for these ATSs the lister sees every job on the board,
# so signals like remote-ratio and hub concentration are meaningful. Workday
# and Jobvite only see keyword-search results; Teamtailor/JazzHR lack
# locations. Signals for those are marked partial.
FULL_BOARD_ATS = {'ashby', 'lever', 'greenhouse', 'smartrecruiters', 'workable',
                  'recruitee', 'breezy', 'rippling', 'personio'}


# ---------------------------------------------------------------------------
# Stable identity for a posting across runs (survives host/slug variations)
# ---------------------------------------------------------------------------

def state_key(url):
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [s for s in p.path.split('/') if s]
    if 'greenhouse.io' in host and len(parts) >= 3:
        return f"greenhouse:{parts[0].lower()}:{parts[2]}"
    if 'smartrecruiters.com' in host and len(parts) >= 2:
        m = re.match(r'\d+', parts[1])
        return f"smartrecruiters:{parts[0].lower()}:{m.group(0) if m else parts[1].lower()}"
    if 'teamtailor.com' in host and len(parts) >= 2:
        m = re.match(r'\d+', parts[1])
        return f"teamtailor:{host}:{m.group(0) if m else parts[1].lower()}"
    if 'myworkdayjobs.com' in host and parts:
        m = re.search(r'_([A-Za-z0-9-]+)$', parts[-1])
        return f"workday:{host}:{m.group(1) if m else parts[-1].lower()}"
    if 'breezy.hr' in host and len(parts) >= 2:
        return f"breezy:{host}:{parts[1].split('-')[0]}"
    return url.lower().rstrip('/')


def scrape_one(url):
    fn = scrape.route(url)
    if fn is None:
        return None, {'url': url, 'error': 'no handler'}
    last_err = None
    for attempt in (1, 2):
        try:
            rec = fn(url)
            if rec is None:
                return None, {'url': url, 'error': 'delisted or no data'}
            rec['source_url'] = url
            return rec, None
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None, {'url': url, 'error': f'HTTP {e.code}'}
            last_err = f'HTTP {e.code}'
        except Exception as e:
            last_err = str(e)
        time.sleep(1.0)
    return None, {'url': url, 'error': last_err}


def main():
    started = datetime.now(timezone.utc)
    now_iso = started.isoformat(timespec='seconds')

    with open(os.path.join(BASE, 'unique_urls.txt')) as f:
        known_urls = [l.strip() for l in f if l.strip()]
    try:
        with open(os.path.join(BASE, 'final_jobs_sorted.json')) as f:
            previous_final = json.load(f)
    except FileNotFoundError:
        previous_final = []

    boards = boards_from_urls(known_urls)
    errors = []

    # 1. Enumerate every known board: PMM candidates + full-board signals.
    candidates = {}  # state_key -> canonical url
    board_jobs = {}  # "ats:key" -> list of job dicts (all roles, not just PMM)

    def add_candidate(url, title):
        canon = canonicalize(url) or url
        if title is not None and not relevant(title):
            return
        candidates.setdefault(state_key(canon), canon)

    tasks = [(ats, key) for ats, keys in boards.items() for key in sorted(keys, key=str)]
    print(f"Enumerating {len(tasks)} boards across {len(boards)} ATS platforms...", file=sys.stderr)
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(LISTERS[ats], key): (ats, key) for ats, key in tasks}
        for fut in as_completed(futs):
            ats, key = futs[fut]
            done += 1
            try:
                jobs_list = fut.result()
                board_jobs[f"{ats}:{key}"] = jobs_list
                for j in jobs_list:
                    add_candidate(j['url'], j.get('title'))
            except Exception as e:
                errors.append({'board': f'{ats}:{key}', 'error': str(e)})
            if done % 100 == 0:
                print(f"...{done}/{len(tasks)} boards ({len(candidates)} candidates)", file=sys.stderr)

    print(f"Board enumeration done: {len(candidates)} candidates, {len(errors)} board errors", file=sys.stderr)

    # 1b. Aggregate per-company signals from the full-board data.
    signals = {}
    for bkey, jobs_list in board_jobs.items():
        ats = bkey.split(':', 1)[0]
        sig = company_signals.compute(jobs_list, full_board=ats in FULL_BOARD_ATS)
        sig['computed_at'] = now_iso
        signals[bkey] = sig
    with open(os.path.join(BASE, 'company_signals.json'), 'w') as f:
        json.dump(signals, f, indent=0, sort_keys=True)
    print(f"Company signals written for {len(signals)} boards", file=sys.stderr)

    # 2. Re-verify everything we already show, plus known URLs on platforms
    #    without a list endpoint (iCIMS).
    for j in previous_final:
        u = j.get('source_url')
        if u:
            candidates.setdefault(state_key(u), u)
    for u in known_urls:
        if 'icims.com' in urlparse(u).netloc.lower():
            candidates.setdefault(state_key(u), u)

    # 3. Scrape every candidate through the existing per-URL processors.
    urls = sorted(candidates.values())
    print(f"Scraping {len(urls)} job URLs...", file=sys.stderr)
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(scrape_one, u): u for u in urls}
        for fut in as_completed(futs):
            done += 1
            rec, err = fut.result()
            if rec:
                results.append(rec)
            elif err:
                errors.append(err)
            if done % 200 == 0:
                print(f"...{done}/{len(urls)} scraped ({len(results)} ok)", file=sys.stderr)

    final = finalize(results)

    # 4. Diff against state to find roles first seen in this run.
    state_path = os.path.join(BASE, 'jobs_seen.json')
    try:
        with open(state_path) as f:
            seen = json.load(f)
        first_run = False
    except FileNotFoundError:
        seen = {}
        first_run = True

    new_jobs = []
    for j in final:
        key = state_key(j['source_url'])
        if key not in seen:
            seen[key] = now_iso
            if not first_run:
                new_jobs.append(j)
        j['first_seen'] = seen[key]
    new_jobs.sort(key=lambda d: d.get('posted_date') or '', reverse=True)

    with open(state_path, 'w') as f:
        json.dump(seen, f, indent=0, sort_keys=True)
    with open(os.path.join(BASE, 'final_jobs_sorted.json'), 'w') as f:
        json.dump(final, f)
    with open(os.path.join(BASE, 'new_jobs_latest.json'), 'w') as f:
        json.dump(new_jobs, f, indent=1)
    with open(os.path.join(BASE, 'refresh_errors.json'), 'w') as f:
        json.dump(errors, f, indent=1)
    with open(os.path.join(BASE, 'last_refresh.json'), 'w') as f:
        json.dump({'refreshed_at': now_iso, 'total': len(final), 'new': len(new_jobs),
                   'errors': len(errors), 'first_run': first_run}, f, indent=1)

    mins = (datetime.now(timezone.utc) - started).total_seconds() / 60
    print(f"DONE in {mins:.1f} min: {len(final)} roles ({len(new_jobs)} new, "
          f"{len(errors)} errors){' [first run: seeded state]' if first_run else ''}", file=sys.stderr)


if __name__ == '__main__':
    main()
