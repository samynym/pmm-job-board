"""Email the roles first seen in the latest refresh via Resend.

Requires env vars:
  RESEND_API_KEY  - Resend API key
  NOTIFY_EMAILS   - comma-separated recipient list
Reads new_jobs_latest.json + last_refresh.json written by refresh.py.
"""

import html, json, os, sys, urllib.request
from datetime import datetime, timezone

from refresh import state_key

BASE = os.path.dirname(os.path.abspath(__file__))
BOARD_URL = "https://samynym.github.io/pmm-job-board/"
FROM = "PMM Job Board <jobs@growsteady.me>"
MAX_ROWS = 60

def esc(s):
    return html.escape(s) if isinstance(s, str) else ''

def main():
    api_key = os.environ['RESEND_API_KEY']
    recipients = [e.strip() for e in os.environ['NOTIFY_EMAILS'].split(',') if e.strip()]

    with open(os.path.join(BASE, 'new_jobs_latest.json')) as f:
        new_jobs = json.load(f)
    with open(os.path.join(BASE, 'last_refresh.json')) as f:
        lr = json.load(f)
    try:
        with open(os.path.join(BASE, 'eligibility.json')) as f:
            eligibility = json.load(f)
    except FileNotFoundError:
        eligibility = {}

    if lr.get('first_run'):
        print("First run (state seeding) — skipping email.")
        return

    date_str = datetime.now(timezone.utc).strftime('%b %-d')
    n = len(new_jobs)
    subject = (f"PMM Job Board: {n} new role{'s' if n != 1 else ''} — {date_str}"
               if n else f"PMM Job Board: no new roles — {date_str}")

    rows = []
    for j in new_jobs[:MAX_ROWS]:
        posted = (j.get('posted_date') or '')[:10] or 'date unknown'
        salary = f" &middot; {esc(j['salary'])}" if j.get('salary') else ''
        e = eligibility.get(state_key(j.get('source_url') or ''))
        hires = ''
        if e and e.get('eligibility_stated'):
            label = ', '.join(e.get('countries') or e.get('regions') or [])
            if label:
                hires = f" &middot; hires in {esc(label)}"
        salary += hires
        rows.append(
            '<tr>'
            f'<td style="padding:10px 12px;border-bottom:1px solid #eee8da;vertical-align:top;">'
            f'<a href="{esc(j.get("apply_url") or j.get("source_url"))}" '
            f'style="color:#D97757;font-weight:600;text-decoration:none;">{esc(j.get("title"))}</a><br>'
            f'<span style="color:#4a4438;">{esc(j.get("company"))}</span>'
            f'<span style="color:#857a68;font-size:13px;"> &middot; {esc(j.get("location") or "location n/a")}'
            f' &middot; {esc(j.get("remote_label") or "?")}{salary} &middot; posted {esc(posted)}</span>'
            '</td></tr>'
        )
    more = ''
    if n > MAX_ROWS:
        more = (f'<p style="color:#857a68;">…and {n - MAX_ROWS} more — '
                f'see <a href="{BOARD_URL}" style="color:#D97757;">the full board</a>.</p>')

    body_middle = (
        f'<table style="border-collapse:collapse;width:100%;background:#fffdf9;'
        f'border:1px solid #ddd6c8;border-radius:12px;">{"".join(rows)}</table>{more}'
        if n else '<p style="color:#4a4438;">No new product marketing roles showed up in the last 24 hours.</p>'
    )

    html_body = f"""
<div style="background:#F0EEE6;padding:24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#2b2620;">
  <div style="max-width:680px;margin:0 auto;">
    <h1 style="font-size:19px;margin:0 0 4px;color:#201c17;">{n} new product marketing role{'s' if n != 1 else ''}</h1>
    <p style="font-size:13px;color:#6b6255;margin:0 0 16px;">
      First seen in the last 24 hours &middot; {lr.get('total', '?')} live roles on
      <a href="{BOARD_URL}" style="color:#D97757;">the board</a>
    </p>
    {body_middle}
    <p style="font-size:12px;color:#857a68;margin-top:18px;">
      Refreshed daily at 5:00 SAST across 15 ATS platforms &middot;
      <a href="{BOARD_URL}" style="color:#D97757;">samynym.github.io/pmm-job-board</a>
    </p>
  </div>
</div>"""

    payload = json.dumps({
        "from": FROM,
        "to": recipients,
        "subject": subject,
        "html": html_body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                 # Cloudflare fronting api.resend.com 403s (error 1010) on urllib's default UA
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode())
    print(f"Sent '{subject}' to {len(recipients)} recipients (id={resp.get('id')})")


if __name__ == '__main__':
    main()
