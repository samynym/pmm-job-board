"""Web-research a company's remote-hiring posture, with citations.

For companies that matter (current remote PMM role, or remote-leaning board
signals), asks Claude — armed with server-side web search + web fetch — to
establish where the company can actually hire: careers-page hiring-country
lists, remote-company directories (Himalayas, RemoteOK, remote.co),
handbooks/blogs, EOR usage (Deel/Remote.com/Oyster), and LinkedIn snippets
surfaced by search. Every claim must carry a source URL and quote. The
deterministic board signals are passed in as context to be reconciled, not
repeated back.

Cached in company_research.json (re-researched after RESEARCH_TTL_DAYS).
Fails soft without ANTHROPIC_API_KEY.
"""

import json, os, sys, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import llm
import scrape
import company_signals as cs

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE, 'company_research.json')

MODEL = os.environ.get('RESEARCH_MODEL', 'claude-sonnet-5')
MAX_RESEARCH_PER_RUN = int(os.environ.get('MAX_RESEARCH', '15'))
RESEARCH_TTL_DAYS = 90
MAX_WORKERS = int(os.environ.get('RESEARCH_WORKERS', '3'))
MAX_CONTINUATIONS = 6

REGIONS = ["US", "Canada", "Latin America", "Europe", "UK", "Africa",
           "Middle East", "Asia", "Oceania"]
ELIG = {"type": "string", "enum": ["yes", "likely", "unlikely", "no", "unknown"]}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "remote_posture": {"type": "string",
                           "enum": ["worldwide", "multi-region", "region-locked",
                                    "hub-based", "not-remote", "unknown"]},
        "region_eligibility": {
            "type": "object",
            "description": "for EACH region: can the company realistically hire a remote employee living there?",
            "properties": {r: ELIG for r in REGIONS},
            "required": REGIONS,
            "additionalProperties": False,
        },
        "scope_basis": {"type": "string",
                        "enum": ["legal-entity", "timezone-preference", "mixed", "unclear"],
                        "description": "when the company limits remote scope, is the limit about where they can legally employ, or about working-hours overlap?"},
        "employs_via": {"type": ["string", "null"],
                        "description": "how they employ internationally if found (own entities / EOR name / contractors)"},
        "evidence": {"type": "array",
                     "description": "at most 5 items",
                     "items": {"type": "object",
                               "properties": {"claim": {"type": "string"},
                                              "quote": {"type": "string"},
                                              "url": {"type": "string"}},
                               "required": ["claim", "quote", "url"],
                               "additionalProperties": False}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["remote_posture", "region_eligibility", "scope_basis",
                 "employs_via", "evidence", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You research where a company can actually hire remote employees. You have web search and web fetch.

Look for, in rough priority order:
1. The company's own careers page: remote policy, "we hire in these countries" lists, location scopes on other open roles.
2. Remote-company directories (Himalayas company profiles list hiring countries; also RemoteOK, remote.co, WeWorkRemotely).
3. Handbook/blog/press statements about being remote-first or distributed, and where employees are located.
4. EOR usage: mentions of Deel, Remote.com, Oyster, Omnipresent in their postings or pages imply they can employ in many countries.
5. LinkedIn X-ray via search: 'site:linkedin.com/in "at {company}"' surfaces public employee profiles; country-coded subdomains filter by employee location — e.g. 'site:za.linkedin.com/in "at {company}"' returns only South-Africa-based employees (za=South Africa, ng=Nigeria, ke=Kenya, br=Brazil, in=India, pl=Poland...). Real profile hits in a country are direct evidence the company employs people there. For common-word company names, add a product/domain term to disambiguate.

Strict rules:
- Every conclusion needs evidence with a real URL you actually saw and a short verbatim quote from it. No evidence, no claim.
- Distinguish work-flexibility perk language ("work from anywhere" benefits copy) from hiring eligibility ("we hire in 40 countries"). Perk language alone does not make a company worldwide.
- A company hiring remotely only within one region is region-locked, not worldwide.
- Judge EVERY region independently in region_eligibility. "yes" needs explicit evidence for that region (hiring-country list, employees/roles there, worldwide hiring with EOR). "likely" needs strong indirect evidence. When in doubt: "unknown". Do not be generous — a false "yes" costs someone a wasted application.
- scope_basis matters: figure out WHY a scope is limited. Stated legal/payroll/entity reasons ("we can only employ where we have entities") = legal-entity. Stated hours/collaboration reasons ("to ensure overlap with CET") = timezone-preference. Both = mixed. Unstated = unclear.
- Key inference you SHOULD make: if a company scopes remote hiring to a region for timezone reasons AND uses an EOR (Deel, Remote.com, Oyster, Omnipresent — check their job postings and pages), then countries in compatible timezones outside that region are "likely" even if unnamed. Example: "Remote - Europe" + hires via Deel → South Africa (UTC+2, matches CET) is "likely"; the Americas stay "unlikely". Without EOR evidence, do not make this upgrade.
- 2-5 searches are usually enough. If little is found, say unknown with low confidence."""


# ccTLD panel for the LinkedIn X-ray, region-balanced. US has no ccTLD
# (profiles live on www.linkedin.com) — 'us' here means the www variant.
XRAY_PANEL = {
    'Africa': ['za', 'ng', 'ke'],
    'Middle East': ['ae', 'sa'],
    'Europe': ['uk', 'de', 'fr', 'pl'],
    'Latin America': ['br', 'mx', 'co'],
    'Asia': ['in', 'ph', 'sg', 'jp'],
    'Oceania': ['au'],
    'Canada': ['ca'],
    'US': ['us'],
}
ALL_CCS = [cc for ccs in XRAY_PANEL.values() for cc in ccs]

XRAY_SCHEMA = {
    "type": "object",
    "properties": {
        "distribution": {
            "type": "object",
            "description": "per country-code: how many current-employee LinkedIn profiles the X-ray searches surfaced",
            "properties": {cc: {"type": "string", "enum": ["none", "few", "many", "unknown"]}
                           for cc in ALL_CCS},
            "required": ALL_CCS,
            "additionalProperties": False,
        },
        "summary": {"type": "string",
                    "description": "one sentence: where this company's employees actually live"},
    },
    "required": ["distribution", "summary"],
    "additionalProperties": False,
}

XRAY_PROMPT = """You estimate where a company's employees live using LinkedIn X-ray searches.

Technique: public LinkedIn profiles are indexed on country-coded subdomains. Search
  site:{cc}.linkedin.com/in "at {company}"
for each requested country code ({cc}=za,ng,ke,ae,sa,uk,de,fr,pl,br,mx,co,in,ph,sg,jp,au,ca).
For the US use  site:www.linkedin.com/in "at {company}".
For common-word company names add a disambiguating product/domain term.

Batch efficiently: you can OR several ccTLDs in one query, e.g.
  ("site:za.linkedin.com/in" OR "site:ng.linkedin.com/in" OR "site:ke.linkedin.com/in") "at {company}"
Judge from actual profile results (current employees only — ignore "former/ex-"):
none = 0 profiles; few = 1-3; many = 4+; unknown = search failed/ambiguous."""


def xray_one(company_name):
    user = f'Company: "{company_name}". Estimate the employee-location distribution per the panel.'
    return llm.research_json(XRAY_PROMPT, user, XRAY_SCHEMA, effort='low', tier='small')


def research_one(api_key, company_name, board_key, sig, sample_titles):
    context = {
        'board_ats': board_key.split(':', 1)[0],
        'jobs_on_board': sig.get('n_jobs'),
        'remote_ratio': sig.get('remote_ratio'),
        'top_location': sig.get('top_location'),
        'sample_remote_locations': sig.get('sample_remote_locations'),
        'board_classification': cs.classify(sig),
    }
    user_msg = (
        f"Company: {company_name}\n"
        f"(ATS board id: {board_key}; sample roles: {', '.join(sample_titles[:4])})\n\n"
        f"Deterministic signals from their live job board, to reconcile with what you find:\n"
        f"{json.dumps(context, indent=1)}\n\n"
        "Research their remote-hiring posture and answer per the schema."
    )
    return llm.research_json(SYSTEM_PROMPT, user_msg, OUTPUT_SCHEMA, effort='medium')


def companies_to_research(signals, jobs, cache):
    """Priority order: remote PMM role now > remote-leaning board posture."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RESEARCH_TTL_DAYS)).isoformat()
    import refresh
    by_board = {}
    for j in jobs:
        b = board_key_of(j['source_url'])
        if b:
            by_board.setdefault(b, []).append(j)

    # tier 1: companies with a current REMOTE PMM role (on-site-only PMM
    # companies are skipped — researching them doesn't serve the remote goal);
    # tier 2: remote-leaning boards with no current PMM role (watchlist).
    ordered = []
    for b, js in by_board.items():
        if any(j.get('remote_label') == 'Remote' for j in js):
            ordered.append((0, b))
    remote_postures = {'globally-inclusive', 'multi-region', 'remote-first'}
    for b, sig in signals.items():
        if b not in by_board and cs.classify(sig) in remote_postures:
            ordered.append((1, b))
    ordered.sort()

    out = []
    for _, b in ordered:
        entry = cache.get(b)
        if entry and entry.get('researched_at', '') > cutoff:
            continue
        out.append(b)
    return out, by_board


def board_key_of(url):
    import refresh
    for ats, keys in refresh.boards_from_urls([url]).items():
        for key in keys:
            return f"{ats}:{key}"
    return None


def company_name_for(board_key, by_board, signals):
    js = by_board.get(board_key) or []
    for j in js:
        if j.get('company'):
            return j['company']
    return board_key.split(':', 1)[1].split('.')[0].replace('-', ' ')


def main():
    api_key = llm.provider()
    if not api_key:
        print("no LLM API key set — skipping company research", file=sys.stderr)
        return
    print(f"company research via {api_key} ({llm.MODELS[api_key]['research']})", file=sys.stderr)

    with open(os.path.join(BASE, 'final_jobs_sorted.json')) as f:
        jobs = json.load(f)
    with open(os.path.join(BASE, 'company_signals.json')) as f:
        signals = json.load(f)
    try:
        with open(CACHE_PATH) as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    todo, by_board = companies_to_research(signals, jobs, cache)
    if len(todo) > MAX_RESEARCH_PER_RUN:
        print(f"capping research at {MAX_RESEARCH_PER_RUN} of {len(todo)} due", file=sys.stderr)
        todo = todo[:MAX_RESEARCH_PER_RUN]

    print(f"Researching {len(todo)} companies...", file=sys.stderr)
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds')
    ok = errs = 0

    def work(b):
        sig = signals.get(b) or {}
        name = company_name_for(b, by_board, signals)
        titles = [j.get('title') or '' for j in (by_board.get(b) or [])] or \
                 ['(no current PMM role)']
        result = research_one(api_key, name, b, sig, titles)
        result['company'] = name
        result['researched_at'] = now_iso
        try:
            x = xray_one(name)
            result['employee_distribution'] = x['distribution']
            result['distribution_summary'] = x['summary']
        except Exception as e:
            print(f"  xray failed [{name}]: {str(e)[:60]}", file=sys.stderr, flush=True)
        return b, result

    import threading
    lock = threading.Lock()

    def save():
        with open(CACHE_PATH, 'w') as f:
            json.dump(cache, f, indent=1, sort_keys=True)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(work, b): b for b in todo}
        for fut in as_completed(futs):
            b = futs[fut]
            try:
                key, result = fut.result()
                with lock:
                    cache[key] = result
                    ok += 1
                    if ok % 5 == 0:
                        save()  # incremental: a crash keeps progress
                re_map = result.get('region_eligibility') or {}
                yes = [r for r, v in re_map.items() if v in ('yes', 'likely')]
                print(f"  [{ok + errs}] {result['company']}: {result['remote_posture']}/{result.get('scope_basis')} "
                      f"regions={yes} ({result['confidence']})", file=sys.stderr, flush=True)
            except Exception as e:
                errs += 1
                print(f"  error [{b}]: {str(e)[:100]}", file=sys.stderr, flush=True)

    save()
    print(f"RESEARCH DONE: {ok} researched, {errs} errors; cache {len(cache)} companies", file=sys.stderr)


if __name__ == '__main__':
    main()
