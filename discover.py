"""Discover company boards that aren't in the pool yet — no Google needed.

The daily refresh (refresh.py) finds every product-marketing role at *known*
companies, but a company only becomes known once one of its job URLs enters
raw/. This script feeds that pool automatically. One URL per company is
enough — board enumeration takes it from there.

Sources, strongest first:

  1. Workable global cross-company search (jobs.workable.com/api/v1/jobs) —
     the one big ATS with a public aggregate search. Its results don't expose
     the company's apply.workable.com slug, so we guess candidate slugs from
     the company name/website and verify against the public widget API.
  2. Hacker News "Ask HN: Who is hiring?" threads via the Algolia API —
     comments mentioning product marketing sometimes carry direct ATS links.
  3. DuckDuckGo HTML dorks (site:<ats> "<keyword>") — the same queries as the
     original manual Google phase. DDG bot-blocks bursts, so each run only
     issues a small rotating slice of the query matrix (offset persisted in
     last_discover.json) and the source aborts on anomaly pages.

New finds append to raw/auto-discovered.txt; dedupe.py then rebuilds
unique_urls.txt (also folding hand additions from raw/manual-additions.txt —
any job URL on a supported ATS, one per line).

Every source fails soft so the daily pipeline never dies on discovery.
"""

import json, os, re, sys, time
import urllib.parse, urllib.request
from datetime import datetime, timezone

import dedupe
from config import ATS_DOMAINS, KEYWORDS
from dedupe import canonicalize
from finalize import relevant
from refresh import boards_from_urls

BASE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"

WORKABLE_PAGES_PER_QUERY = 10    # 20 jobs/page
WORKABLE_RESOLVE_CAP = 40        # max slug-verification attempts per run
HN_THREADS = 2                   # latest N "Who is hiring?" stories
DDG_QUERIES_PER_RUN = 6          # rotating slice of the (domain, keyword) matrix
DDG_SLEEP = 4.0

ATS_LINK_RE = re.compile(
    r'https?://(?:jobs\.ashbyhq\.com|jobs\.lever\.co|boards\.greenhouse\.io|'
    r'job-boards\.greenhouse\.io|jobs\.smartrecruiters\.com|jobs\.jobvite\.com|'
    r'apply\.workable\.com|ats\.rippling\.com|[a-z0-9-]+\.(?:breezy\.hr|'
    r'recruitee\.com|teamtailor\.com|applytojob\.com|jobs\.personio\.de)|'
    r'[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com)/[^\s"\'<>&\\)\\]]+')


def http(url, headers=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "text/html, application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')


def get_json(url):
    return json.loads(http(url, headers={"Accept": "application/json"}))


# ---------------------------------------------------------------------------
# Source 1: Workable global search + slug verification
# ---------------------------------------------------------------------------

def slug_candidates(title, website):
    cands = []
    t = (title or '').lower()
    for c in (re.sub(r'[^a-z0-9]+', '-', t).strip('-'),
              re.sub(r'[^a-z0-9]+', '', t)):
        if c and c not in cands:
            cands.append(c)
    host = urllib.parse.urlparse(website or '').netloc
    dom = re.sub(r'^www\.', '', host).split('.')[0] if host else ''
    if dom and dom not in cands:
        cands.append(dom)
    return cands


def source_workable(log, known_boards):
    seen_companies = {}
    for kw in KEYWORDS:
        token = None
        for _ in range(WORKABLE_PAGES_PER_QUERY):
            try:
                url = f"https://jobs.workable.com/api/v1/jobs?query={urllib.parse.quote(kw)}"
                if token:
                    url += f"&pageToken={urllib.parse.quote(token)}"
                d = get_json(url)
            except Exception as e:
                log.append({'source': 'workable', 'kw': kw, 'error': str(e)})
                break
            for job in d.get('jobs', []):
                comp = job.get('company') or {}
                if relevant(job.get('title')) and comp.get('title'):
                    seen_companies.setdefault(comp['title'], comp.get('website'))
            token = d.get('nextPageToken')
            if not token:
                break
            time.sleep(0.5)

    found, attempts = [], 0
    for title, website in seen_companies.items():
        if attempts >= WORKABLE_RESOLVE_CAP:
            log.append({'source': 'workable', 'note': f'resolve cap hit, {len(seen_companies)} companies seen'})
            break
        cands = slug_candidates(title, website)
        if any(('workable', c) in known_boards for c in cands):
            continue  # already covered, save the API calls
        attempts += 1
        for slug in cands:
            try:
                w = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=false")
            except Exception:
                continue
            jobs = w.get('jobs', [])
            if not jobs:
                break
            pick = next((j for j in jobs if relevant(j.get('title'))), jobs[0])
            found.append(f"https://apply.workable.com/{slug}/j/{pick['shortcode'].upper()}")
            break
        time.sleep(0.3)
    return found


# ---------------------------------------------------------------------------
# Source 2: HN "Who is hiring?" threads
# ---------------------------------------------------------------------------

def source_hn(log):
    found = []
    try:
        stories = get_json('https://hn.algolia.com/api/v1/search_by_date'
                           '?query=%22who%20is%20hiring%22&tags=story,author_whoishiring'
                           f'&hitsPerPage={HN_THREADS}')
    except Exception as e:
        log.append({'source': 'hn', 'error': str(e)})
        return found
    for story in stories.get('hits', []):
        sid = story.get('objectID')
        try:
            comments = get_json('https://hn.algolia.com/api/v1/search'
                                f'?tags=comment,story_{sid}'
                                '&query=%22product%20marketing%22&hitsPerPage=100')
        except Exception as e:
            log.append({'source': 'hn', 'story': sid, 'error': str(e)})
            continue
        for c in comments.get('hits', []):
            text = urllib.parse.unquote(c.get('comment_text') or '')
            found += ATS_LINK_RE.findall(text.replace('&#x2F;', '/'))
        time.sleep(0.3)
    return found


# ---------------------------------------------------------------------------
# Source 3: DuckDuckGo dorks (rotating slice, anomaly-aware)
# ---------------------------------------------------------------------------

def ddg_search(query):
    q = urllib.parse.quote(query)
    for ep in (f"https://html.duckduckgo.com/html/?q={q}",
               f"https://lite.duckduckgo.com/lite/?q={q}"):
        try:
            page = http(ep)
        except Exception:
            continue
        urls = [urllib.parse.unquote(e) for e in re.findall(r'uddg=([^&"\']+)', page)]
        urls += re.findall(r'href="(https?://[^"]+)"', page)
        hits = [u for u in urls if 'duckduckgo.com' not in u]
        if hits:
            return hits
        if 'anomaly' in page.lower() or 'challenge' in page.lower():
            return None  # bot-blocked
    return []


def source_ddg(log, offset):
    matrix = [(d, k) for d in ATS_DOMAINS for k in KEYWORDS]
    found = []
    blocked = 0
    for i in range(DDG_QUERIES_PER_RUN):
        domain, kw = matrix[(offset + i) % len(matrix)]
        hits = ddg_search(f'site:{domain} "{kw}"')
        if hits is None:
            blocked += 1
            log.append({'source': 'ddg', 'query': f'{domain}|{kw}', 'error': 'anomaly page (bot-blocked)'})
            if blocked >= 2:
                log.append({'source': 'ddg', 'error': 'blocked twice, aborting source'})
                break
        else:
            found += [u for u in hits if domain in urllib.parse.urlparse(u).netloc.lower()]
        time.sleep(DDG_SLEEP)
    next_offset = (offset + DDG_QUERIES_PER_RUN) % len(matrix)
    return found, next_offset


# ---------------------------------------------------------------------------

def board_of(url):
    for ats, keys in boards_from_urls([url]).items():
        for key in keys:
            return (ats, key)
    return None


def main():
    started = datetime.now(timezone.utc)
    log = []

    with open(os.path.join(BASE, 'unique_urls.txt')) as f:
        known_urls = [l.strip() for l in f if l.strip()]
    known_boards = set()
    for ats, keys in boards_from_urls(known_urls).items():
        known_boards |= {(ats, k) for k in keys}

    try:
        with open(os.path.join(BASE, 'last_discover.json')) as f:
            dork_offset = json.load(f).get('dork_offset', 0)
    except (FileNotFoundError, ValueError):
        dork_offset = 0

    auto_path = os.path.join(BASE, 'raw', 'auto-discovered.txt')
    already_recorded = set()
    if os.path.exists(auto_path):
        with open(auto_path) as f:
            already_recorded = {l.strip() for l in f if l.strip()}

    new_urls, new_boards = [], set()

    def consider(url, source):
        canon = canonicalize(url)
        if not canon or canon in already_recorded:
            return
        board = board_of(canon)
        if board is None or board in known_boards or board in new_boards:
            return
        new_boards.add(board)
        new_urls.append(canon)
        print(f"  new board via {source}: {board[0]}:{board[1]}", file=sys.stderr)

    print("Discovery: Workable global search...", file=sys.stderr)
    for u in source_workable(log, known_boards):
        consider(u, 'workable')

    print("Discovery: HN who-is-hiring...", file=sys.stderr)
    for u in source_hn(log):
        consider(u, 'hn')

    print(f"Discovery: DDG dorks (slice at offset {dork_offset})...", file=sys.stderr)
    ddg_urls, next_offset = source_ddg(log, dork_offset)
    for u in ddg_urls:
        consider(u, 'ddg')

    if new_urls:
        with open(auto_path, 'a') as f:
            for u in new_urls:
                f.write(u + '\n')
    # always rebuild: folds raw/manual-additions.txt even when nothing auto-found
    dedupe.main()

    with open(os.path.join(BASE, 'last_discover.json'), 'w') as f:
        json.dump({
            'ran_at': started.isoformat(timespec='seconds'),
            'new_boards': sorted(f'{a}:{k}' for a, k in new_boards),
            'new_urls': len(new_urls),
            'errors': len(log),
            'dork_offset': next_offset,
        }, f, indent=1)
    with open(os.path.join(BASE, 'discover_errors.json'), 'w') as f:
        json.dump(log, f, indent=1)

    mins = (datetime.now(timezone.utc) - started).total_seconds() / 60
    print(f"DISCOVERY DONE in {mins:.1f} min: {len(new_boards)} new boards, "
          f"{len(log)} source errors", file=sys.stderr)


if __name__ == '__main__':
    main()
