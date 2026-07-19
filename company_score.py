"""Combine job-level, board-level, and web-research signals into verdicts.

Three inputs, in order of authority for a specific role:
  1. JD-stated eligibility (eligibility.json) — what THIS posting says. A
     restrictive statement (e.g. "US only") always wins for that role.
  2. Web-research verdict (company_research.json) — cited evidence about
     where the company hires.
  3. Deterministic board signals (company_signals.json) — remote ratio, hub
     concentration, regions present among remote roles.

Produces per-company verdicts (posture + africa_eligible ladder) and per-job
effective region sets used by the board filter and the leads page. The
Africa ladder is deliberately conservative: 'yes' needs direct evidence."""

import json, os

import company_signals as cs
import refresh

BASE = os.path.dirname(os.path.abspath(__file__))

AFRICA_ORDER = {'yes': 0, 'likely': 1, 'unknown': 2, 'unlikely': 3, 'no': 4}


def _load(name, default):
    try:
        with open(os.path.join(BASE, name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def load_all():
    return {
        'signals': _load('company_signals.json', {}),
        'research': _load('company_research.json', {}),
        'eligibility': _load('eligibility.json', {}),
        'jobs': _load('final_jobs_sorted.json', []),
    }


def board_key_of(url):
    for ats, keys in refresh.boards_from_urls([url]).items():
        for key in keys:
            return f"{ats}:{key}"
    return None


REGIONS = ["US", "Canada", "Latin America", "Europe", "UK", "Africa",
           "Middle East", "Asia", "Oceania"]

# rough UTC bands per region for the timezone-compatibility rule
REGION_UTC = {'US': (-8, -5), 'Canada': (-8, -3.5), 'Latin America': (-6, -3),
              'Europe': (0, 3), 'UK': (0, 1), 'Africa': (-1, 4),
              'Middle East': (2, 4.5), 'Asia': (5, 9), 'Oceania': (8, 13)}

def _tz_overlap(r1, r2, slack=1.0):
    a, b = REGION_UTC.get(r1), REGION_UTC.get(r2)
    return bool(a and b and a[0] - slack <= b[1] and b[0] - slack <= a[1])

# ccTLD → region, from the X-ray panel
from company_research import XRAY_PANEL
CC_REGION = {cc: region for region, ccs in XRAY_PANEL.items() for cc in ccs}

def company_verdict(board_key, signals, research):
    """Merge research + board signals into one company-level verdict."""
    sig = signals.get(board_key)
    res = research.get(board_key)
    board_label = cs.classify(sig) if sig else 'unknown'
    rr = (sig or {}).get('remote_region') or {}

    posture = res['remote_posture'] if res else None
    confidence = res['confidence'] if res else None
    evidence = (res or {}).get('evidence') or []
    region_map = dict((res or {}).get('region_eligibility') or {})
    for r in REGIONS:
        region_map.setdefault(r, 'unknown')

    # board data can only *upgrade* a region from unknown, never override a
    # researched verdict; remote roles located in a region are direct evidence
    def upgrade(region, level):
        if region_map.get(region) == 'unknown':
            region_map[region] = level

    if rr.get('africa'):
        upgrade('Africa', 'yes')
    if rr.get('latam'):
        upgrade('Latin America', 'yes')
    if rr.get('asia'):
        upgrade('Asia', 'yes')
    if rr.get('emea'):
        for r in ('Europe', 'Middle East', 'Africa'):
            upgrade(r, 'likely')
    if rr.get('global'):
        for r in REGIONS:
            upgrade(r, 'likely')
    if not res and board_label in ('hub-based', 'office-leaning'):
        for r in REGIONS:
            upgrade(r, 'unlikely')

    # LinkedIn X-ray distribution: employees actually living in a region is
    # direct evidence the company can employ there (many -> yes, few -> likely)
    dist = (res or {}).get('employee_distribution') or {}
    for cc, level in dist.items():
        region = CC_REGION.get(cc)
        if region and level == 'many':
            upgrade(region, 'yes')
    for cc, level in dist.items():
        region = CC_REGION.get(cc)
        if region and level == 'few':
            upgrade(region, 'likely')

    # timezone-compatibility rule (generic): when remote scope is limited for
    # TIMEZONE reasons — not legal-entity reasons — regions with overlapping
    # UTC bands are plausible even if unnamed (e.g. Europe-scoped -> Africa,
    # US-scoped -> Latin America). Only upgrades unknowns.
    tz_note = None
    if (res or {}).get('scope_basis') == 'timezone-preference':
        eligible = [r for r in REGIONS if region_map.get(r) in ('yes', 'likely')]
        for r2 in REGIONS:
            if region_map.get(r2) == 'unknown' and any(_tz_overlap(r, r2) for r in eligible):
                region_map[r2] = 'likely'
                tz_note = 'timezone-scoped hiring; UTC-band-compatible regions are plausible'

    if not posture:
        posture = {'globally-inclusive': 'multi-region', 'multi-region': 'multi-region',
                   'remote-first': 'region-locked', 'remote-friendly': 'region-locked',
                   'hub-based': 'hub-based', 'office-leaning': 'not-remote',
                   'partial-data': 'unknown', 'unknown': 'unknown'}[board_label]
        confidence = 'low'

    return {
        'posture': posture,
        'confidence': confidence,
        'tz_note': tz_note,
        'scope_basis': (res or {}).get('scope_basis'),
        'employs_via': (res or {}).get('employs_via'),
        'region_eligibility': region_map,
        'africa': region_map['Africa'],
        'board_label': board_label,
        'researched': bool(res),
        'evidence': evidence[:3],
        'hiring_regions': [r for r in REGIONS if region_map[r] in ('yes', 'likely')],
        'sig': sig or {},
    }


def all_company_verdicts(data):
    keys = set(data['signals']) | set(data['research'])
    return {b: company_verdict(b, data['signals'], data['research']) for b in keys}


def job_effective(job, elig_entry, verdict):
    """Effective filterable regions + display info for one job.

    Returns dict: regions (for bucket filtering), source ('stated'|'company'),
    africa ('yes'/'likely'/...), display, note."""
    stated = bool(elig_entry and elig_entry.get('eligibility_stated'))
    regions = list(elig_entry.get('regions') or []) if stated else []
    v = verdict or {}

    if stated:
        source = 'stated'
        africa = 'yes' if ({'Africa', 'Worldwide'} & set(regions)) else \
                 ('no' if regions else 'unknown')
    else:
        source = 'company'
        regions = list(v.get('hiring_regions') or [])
        africa = v.get('africa', 'unknown')
        if job.get('remote_label') != 'Remote':
            africa = 'no'
            regions = []
    return {'regions': regions, 'source': source, 'africa': africa,
            'company_posture': v.get('posture', 'unknown'),
            'company_africa': v.get('africa', 'unknown'),
            'researched': v.get('researched', False)}


def leads(data, verdicts, target='Africa'):
    """Tiered lead list for a target region. A: apply now (open remote roles
    workable from the target region — stated, or company verified yes).
    B: worth a shot (posting silent, company 'likely' for the target).
    C: watchlist (no current PMM role, but company hires PMMs and is
    target-region-friendly or worldwide-remote — outreach targets)."""
    by_board = {}
    for j in data['jobs']:
        b = board_key_of(j['source_url'])
        if b:
            by_board.setdefault(b, []).append(j)

    def target_verdict(v):
        return ((v.get('region_eligibility') or {}).get(target)
                or ('yes' if v.get('posture') == 'worldwide' else 'unknown'))

    tier_a, tier_b = [], []
    for b, jobs in by_board.items():
        v = verdicts.get(b) or {}
        tv = target_verdict(v)
        for j in jobs:
            if j.get('remote_label') != 'Remote':
                continue
            key = refresh.state_key(j['source_url'])
            e = data['eligibility'].get(key)
            eff = job_effective(j, e, v)
            stated_set = set(eff['regions'])
            entry = {'job': j, 'board': b, 'verdict': v, 'eff': eff,
                     'stated': bool(e and e.get('eligibility_stated')),
                     'evidence': (e or {}).get('evidence')}
            stated_target = eff['source'] == 'stated' and ({target, 'Worldwide'} & stated_set)
            stated_excludes = (entry['stated'] and stated_set
                               and not ({target, 'Worldwide'} & stated_set))
            if stated_target:
                tier_a.append(entry)
            elif stated_excludes:
                continue  # the posting names other regions; role-level wins
            elif tv == 'yes':
                tier_a.append(entry)
            elif tv == 'likely':
                tier_b.append(entry)

    covered = {b for b in by_board}
    tier_c = []
    for b, v in verdicts.items():
        if b in covered:
            continue
        if target_verdict(v) in ('yes', 'likely'):
            sig = v.get('sig') or {}
            tier_c.append({'board': b, 'verdict': v,
                           'n_jobs': sig.get('n_jobs'),
                           'remote_ratio': sig.get('remote_ratio')})

    date_key = lambda x: x['job'].get('posted_date') or ''
    tier_a.sort(key=date_key, reverse=True)
    tier_b.sort(key=date_key, reverse=True)
    tier_c.sort(key=lambda x: (AFRICA_ORDER.get(target_verdict(x['verdict']), 9),
                               -(x.get('remote_ratio') or 0)))
    return tier_a, tier_b, tier_c


BOARD_URL_TEMPLATES = {
    'ashby': 'https://jobs.ashbyhq.com/{k}',
    'greenhouse': 'https://boards.greenhouse.io/{k}',
    'lever': 'https://jobs.lever.co/{k}',
    'workable': 'https://apply.workable.com/{k}',
    'smartrecruiters': 'https://jobs.smartrecruiters.com/{k}',
    'rippling': 'https://ats.rippling.com/{k}',
    'jobvite': 'https://jobs.jobvite.com/{k}',
    'recruitee': 'https://{k}.recruitee.com',
    'breezy': 'https://{k}.breezy.hr',
}

def board_url(board_key):
    ats, k = board_key.split(':', 1)
    if ats in BOARD_URL_TEMPLATES:
        return BOARD_URL_TEMPLATES[ats].format(k=k)
    if ats in ('teamtailor', 'jazzhr', 'personio'):
        return f"https://{k}"
    if ats == 'workday':
        # key repr: "('host', 'site')"
        try:
            host, site = eval(k)  # trusted repo data
            return f"https://{host}/{site}"
        except Exception:
            return None
    return None


def company_display_name(board_key, by_board_names, research):
    r = research.get(board_key)
    if r and r.get('company'):
        return r['company']
    if board_key in by_board_names:
        return by_board_names[board_key]
    k = board_key.split(':', 1)[1]
    return k.split('.')[0].replace('-', ' ').title()
