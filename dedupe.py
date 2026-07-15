import re, glob, json, os
from urllib.parse import urlparse, unquote

BASE = os.path.dirname(os.path.abspath(__file__))

def canonicalize(url):
    url = url.strip()
    if not url:
        return None
    p = urlparse(url)
    host = p.netloc.lower()
    parts = [seg for seg in p.path.split('/') if seg]
    parts = [unquote(seg) for seg in parts]

    if 'ashbyhq.com' in host:
        if len(parts) < 2:
            return None
        company, jobid = parts[0], parts[1]
        return f"https://jobs.ashbyhq.com/{company}/{jobid}"
    if 'lever.co' in host:
        if len(parts) < 2:
            return None
        company, jobid = parts[0], parts[1]
        return f"https://jobs.lever.co/{company}/{jobid}"
    if 'smartrecruiters.com' in host:
        if len(parts) < 2:
            return None
        company, slug = parts[0], parts[1]
        return f"https://jobs.smartrecruiters.com/{company}/{slug}"
    if 'jobvite.com' in host:
        if len(parts) < 3 or parts[1] != 'job':
            return None
        company, _, jobid = parts[0], parts[1], parts[2]
        return f"https://jobs.jobvite.com/{company}/job/{jobid}"
    if 'greenhouse.io' in host:
        if len(parts) < 3 or parts[1] != 'jobs':
            return None
        company, _, jobid = parts[0], parts[1], parts[2]
        prefix = 'job-boards' if 'job-boards' in host else 'boards'
        return f"https://{prefix}.greenhouse.io/{company}/jobs/{jobid}"
    if 'breezy.hr' in host:
        # {company}.breezy.hr/p/{id-slug}[/apply]
        if len(parts) < 2 or parts[0] != 'p':
            return None
        company = host.split('.')[0]
        return f"https://{company}.breezy.hr/p/{parts[1]}"
    if 'apply.workable.com' in host:
        # apply.workable.com/{company}/j/{SHORTCODE}[/apply]
        if len(parts) < 3 or parts[1] != 'j':
            return None
        return f"https://apply.workable.com/{parts[0]}/j/{parts[2].upper()}"
    if 'recruitee.com' in host:
        # {company}.recruitee.com/o/{slug}[/c/new]
        if len(parts) < 2 or parts[0] != 'o':
            return None
        company = host.split('.')[0]
        return f"https://{company}.recruitee.com/o/{parts[1]}"
    if 'teamtailor.com' in host:
        # {company}[.na].teamtailor.com/jobs/{id-slug}[/applications/new]
        if len(parts) < 2 or parts[0] != 'jobs':
            return None
        return f"https://{host}/jobs/{parts[1]}"
    if 'myworkdayjobs.com' in host:
        # {tenant}.wdN.myworkdayjobs.com/[locale/]{site}/job/[{loc}/]{Title_ReqId}[/apply...]
        if 'job' not in parts:
            return None
        ji = parts.index('job')
        site_parts = parts[:ji]
        # strip locale segment like en-US, fr-FR, es, sv-SE, pt-BR, no-NO, en-us
        site_parts = [s for s in site_parts if not re.fullmatch(r'[a-z]{2}(-[A-Za-z]{2})?', s)]
        if not site_parts:
            return None
        site = site_parts[-1]
        after = parts[ji+1:]
        # drop trailing apply/... segments
        for stop in ('apply', 'applyManually', 'autofillWithResume', 'useMyLastApplication'):
            if stop in after:
                after = after[:after.index(stop)]
        if not after:
            return None
        req = after[-1]
        return f"https://{host}/{site}/job/{req}"
    if 'icims.com' in host:
        # careers-{company}.icims.com/jobs/{id}/{slug}/job
        if len(parts) < 2 or parts[0] != 'jobs':
            return None
        return f"https://{host}/jobs/{parts[1]}/job"
    if 'applytojob.com' in host:
        # {company}.applytojob.com/apply/{id}/{slug}
        if len(parts) < 2 or parts[0] != 'apply':
            return None
        return f"https://{host}/apply/{parts[1]}"
    if 'ats.rippling.com' in host:
        # ats.rippling.com/{board}/jobs/{uuid}[/apply]
        if len(parts) < 3 or parts[1] != 'jobs':
            return None
        return f"https://ats.rippling.com/{parts[0]}/jobs/{parts[2]}"
    if 'jobs.personio.de' in host:
        # {company}.jobs.personio.de/job/{id}
        if len(parts) < 2 or parts[0] != 'job':
            return None
        return f"https://{host}/job/{parts[1]}"
    return None

def main():
    seen = {}
    source_files = sorted(glob.glob(os.path.join(BASE, 'raw', '*.txt')))
    total_raw = 0
    for fpath in source_files:
        tag = fpath.split('/')[-1].replace('.txt','')
        with open(fpath) as f:
            for line in f:
                total_raw += 1
                canon = canonicalize(line)
                if canon is None:
                    continue
                if canon not in seen:
                    seen[canon] = set()
                seen[canon].add(tag)

    print(f"Total raw lines: {total_raw}")
    print(f"Unique canonical job URLs: {len(seen)}")

    with open(os.path.join(BASE, 'unique_urls.txt'), 'w') as f:
        for url in sorted(seen.keys()):
            f.write(url + '\n')

    with open(os.path.join(BASE, 'unique_urls_sources.json'), 'w') as f:
        json.dump({url: sorted(list(tags)) for url, tags in seen.items()}, f, indent=1)

if __name__ == '__main__':
    main()
