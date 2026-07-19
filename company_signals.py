"""Deterministic per-company remote-posture signals from full board data.

Given every (title, location, remote) on a company's job board, computes the
signals that JD text alone can't provide: what share of roles are remote, how
hub-concentrated hiring is, which countries appear, and whether locations
mention globally-inclusive scopes (Worldwide/EMEA/APAC/...). A company whose
whole board sits in one city is a hub employer no matter what a perk blurb
says; a company posting roles across four continents plausibly hires broadly.
"""

import re

# Location keywords per macro-region. Deliberately country-level and
# unambiguous; matched case-insensitively against full location strings.
AFRICA = ['south africa', 'nigeria', 'kenya', 'egypt', 'ghana', 'morocco',
          'tunisia', 'rwanda', 'uganda', 'tanzania', 'ethiopia', 'senegal',
          'ivory coast', "cote d'ivoire", 'cape town', 'johannesburg', 'lagos',
          'nairobi', 'cairo', 'accra', 'africa']
LATAM = ['brazil', 'argentina', 'mexico', 'colombia', 'chile', 'peru',
         'uruguay', 'costa rica', 'guatemala', 'ecuador', 'latam',
         'latin america', 'south america']
ASIA = ['india', 'philippines', 'indonesia', 'vietnam', 'thailand', 'malaysia',
        'pakistan', 'bangladesh', 'sri lanka', 'singapore', 'japan', 'china',
        'korea', 'taiwan', 'hong kong', 'apac', 'asia']
EASTERN_EU = ['poland', 'romania', 'ukraine', 'serbia', 'bulgaria', 'croatia',
              'hungary', 'czech', 'slovakia', 'lithuania', 'latvia', 'estonia',
              'georgia', 'armenia']
GLOBAL_STRINGS = ['worldwide', 'anywhere', 'global', 'emea', 'international',
                  'work from anywhere']

_WS = re.compile(r'\s+')


def _norm(loc):
    return _WS.sub(' ', (loc or '').lower()).strip()


def _any_in(loc, keywords):
    return any(k in loc for k in keywords)


def compute(jobs, full_board=True):
    """jobs: list of {title, location, remote}. Returns the signal dict."""
    n = len(jobs)
    locs = [_norm(j.get('location')) for j in jobs]
    n_remote = sum(1 for j in jobs if j.get('remote'))

    # location frequency among non-remote, non-empty locations = hub signal
    onsite_locs = [l for j, l in zip(jobs, locs) if l and not j.get('remote')]
    freq = {}
    for l in onsite_locs:
        freq[l] = freq.get(l, 0) + 1
    top_location, top_count = (max(freq.items(), key=lambda kv: kv[1])
                               if freq else (None, 0))

    distinct_locs = {l for l in locs if l}
    africa = [l for l in distinct_locs if _any_in(l, AFRICA)]
    latam = [l for l in distinct_locs if _any_in(l, LATAM)]
    asia = [l for l in distinct_locs if _any_in(l, ASIA)]
    eastern_eu = [l for l in distinct_locs if _any_in(l, EASTERN_EU)]
    global_locs = [l for l in distinct_locs if _any_in(l, GLOBAL_STRINGS)]

    remote_locs = sorted({l for j, l in zip(jobs, locs) if j.get('remote') and l})
    # region presence among REMOTE roles specifically — an office in Lagos is
    # not remote hiring in Africa, but a "Remote - EMEA" role is (weakly)
    remote_region = {
        'africa': any(_any_in(l, AFRICA) for l in remote_locs),
        'latam': any(_any_in(l, LATAM) for l in remote_locs),
        'asia': any(_any_in(l, ASIA) for l in remote_locs),
        'emea': any('emea' in l for l in remote_locs),
        'global': any(_any_in(l, ['worldwide', 'anywhere', 'global', 'international']) for l in remote_locs),
    }

    return {
        'full_board': full_board,
        'n_jobs': n,
        'n_remote': n_remote,
        'remote_ratio': round(n_remote / n, 3) if n else None,
        'n_locations': len(distinct_locs),
        'top_location': top_location,
        'top_location_share': round(top_count / n, 3) if n else None,
        'africa_locations': africa[:6],
        'latam_locations': latam[:6],
        'asia_locations': asia[:6],
        'eastern_eu_locations': eastern_eu[:6],
        'global_location_strings': global_locs[:6],
        'sample_remote_locations': remote_locs[:8],
        'remote_region': remote_region,
    }


def classify(sig):
    """First-cut deterministic label from the signals alone."""
    if not sig or not sig.get('n_jobs'):
        return 'unknown'
    ratio = sig.get('remote_ratio') or 0
    top_share = sig.get('top_location_share') or 0
    spread = bool(sig.get('africa_locations') or sig.get('latam_locations')
                  or sig.get('asia_locations'))
    global_strings = bool(sig.get('global_location_strings'))

    if not sig.get('full_board'):
        return 'partial-data'
    if global_strings and ratio >= 0.3:
        return 'globally-inclusive'
    if spread and ratio >= 0.3:
        return 'multi-region'
    if ratio >= 0.7 and (sig.get('n_locations') or 0) >= 4:
        return 'remote-first'
    if ratio < 0.2 and top_share >= 0.5 and sig['n_jobs'] >= 3:
        return 'hub-based'
    if ratio >= 0.4:
        return 'remote-friendly'
    return 'office-leaning'
