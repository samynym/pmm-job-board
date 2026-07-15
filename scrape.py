import urllib.request, urllib.error, re, json, time, sys
from urllib.parse import urlparse, quote

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"

def safe_url(url):
    p = urlparse(url)
    path = quote(p.path, safe='/%')
    return f"{p.scheme}://{p.netloc}{path}" + (f"?{p.query}" if p.query else '')

def fetch(url, timeout=15):
    req = urllib.request.Request(safe_url(url), headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def extract_jsonld_jobposting(html):
    blocks = re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    for b in blocks:
        try:
            d = json.loads(b)
        except Exception:
            continue
        if isinstance(d, dict) and d.get('@type') == 'JobPosting':
            return d
        if isinstance(d, list):
            for item in d:
                if isinstance(item, dict) and item.get('@type') == 'JobPosting':
                    return item
    return None

SALARY_RE = re.compile(r'\$[\d][\d,]{2,8}(?:\s*(?:-|–|—|to)\s*\$?[\d][\d,]{2,8})?(?:\s*/\s*(?:year|yr|hour|hr|month))?', re.IGNORECASE)

def find_salary(text):
    if not text:
        return None
    text = re.sub(r'<[^>]+>', ' ', text)
    m = SALARY_RE.search(text)
    return m.group(0).strip() if m else None

def clean_text(html_frag):
    if not html_frag:
        return ''
    return re.sub(r'<[^>]+>', ' ', html_frag)

def loc_from_address(addr):
    if not addr:
        return None
    parts = [addr.get('addressLocality'), addr.get('addressRegion'), addr.get('addressCountry')]
    parts = [p for p in parts if p]
    return ', '.join(parts) if parts else None

_ashby_cache = {}

def process_ashby(url):
    p = urlparse(url)
    parts = [s for s in p.path.split('/') if s]
    company_slug = parts[0]
    jobid = parts[1]
    if company_slug not in _ashby_cache:
        try:
            api = f"https://api.ashbyhq.com/posting-api/job-board/{quote(company_slug, safe='')}?includeCompensation=true"
            raw = fetch(api)
            _ashby_cache[company_slug] = json.loads(raw)
        except Exception:
            _ashby_cache[company_slug] = None
    board = _ashby_cache[company_slug]
    if not board:
        return None
    job = next((j for j in board.get('jobs', []) if j.get('id') == jobid), None)
    if not job or not job.get('isListed', True):
        return None  # delisted / expired posting
    loc = job.get('location')
    remote_label = 'Remote' if job.get('isRemote') else (job.get('workplaceType') or 'On-site')
    if remote_label not in ('Remote', 'Hybrid', 'On-site'):
        remote_label = 'Remote' if 'remote' in str(remote_label).lower() else remote_label
    comp = job.get('compensation') or {}
    salary = comp.get('scrapeableCompensationSalarySummary') or comp.get('compensationTierSummary')
    if not salary:
        salary = find_salary(job.get('descriptionPlain', ''))
    return {
        'title': job.get('title'),
        'company': board.get('organizationName') or company_slug,
        'location': loc,
        'remote_label': remote_label,
        'posted_date': job.get('publishedAt'),
        'salary': salary,
        'apply_url': job.get('applyUrl') or job.get('jobUrl') or url,
    }

def process_lever(url):
    html = fetch(url)
    jp = extract_jsonld_jobposting(html)
    if not jp:
        return None
    loc = loc_from_address(jp.get('jobLocation', {}).get('address') if isinstance(jp.get('jobLocation'), dict) else None)
    remote_label = 'Unknown'
    lower_html = html.lower()
    # Lever posting pages have a "posting-categories" block with commitment/location/team/workplaceType
    m = re.search(r'workplace[\s_-]?type["\s:>]+([a-zA-Z\- ]{3,20})', html, re.IGNORECASE)
    if m:
        wt = m.group(1).strip().lower()
        if 'remote' in wt:
            remote_label = 'Remote'
        elif 'hybrid' in wt:
            remote_label = 'Hybrid'
        elif 'onsite' in wt or 'on-site' in wt or 'office' in wt:
            remote_label = 'On-site'
    if remote_label == 'Unknown':
        if 'remote' in lower_html[:6000]:
            remote_label = 'Remote'
    desc = jp.get('description', '') or ''
    salary = find_salary(html)
    return {
        'title': jp.get('title'),
        'company': jp.get('hiringOrganization', {}).get('name') if isinstance(jp.get('hiringOrganization'), dict) else jp.get('hiringOrganization'),
        'location': loc,
        'remote_label': remote_label,
        'posted_date': jp.get('datePosted'),
        'salary': salary,
        'apply_url': url,
    }

def process_jobvite(url):
    html = fetch(url)
    jp = extract_jsonld_jobposting(html)
    if not jp:
        return None
    jl = jp.get('jobLocation')
    addr = None
    if isinstance(jl, list) and jl:
        addr = jl[0].get('address')
    elif isinstance(jl, dict):
        addr = jl.get('address')
    loc = loc_from_address(addr)
    dtxt = clean_text(html).lower()
    remote_label = 'Unknown'
    if 'remote' in dtxt:
        remote_label = 'Remote'
    elif 'hybrid' in dtxt:
        remote_label = 'Hybrid'
    salary = find_salary(html)
    company = jp.get('hiringOrganization')
    if isinstance(company, dict):
        company = company.get('name')
    return {
        'title': jp.get('title'),
        'company': company,
        'location': loc,
        'remote_label': remote_label,
        'posted_date': jp.get('datePosted'),
        'salary': salary,
        'apply_url': url,
    }

def process_greenhouse(url):
    p = urlparse(url)
    parts = [s for s in p.path.split('/') if s]
    company = parts[0]
    jobid = parts[2]
    api = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{jobid}"
    raw = fetch(api)
    d = json.loads(raw)
    loc_name = (d.get('location') or {}).get('name')
    remote_label = 'Unknown'
    if loc_name:
        ll = loc_name.lower()
        if 'remote' in ll:
            remote_label = 'Remote'
        elif 'hybrid' in ll:
            remote_label = 'Hybrid'
        else:
            remote_label = 'On-site'
    content = d.get('content', '') or ''
    salary = find_salary(content)
    return {
        'title': d.get('title'),
        'company': d.get('company_name'),
        'location': loc_name,
        'remote_label': remote_label,
        'posted_date': d.get('first_published') or d.get('updated_at'),
        'salary': salary,
        'apply_url': d.get('absolute_url') or url,
    }

def process_smartrecruiters(url):
    p = urlparse(url)
    parts = [s for s in p.path.split('/') if s]
    company = parts[0]
    slug = parts[1]
    jobid = slug.split('-')[0]
    api = f"https://api.smartrecruiters.com/v1/companies/{company}/postings/{jobid}"
    raw = fetch(api)
    d = json.loads(raw)
    loc = d.get('location', {}) or {}
    remote_label = 'On-site'
    if loc.get('remote'):
        remote_label = 'Remote'
    elif loc.get('hybrid'):
        remote_label = 'Hybrid'
    content_all = ''
    jobad = d.get('jobAd', {}).get('sections', {}) if isinstance(d.get('jobAd'), dict) else {}
    for sec in jobad.values():
        content_all += ' ' + (sec.get('text','') or '')
    salary = find_salary(content_all)
    return {
        'title': d.get('name'),
        'company': (d.get('company') or {}).get('name'),
        'location': loc.get('fullLocation'),
        'remote_label': remote_label,
        'posted_date': d.get('releasedDate'),
        'salary': salary,
        'apply_url': d.get('applyUrl') or d.get('postingUrl') or url,
    }

def _remote_label_from_text(*texts):
    t = ' '.join(x for x in texts if x).lower()
    if 'hybrid' in t:
        return 'Hybrid'
    if 'remote' in t:
        return 'Remote'
    if 'on-site' in t or 'onsite' in t or 'on site' in t:
        return 'On-site'
    return None

def process_generic_jsonld(url, company_fallback=None):
    """Works for Breezy, Teamtailor, iCIMS, JazzHR, Personio."""
    html = fetch(url)
    jp = extract_jsonld_jobposting(html)
    if not jp:
        return None
    jl = jp.get('jobLocation')
    addr = None
    if isinstance(jl, list) and jl:
        addr = jl[0].get('address') if isinstance(jl[0], dict) else None
    elif isinstance(jl, dict):
        addr = jl.get('address')
    if isinstance(addr, str):
        loc = addr
    else:
        loc = loc_from_address(addr)
    company = jp.get('hiringOrganization')
    if isinstance(company, dict):
        company = company.get('name')
    if not company:
        company = company_fallback
    remote_label = 'Remote' if jp.get('jobLocationType') == 'TELECOMMUTE' else None
    if not remote_label:
        remote_label = _remote_label_from_text(loc, jp.get('title'), clean_text(jp.get('description', ''))[:2000]) or 'Unknown'
    salary = None
    bs = jp.get('baseSalary')
    if isinstance(bs, dict):
        v = bs.get('value', {})
        if isinstance(v, dict) and (v.get('minValue') or v.get('maxValue')):
            cur = bs.get('currency', '') or ''
            salary = f"{cur} {v.get('minValue','')}-{v.get('maxValue','')}".strip(' -')
    if not salary:
        salary = find_salary(jp.get('description', '') or html)
    return {
        'title': jp.get('title'),
        'company': company,
        'location': loc,
        'remote_label': remote_label,
        'posted_date': jp.get('datePosted'),
        'salary': salary,
        'apply_url': url,
    }

def process_workable(url):
    p = urlparse(url)
    parts = [s for s in p.path.split('/') if s]
    account, shortcode = parts[0], parts[2]
    d = json.loads(fetch(f"https://apply.workable.com/api/v2/accounts/{account}/jobs/{shortcode}"))
    loc = d.get('location') or {}
    loc_str = ', '.join(x for x in [loc.get('city'), loc.get('region'), loc.get('country')] if x) or None
    remote_label = 'Remote' if d.get('remote') else ('Hybrid' if (d.get('workplace') == 'hybrid') else 'On-site')
    desc = (d.get('description') or '') + ' ' + (d.get('requirements') or '') + ' ' + (d.get('benefits') or '')
    return {
        'title': d.get('title'),
        'company': (d.get('company') or {}).get('title') if isinstance(d.get('company'), dict) else account,
        'location': loc_str,
        'remote_label': remote_label,
        'posted_date': d.get('published'),
        'salary': find_salary(desc),
        'apply_url': url,
    }

def process_recruitee(url):
    p = urlparse(url)
    company = p.netloc.split('.')[0]
    parts = [s for s in p.path.split('/') if s]
    slug = parts[1]
    d = json.loads(fetch(f"https://{company}.recruitee.com/api/offers/{slug}"))
    o = d.get('offer', d)
    remote_label = 'Remote' if o.get('remote') else (_remote_label_from_text(o.get('location'), o.get('title')) or 'On-site')
    created = o.get('created_at')
    if created and ' UTC' in created:
        created = created.replace(' UTC', '').replace(' ', 'T') + 'Z'
    return {
        'title': o.get('title'),
        'company': o.get('company_name') or company,
        'location': o.get('location'),
        'remote_label': remote_label,
        'posted_date': created,
        'salary': find_salary(o.get('description', '') or ''),
        'apply_url': url,
    }

def process_workday(url):
    p = urlparse(url)
    host = p.netloc
    tenant = host.split('.')[0]
    parts = [s for s in p.path.split('/') if s]
    ji = parts.index('job')
    site = parts[ji-1]
    req_path = '/'.join(parts[ji+1:])
    api = f"https://{host}/wday/cxs/{tenant}/{site}/job/{req_path}"
    d = json.loads(fetch(api))
    jpi = d.get('jobPostingInfo', {})
    hiring = d.get('hiringOrganization', {}) or {}
    company = hiring.get('name') or tenant
    loc = jpi.get('location')
    remote_label = _remote_label_from_text(jpi.get('remoteType'), loc, jpi.get('title')) or 'On-site'
    if jpi.get('remoteType') and 'remote' in str(jpi.get('remoteType')).lower():
        remote_label = 'Remote'
    return {
        'title': jpi.get('title'),
        'company': company,
        'location': loc,
        'remote_label': remote_label,
        'posted_date': jpi.get('startDate'),
        'salary': find_salary(jpi.get('jobDescription', '') or ''),
        'apply_url': jpi.get('externalUrl') or url,
    }

_rippling_cache = {}

def process_rippling(url):
    p = urlparse(url)
    parts = [s for s in p.path.split('/') if s]
    board, jobid = parts[0], parts[2]
    if board not in _rippling_cache:
        try:
            _rippling_cache[board] = json.loads(fetch(f"https://api.rippling.com/platform/api/ats/v1/board/{board}/jobs"))
        except Exception:
            _rippling_cache[board] = None
    jobs = _rippling_cache[board]
    if not jobs:
        return None
    job = next((j for j in jobs if j.get('uuid') == jobid), None)
    if not job:
        return None  # delisted
    loc = (job.get('workLocation') or {}).get('label')
    remote_label = _remote_label_from_text(loc) or 'On-site'
    return {
        'title': job.get('name'),
        'company': board.replace('-careers', '').replace('-jobs', '').replace('-', ' ').title(),
        'location': loc,
        'remote_label': remote_label,
        'posted_date': None,  # Rippling board API exposes no posted date
        'salary': None,
        'apply_url': job.get('url') or url,
    }

def process_breezy(url):
    company = urlparse(url).netloc.split('.')[0]
    return process_generic_jsonld(url, company_fallback=company)

def process_teamtailor(url):
    company = urlparse(url).netloc.split('.')[0]
    return process_generic_jsonld(url, company_fallback=company)

def process_icims(url):
    host = urlparse(url).netloc
    company = re.sub(r'^(careers-|uscareers-|careersenus-|jobs-|americas-|canada-|english-|uk-|hubcareers-|cancareers-|external-|us-careers-)', '', host.split('.')[0])
    return process_generic_jsonld(url, company_fallback=company)

def process_jazzhr(url):
    company = urlparse(url).netloc.split('.')[0]
    return process_generic_jsonld(url, company_fallback=company)

def process_personio(url):
    company = urlparse(url).netloc.split('.')[0]
    rec = process_generic_jsonld(url, company_fallback=company)
    if rec and not rec.get('company'):
        rec['company'] = company
    return rec

def route(url):
    if 'ashbyhq.com' in url:
        return process_ashby
    if 'lever.co' in url:
        return process_lever
    if 'jobvite.com' in url:
        return process_jobvite
    if 'greenhouse.io' in url:
        return process_greenhouse
    if 'smartrecruiters.com' in url:
        return process_smartrecruiters
    if 'breezy.hr' in url:
        return process_breezy
    if 'apply.workable.com' in url:
        return process_workable
    if 'recruitee.com' in url:
        return process_recruitee
    if 'teamtailor.com' in url:
        return process_teamtailor
    if 'myworkdayjobs.com' in url:
        return process_workday
    if 'icims.com' in url:
        return process_icims
    if 'applytojob.com' in url:
        return process_jazzhr
    if 'ats.rippling.com' in url:
        return process_rippling
    if 'jobs.personio.de' in url:
        return process_personio
    return None

def main():
    with open('/Users/andrea/jobboard-work/unique_urls.txt') as f:
        urls = [l.strip() for l in f if l.strip()]

    results = []
    errors = []
    for i, url in enumerate(urls):
        fn = route(url)
        if fn is None:
            errors.append({'url': url, 'error': 'no handler'})
            continue
        try:
            rec = fn(url)
            if rec is None:
                errors.append({'url': url, 'error': 'no jsonld/data found'})
                continue
            rec['source_url'] = url
            results.append(rec)
        except urllib.error.HTTPError as e:
            errors.append({'url': url, 'error': f'HTTP {e.code}'})
        except Exception as e:
            errors.append({'url': url, 'error': str(e)})
        if (i+1) % 25 == 0:
            print(f"...{i+1}/{len(urls)} processed ({len(results)} ok, {len(errors)} errors)", file=sys.stderr)
        time.sleep(0.15)

    with open('/Users/andrea/jobboard-work/scraped_jobs.json', 'w') as f:
        json.dump(results, f, indent=1)
    with open('/Users/andrea/jobboard-work/scrape_errors.json', 'w') as f:
        json.dump(errors, f, indent=1)
    print(f"DONE. ok={len(results)} errors={len(errors)}", file=sys.stderr)

if __name__ == '__main__':
    main()
