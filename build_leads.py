"""Render leads.html — the prioritized opportunity list for Cape Town.

Three tiers from company_score.leads():
  A. Apply now — open remote PMM roles workable from Africa (stated in the
     posting, or company verified Africa-eligible).
  B. Worth a shot — open remote roles where the posting is silent but the
     company looks Africa-friendly (research says "likely").
  C. Watchlist — companies with no current PMM opening, but they hire PMMs
     (that's how they entered the pool) and hire remotely in Africa-inclusive
     scopes: outreach targets for when a role opens (or before it does).
"""

import html, json, os
from datetime import datetime, timezone

import company_score

BASE = os.path.dirname(os.path.abspath(__file__))


def esc(s):
    return html.escape(s) if isinstance(s, str) else ''


def ev_links(evidence):
    out = []
    for e in (evidence or [])[:2]:
        url, quote = e.get('url'), e.get('quote', '')
        if url:
            out.append(f'<a class="ev" href="{esc(url)}" target="_blank" rel="noopener" '
                       f'title="{esc(quote[:160])}">source</a>')
    return ' '.join(out)


def job_row(entry, target):
    j, v, eff = entry['job'], entry['verdict'], entry['eff']
    posted = (j.get('posted_date') or '')[:10] or '—'
    if entry['stated']:
        basis = f'<span class="basis stated" title="{esc(entry.get("evidence") or "")}">posting: {esc(", ".join(eff["regions"][:4]))}</span>'
    else:
        tz = f' · {esc(v["tz_note"])}' if v.get('tz_note') else ''
        tv = (v.get('region_eligibility') or {}).get(target, '?')
        dist = f' · {esc(v["distribution_summary"])}' if v.get('distribution_summary') else ''
        basis = (f'<span class="basis company">company: {esc(v.get("posture") or "?")}, '
                 f'{esc(target)} {esc(tv)} ({esc(v.get("confidence") or "low")}){tz}{dist}</span> '
                 + ev_links(v.get('evidence')))
    salary = f'<span class="sal">{esc(j["salary"])}</span>' if j.get('salary') else ''
    return (
        '<div class="lead">'
        f'<div class="lead-main"><a class="role" href="{esc(j.get("apply_url"))}" target="_blank" rel="noopener">'
        f'{esc(j.get("title"))}</a><span class="co">{esc(j.get("company"))}</span></div>'
        f'<div class="lead-meta">{basis} {salary}'
        f'<span class="posted">posted {esc(posted)}</span></div>'
        '</div>'
    )


def watch_row(entry, research, target):
    b, v = entry['board'], entry['verdict']
    name = company_score.company_display_name(b, {}, research)
    url = company_score.board_url(b)
    tv = (v.get('region_eligibility') or {}).get(target, '?')
    sig_bits = []
    if entry.get('n_jobs'):
        sig_bits.append(f"{entry['n_jobs']} open roles")
    if entry.get('remote_ratio') is not None:
        sig_bits.append(f"{int((entry['remote_ratio'] or 0) * 100)}% remote")
    return (
        '<div class="lead">'
        f'<div class="lead-main"><span class="role">{esc(name)}</span>'
        f'<span class="co">{esc(target)} {esc(tv)} · {esc(v.get("posture") or "?")}'
        + (f' · {" · ".join(sig_bits)}' if sig_bits else '') + '</span></div>'
        f'<div class="lead-meta">{ev_links(v.get("evidence"))}'
        + (f' <a class="ev" href="{esc(url)}" target="_blank" rel="noopener">careers page</a>' if url else '')
        + '</div></div>'
    )


TARGET_REGION = os.environ.get('TARGET_REGION', 'Africa')

def main():
    data = company_score.load_all()
    verdicts = company_score.all_company_verdicts(data)
    tier_a, tier_b, tier_c = company_score.leads(data, verdicts, target=TARGET_REGION)
    research = data['research']
    generated = datetime.now(timezone.utc).strftime('%b %-d, %Y')

    n_researched = sum(1 for v in verdicts.values() if v.get('researched'))

    def section(title, sub, items):
        body = ''.join(items) if items else '<div class="none">Nothing here yet.</div>'
        return (f'<h2>{title} <span class="n">{len(items)}</span></h2>'
                f'<p class="sub">{sub}</p>{body}')

    tz_line = (' timezone note: SAST (UTC+2) overlaps all European hours, so EMEA/CET-overlap roles fit.'
               if TARGET_REGION == 'Africa' else '')
    page = f"""<title>PMM Leads — remote-workable from {esc(TARGET_REGION)}</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; background: #F0EEE6; color: #2b2620;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  .wrap {{ max-width: 860px; margin: 0 auto; padding: 28px 20px 60px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; color: #201c17; }}
  .subtitle {{ font-size: 13px; color: #6b6255; margin: 0 0 6px; }}
  .backlink {{ font-size: 12.5px; }} a {{ color: #D97757; }}
  h2 {{ font-size: 16px; margin: 28px 0 2px; color: #201c17; }}
  h2 .n {{ background: #e6f2ea; color: #21713f; font-size: 12px; border-radius: 999px; padding: 2px 9px; vertical-align: 2px; }}
  .sub {{ font-size: 12.5px; color: #857a68; margin: 2px 0 12px; }}
  .lead {{ background: #fffdf9; border: 1px solid #ddd6c8; border-radius: 12px; padding: 12px 15px; margin-bottom: 9px; }}
  .lead-main {{ display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
  .role {{ font-weight: 650; font-size: 14.5px; text-decoration: none; }}
  .co {{ color: #6b6255; font-size: 12.5px; }}
  .lead-meta {{ margin-top: 5px; font-size: 12px; color: #55503f; display: flex; gap: 12px; flex-wrap: wrap; align-items: baseline; }}
  .basis.stated {{ color: #21713f; font-weight: 600; }}
  .basis.company {{ color: #91591a; font-style: italic; }}
  .ev {{ font-size: 11.5px; }}
  .sal {{ color: #4a4438; }}
  .posted {{ color: #8a8170; }}
  .none {{ color: #8a8170; font-size: 13px; padding: 8px 2px; }}
  .note {{ background: #fdf1e2; border: 1px solid #ecd9b8; border-radius: 10px; padding: 10px 14px; font-size: 12.5px; color: #6b5330; margin: 14px 0 0; }}
</style>
<div class="wrap">
  <h1>PMM Leads — remote-workable from {esc(TARGET_REGION)}</h1>
  <p class="subtitle">Generated {generated} · {n_researched} companies web-researched with cited evidence ·{tz_line}</p>
  <p class="backlink"><a href="index.html">&larr; full job board</a></p>

  {section("Apply now", f"Open remote PMM roles workable from {esc(TARGET_REGION)} — the posting states it, or the company is verified eligible.", [job_row(x, TARGET_REGION) for x in tier_a])}
  {section("Worth a shot", f"Posting is silent on eligibility, but the company looks {esc(TARGET_REGION)}-friendly (evidence-cited “likely”). Apply, but expect some misses.", [job_row(x, TARGET_REGION) for x in tier_b])}
  {section("Watchlist — outreach targets", "No PMM opening today, but they hire PMMs (that's how they're in this pool) and hire remotely in matching scopes. Reach out before the role is posted.", [watch_row(x, research, TARGET_REGION) for x in tier_c])}

  <div class="note">Verdicts combine three signals: what each posting states (always wins when restrictive),
  web-researched company hiring posture with cited sources, and live analysis of every role on the company's
  own job board (remote ratio, hub concentration, regions hired into).</div>
</div>"""

    with open(os.path.join(BASE, 'leads.html'), 'w') as f:
        f.write(page)
    print(f"leads.html: A={len(tier_a)} B={len(tier_b)} C={len(tier_c)}")


if __name__ == '__main__':
    main()
