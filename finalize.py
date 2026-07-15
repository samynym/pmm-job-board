import html, json, re, os

BASE = os.path.dirname(os.path.abspath(__file__))

def relevant(title):
    if not title:
        return False
    t = title.lower()
    if 'product market' in t:
        return True
    if re.search(r'\bpmm\b', t):
        return True
    return False

def fix_mojibake(s):
    if not isinstance(s, str):
        return s
    if 'â' in s or 'Ã' in s:
        try:
            return s.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s

def finalize(data):
    for d in data:
        for k in ('title', 'company', 'location', 'salary'):
            v = fix_mojibake(d.get(k))
            # some ATS titles arrive pre-escaped ("R&amp;D") — store plain text
            d[k] = html.unescape(v) if isinstance(v, str) else v

    rel = [d for d in data if relevant(d.get('title'))]

    # final dedupe safety net: same company+title+date scraped via different source URLs
    seen = {}
    for d in rel:
        key = (
            (d.get('company') or '').strip().lower(),
            (d.get('title') or '').strip().lower(),
            (d.get('posted_date') or '')[:10],
        )
        if key not in seen:
            seen[key] = d

    final = list(seen.values())
    # newest first; missing dates sink to the bottom
    final.sort(key=lambda d: d.get('posted_date') or '', reverse=True)
    return final

def main():
    data = json.load(open(os.path.join(BASE, 'scraped_jobs.json')))
    final = finalize(data)
    rel = [d for d in data if relevant(d.get('title'))]

    with open(os.path.join(BASE, 'final_jobs_sorted.json'), 'w') as f:
        json.dump(final, f)

    print(f"scraped={len(data)} relevant={len(rel)} final={len(final)}")
    no_date = sum(1 for d in final if not d.get('posted_date'))
    print(f"missing posted_date: {no_date}")

if __name__ == '__main__':
    main()
