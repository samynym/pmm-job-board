"""Extract hiring-eligibility facts from remote job descriptions.

For every Remote-labeled role, pulls the full job description from the ATS and
asks Claude (Haiku) to extract ONLY what the posting states about where the
company can hire: eligible countries/regions, timezone requirements, work
authorization, employment model. No guessing — a posting that just says
"Remote" yields eligibility_stated=false. Every positive extraction carries a
short supporting quote from the description.

Results are cached in eligibility.json keyed by the same state_key(url) used
everywhere else, so each posting is extracted once, ever. Fails soft: without
ANTHROPIC_API_KEY the script exits cleanly and the pipeline continues.

Env: ANTHROPIC_API_KEY (required to extract; absent = skip).
"""

import html as html_mod
import json, os, re, sys, time
import urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urlparse, quote

import llm
import scrape
from refresh import state_key

BASE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE, 'eligibility.json')

MODEL = "claude-haiku-4-5"
MAX_EXTRACTIONS_PER_RUN = int(os.environ.get('MAX_EXTRACTIONS', '80'))  # cost guard; backfill overrides via env
MAX_WORKERS = 4
MAX_DESC_CHARS = 14000         # eligibility notes often sit at the end — keep head + tail

REGION_VOCAB = ["Worldwide", "US", "Canada", "Americas", "Latin America",
                "Europe", "UK", "Africa", "Middle East", "Asia", "Oceania"]

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "eligibility_stated": {
            "type": "boolean",
            "description": "true only if the posting explicitly states where remote hires can (or cannot) be located",
        },
        "regions": {
            "type": "array",
            "items": {"type": "string", "enum": REGION_VOCAB},
            "description": "normalized regions the company states it can hire in; empty if not stated",
        },
        "countries": {
            "type": "array",
            "items": {"type": "string"},
            "description": "specific countries explicitly listed as eligible, English names",
        },
        "timezone": {
            "type": ["string", "null"],
            "description": "stated timezone requirement, short form (e.g. 'within 3h of CET'), else null",
        },
        "work_auth": {
            "type": ["string", "null"],
            "description": "stated work-authorization requirement (e.g. 'US work authorization required'), else null",
        },
        "evidence": {
            "type": ["string", "null"],
            "description": "short verbatim quote (<=200 chars) from the posting supporting the extraction; null if eligibility_stated is false",
        },
    },
    "required": ["eligibility_stated", "regions", "countries", "timezone", "work_auth", "evidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You extract hiring-eligibility facts from job postings for remote roles.

Rules — these are strict:
- Extract ONLY what the posting explicitly states. Never infer eligibility from the company's headquarters, the currency of the salary, or the ATS platform.
- Every region you output MUST be individually supported by the evidence quote. If the posting names "US, Canada, Europe and Latin America", output exactly those — do NOT round up to neighboring regions the posting didn't name.
- A posting that says just "Remote" with no qualifier states nothing: eligibility_stated=false, empty regions.
- Perk/benefits language is NOT eligibility. "Work from anywhere", "work from home or the beach", "flexible location" in a benefits blurb describes flexibility for people the company can already employ — it does not state where the company can legally hire. Only output Worldwide when the posting states hiring/employment eligibility globally (e.g. "open to candidates in any country", "we hire worldwide", "location: Remote - Worldwide" in the location/eligibility section). If the only signal is perk language, set eligibility_stated=false.
- Location-field qualifiers count as stated: "Remote - US" means US only; "Remote (EMEA)" means Europe+Middle East+Africa.
- "Must be authorized to work in the US" (or similar) is a work_auth fact AND implies US eligibility.
- Statements like "we hire in 30+ countries" with a list: put the listed countries in countries and their regions in regions.
- "US only", "US-based": regions=["US"]. EMEA: ["Europe","Middle East","Africa"]. APAC: ["Asia","Oceania"]. LATAM: ["Latin America"].
- evidence must be a verbatim quote from the posting (<=200 chars) that supports your extraction. If eligibility_stated is false, evidence is null.
- Timezone overlap requirements ("4 hours overlap with EST") go in timezone, shortened."""


# ---------------------------------------------------------------------------
# Description fetching, per ATS (reuses scrape.py primitives)
# ---------------------------------------------------------------------------

def _strip_html(s):
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', html_mod.unescape(s)).strip()

_ashby_boards = {}

def fetch_description(url):
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [s for s in p.path.split('/') if s]

    if 'ashbyhq.com' in host:
        slug, jobid = parts[0], parts[1]
        if slug not in _ashby_boards:
            _ashby_boards[slug] = json.loads(scrape.fetch(
                f"https://api.ashbyhq.com/posting-api/job-board/{quote(slug, safe='')}"))
        job = next((j for j in _ashby_boards[slug].get('jobs', []) if j.get('id') == jobid), None)
        return (job or {}).get('descriptionPlain') or _strip_html((job or {}).get('descriptionHtml'))

    if 'greenhouse.io' in host:
        d = json.loads(scrape.fetch(
            f"https://boards-api.greenhouse.io/v1/boards/{parts[0]}/jobs/{parts[2]}"))
        return _strip_html(html_mod.unescape(d.get('content') or ''))

    if 'lever.co' in host:
        try:
            d = json.loads(scrape.fetch(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}"))
            desc = d.get('descriptionPlain') or _strip_html(d.get('description'))
            extra = ' '.join(_strip_html(x.get('content', '')) for x in d.get('lists', []))
            if desc:
                return f"{desc} {extra}".strip()
        except Exception:
            pass
        jp = scrape.extract_jsonld_jobposting(scrape.fetch(url))
        return _strip_html((jp or {}).get('description'))

    if 'smartrecruiters.com' in host:
        jobid = parts[1].split('-')[0]
        d = json.loads(scrape.fetch(
            f"https://api.smartrecruiters.com/v1/companies/{parts[0]}/postings/{jobid}"))
        sections = (d.get('jobAd') or {}).get('sections', {})
        return _strip_html(' '.join(s.get('text', '') for s in sections.values()))

    if 'apply.workable.com' in host:
        d = json.loads(scrape.fetch(
            f"https://apply.workable.com/api/v2/accounts/{parts[0]}/jobs/{parts[2]}"))
        return _strip_html(' '.join(filter(None, [d.get('description'), d.get('requirements'), d.get('benefits')])))

    if 'recruitee.com' in host:
        d = json.loads(scrape.fetch(f"https://{host.split('.')[0]}.recruitee.com/api/offers/{parts[1]}"))
        o = d.get('offer', d)
        return _strip_html(' '.join(filter(None, [o.get('description'), o.get('requirements')])))

    if 'myworkdayjobs.com' in host:
        tenant = host.split('.')[0]
        ji = parts.index('job')
        api = f"https://{host}/wday/cxs/{tenant}/{parts[ji-1]}/job/{'/'.join(parts[ji+1:])}"
        d = json.loads(scrape.fetch(api))
        return _strip_html((d.get('jobPostingInfo') or {}).get('jobDescription'))

    # breezy, teamtailor, icims, jazzhr, personio, jobvite, rippling pages:
    # generic JSON-LD carries the description for all but rippling
    jp = scrape.extract_jsonld_jobposting(scrape.fetch(url))
    return _strip_html((jp or {}).get('description'))


# ---------------------------------------------------------------------------
# Claude extraction (raw HTTP, stdlib-only like the rest of this pipeline)
# ---------------------------------------------------------------------------

def extract_one(api_key, job, desc):
    if len(desc) > MAX_DESC_CHARS:
        head = desc[:MAX_DESC_CHARS // 2]
        tail = desc[-MAX_DESC_CHARS // 2:]
        desc = f"{head}\n[...middle truncated...]\n{tail}"
    user_msg = (
        f"Job title: {job.get('title')}\n"
        f"Company: {job.get('company')}\n"
        f"Location field: {job.get('location') or '(empty)'}\n"
        f"Remote label: {job.get('remote_label')}\n\n"
        f"Job description:\n{desc}"
    )
    return llm.extract_json(SYSTEM_PROMPT, user_msg, OUTPUT_SCHEMA, tier='small')


VERIFY_MODEL = "claude-sonnet-5"

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "is_hiring_eligibility": {
            "type": "boolean",
            "description": "true only if the quote states the company can hire/employ candidates anywhere; false if it describes work flexibility for existing/eligible staff",
        },
        "reason": {"type": "string"},
    },
    "required": ["is_hiring_eligibility", "reason"],
    "additionalProperties": False,
}

def verify_worldwide(api_key, job, evidence):
    """Second-opinion check on rare Worldwide claims: hiring eligibility, or perk copy?"""
    user_msg = (
        "A job-posting analyzer claims this posting hires worldwide, citing the quote below. "
        "Distinguish carefully: statements about WHERE THE COMPANY CAN LEGALLY HIRE "
        "(\"open to candidates in any country\", \"we hire globally\", \"Remote - Worldwide\" as the location) "
        "are hiring eligibility. Statements about WORK FLEXIBILITY "
        "(\"work from home or anywhere\", \"work on your terms\", office/home/travel perks) are NOT — "
        "they describe how eligible employees may work, not who can be hired.\n\n"
        f"Job: {job.get('title')} at {job.get('company')} (location field: {job.get('location')})\n"
        f"Quote: \"{evidence}\"")
    return llm.extract_json("You judge job-posting eligibility claims precisely.",
                            user_msg, VERIFY_SCHEMA, tier='judge')


def main():
    api_key = llm.provider()
    if not api_key:
        print("no LLM API key set — skipping eligibility extraction", file=sys.stderr)
        return
    print(f"eligibility extraction via {api_key}", file=sys.stderr)

    with open(os.path.join(BASE, 'final_jobs_sorted.json')) as f:
        jobs = json.load(f)
    try:
        with open(CACHE_PATH) as f:
            cache = json.load(f)
    except FileNotFoundError:
        cache = {}

    todo = [j for j in jobs
            if j.get('remote_label') == 'Remote'
            and state_key(j['source_url']) not in cache]
    capped = False
    if len(todo) > MAX_EXTRACTIONS_PER_RUN:
        todo, capped = todo[:MAX_EXTRACTIONS_PER_RUN], True
        print(f"capping at {MAX_EXTRACTIONS_PER_RUN} extractions this run", file=sys.stderr)

    print(f"Extracting eligibility for {len(todo)} remote roles...", file=sys.stderr)
    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds')
    ok = errs = 0

    def work(job):
        key = state_key(job['source_url'])
        desc = fetch_description(job['source_url'])
        if not desc or len(desc) < 100:
            return key, {'eligibility_stated': False, 'regions': [], 'countries': [],
                         'timezone': None, 'work_auth': None, 'evidence': None,
                         'note': 'no description available', 'extracted_at': now_iso}
        result = extract_one(api_key, job, desc)
        if 'Worldwide' in result.get('regions', []):
            v = verify_worldwide(api_key, job, result.get('evidence') or '')
            if not v.get('is_hiring_eligibility'):
                result = {'eligibility_stated': False, 'regions': [], 'countries': [],
                          'timezone': result.get('timezone'), 'work_auth': result.get('work_auth'),
                          'evidence': None, 'note': f"worldwide claim rejected: {v.get('reason', '')[:140]}"}
        result['extracted_at'] = now_iso
        return key, result

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(work, j): j for j in todo}
        for fut in as_completed(futs):
            job = futs[fut]
            try:
                key, result = fut.result()
                cache[key] = result
                ok += 1
            except Exception as e:
                errs += 1
                print(f"  error [{job.get('company')} | {job.get('title')}]: {str(e)[:80]}", file=sys.stderr)
            if (ok + errs) % 25 == 0:
                print(f"  ...{ok + errs}/{len(todo)}", file=sys.stderr)
            time.sleep(0.1)

    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=0, sort_keys=True)
    stated = sum(1 for v in cache.values() if v.get('eligibility_stated'))
    print(f"ELIGIBILITY DONE: {ok} extracted, {errs} errors{' (capped)' if capped else ''}; "
          f"cache now {len(cache)} entries, {stated} with stated eligibility", file=sys.stderr)


if __name__ == '__main__':
    main()
