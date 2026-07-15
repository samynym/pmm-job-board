import json, html
from urllib.parse import urlparse

with open('/Users/andrea/jobboard-work/final_jobs_sorted.json') as f:
    jobs = json.load(f)

def esc(s):
    return html.escape(s) if isinstance(s, str) else ''

def ats_name(url):
    host = urlparse(url or '').netloc.lower()
    if 'ashbyhq.com' in host: return 'Ashby'
    if 'lever.co' in host: return 'Lever'
    if 'smartrecruiters.com' in host: return 'SmartRecruiters'
    if 'jobvite.com' in host: return 'Jobvite'
    if 'greenhouse.io' in host: return 'Greenhouse'
    if 'breezy.hr' in host: return 'Breezy'
    if 'workable.com' in host: return 'Workable'
    if 'recruitee.com' in host: return 'Recruitee'
    if 'teamtailor.com' in host: return 'Teamtailor'
    if 'myworkdayjobs.com' in host: return 'Workday'
    if 'icims.com' in host: return 'iCIMS'
    if 'applytojob.com' in host: return 'JazzHR'
    if 'rippling.com' in host: return 'Rippling'
    if 'personio.de' in host: return 'Personio'
    return 'Other'

rows = []
for j in jobs:
    rows.append({
        'company': j.get('company') or '',
        'title': j.get('title') or '',
        'location': j.get('location') or 'Not specified',
        'remote': j.get('remote_label') or 'Unknown',
        'posted': j.get('posted_date'),
        'salary': j.get('salary'),
        'apply_url': j.get('apply_url'),
        'source': ats_name(j.get('source_url') or j.get('apply_url')),
    })

data_json = json.dumps(rows, ensure_ascii=False)

html_out = """<title>Product Marketing Job Board</title>
<style>
  :root { color-scheme: light; }
  :root[data-theme="dark"] { color-scheme: light; }

  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    background: #F0EEE6 !important;
    color: #2b2620;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    html, body { background: #F0EEE6 !important; color: #2b2620 !important; }
  }

  .wrap { max-width: 1240px; margin: 0 auto; padding: 28px 20px 60px; }

  h1 { font-size: 22px; margin: 0 0 4px; font-weight: 650; color: #201c17; }
  .subtitle { font-size: 13px; color: #6b6255; margin: 0 0 20px; }

  .toolbar {
    position: sticky; top: 0; z-index: 5;
    background: #F0EEE6;
    padding: 12px 0 14px;
    border-bottom: 1px solid #ddd6c8;
  }
  #search {
    width: 100%;
    font-size: 15px;
    padding: 11px 14px;
    border-radius: 10px;
    border: 1.5px solid #ddd6c8;
    background: #fffdf9;
    color: #201c17;
    outline: none;
  }
  #search:focus { border-color: #D97757; box-shadow: 0 0 0 3px rgba(217,119,87,0.15); }

  .count { font-size: 12.5px; color: #857a68; margin-top: 8px; }

  .table-scroll {
    margin-top: 16px;
    border: 1px solid #ddd6c8;
    border-radius: 12px;
    overflow: auto;
    max-height: 74vh;
    background: #fffdf9;
  }
  table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
  thead th {
    position: sticky; top: 0;
    background: #ece7d9;
    text-align: left;
    padding: 10px 12px;
    font-weight: 650;
    color: #2b2620;
    border-bottom: 1px solid #ddd6c8;
    white-space: nowrap;
    cursor: pointer;
    user-select: none;
  }
  thead th:hover { background: #e5e0d0; }
  thead th .arrow { color: #D97757; margin-left: 3px; font-size: 11px; }
  tbody td {
    padding: 10px 12px;
    border-bottom: 1px solid #eee8da;
    vertical-align: top;
    color: #2b2620;
  }
  tbody tr:hover { background: #f7f2e6; }
  tbody tr:last-child td { border-bottom: none; }

  .role { font-weight: 600; }
  .company { font-weight: 500; color:#4a4438; }

  .badge {
    display: inline-block;
    font-size: 11.5px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .badge-remote { background: #e6f2ea; color: #21713f; }
  .badge-hybrid { background: #fdf1e2; color: #91591a; }
  .badge-onsite { background: #efe9db; color: #55503f; }
  .badge-unknown { background: #efe9db; color: #8a8170; }

  .source-tag {
    display: inline-block;
    font-size: 11.5px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 6px;
    white-space: nowrap;
    background: #eee3d8;
    color: #7a4a2c;
  }

  .posted-date { white-space: nowrap; }
  .posted-age { display: block; font-size: 11.5px; color: #8a8170; }
  .posted-age.recent { color: #21713f; font-weight: 600; }

  a.apply {
    color: #D97757;
    text-decoration: none;
    font-weight: 600;
    white-space: nowrap;
  }
  a.apply:hover { text-decoration: underline; }

  .salary { white-space: nowrap; color: #4a4438; }
  .empty-row td { text-align: center; color: #8a8170; padding: 30px; }

  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-thumb { background: #ddd6c8; border-radius: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
</style>

<div class="wrap">
  <h1>Product Marketing Job Board</h1>
  <p class="subtitle">Sourced via Google dorks across 15 ATS platforms: Ashby, Lever, SmartRecruiters, Jobvite, Greenhouse, Breezy, Workable, Recruitee, Teamtailor, Workday, iCIMS, BambooHR, JazzHR, Rippling, and Personio. Click a column header to sort.</p>

  <div class="toolbar">
    <input id="search" type="text" placeholder="Filter by company, role, location, remote, date, salary, or source..." autofocus />
    <div class="count" id="count"></div>
  </div>

  <div class="table-scroll">
    <table>
      <thead>
        <tr>
          <th data-key="company">Company</th>
          <th data-key="title">Role</th>
          <th data-key="location">Location</th>
          <th data-key="remote">Remote?</th>
          <th data-key="posted">Posted</th>
          <th data-key="salary">Salary</th>
          <th data-key="source">Source</th>
          <th>Link</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</div>

<script>
const JOBS = __DATA_JSON__;
let sortState = { key: 'posted', dir: 'desc' };

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function relativeAge(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  const now = new Date();
  const diffMs = now - d;
  const diffDay = Math.floor(diffMs / 86400000);
  if (diffDay < 0) return 'upcoming';
  if (diffDay === 0) return 'today';
  if (diffDay === 1) return '1 day ago';
  if (diffDay < 30) return diffDay + ' days ago';
  const diffMonth = Math.floor(diffDay / 30);
  if (diffMonth < 12) return diffMonth + (diffMonth === 1 ? ' month ago' : ' months ago');
  const diffYear = Math.floor(diffMonth / 12);
  return diffYear + (diffYear === 1 ? ' year ago' : ' years ago');
}

function badgeClass(label) {
  const l = (label || 'Unknown').toLowerCase();
  if (l === 'remote') return 'badge-remote';
  if (l === 'hybrid') return 'badge-hybrid';
  if (l === 'on-site') return 'badge-onsite';
  return 'badge-unknown';
}

function formatDate(iso) {
  if (!iso) return 'date unknown';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return 'date unknown';
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function sortJobs(list) {
  const { key, dir } = sortState;
  const mult = dir === 'asc' ? 1 : -1;
  return list.slice().sort((a, b) => {
    let av = a[key], bv = b[key];
    if (key === 'posted') {
      av = av ? new Date(av).getTime() : -Infinity;
      bv = bv ? new Date(bv).getTime() : -Infinity;
      return (av - bv) * mult;
    }
    av = (av || '').toString().toLowerCase();
    bv = (bv || '').toString().toLowerCase();
    if (av < bv) return -1 * mult;
    if (av > bv) return 1 * mult;
    return 0;
  });
}

function updateHeaderArrows() {
  document.querySelectorAll('th[data-key]').forEach(th => {
    const key = th.getAttribute('data-key');
    const label = th.getAttribute('data-label') || th.textContent.replace(/[\\u25B2\\u25BC]/g, '').trim();
    th.setAttribute('data-label', label);
    if (key === sortState.key) {
      th.innerHTML = label + '<span class="arrow">' + (sortState.dir === 'asc' ? '\\u25B2' : '\\u25BC') + '</span>';
    } else {
      th.innerHTML = label;
    }
  });
}

function render(filterText) {
  const tbody = document.getElementById('tbody');
  const q = (filterText || '').trim().toLowerCase();
  let shown = 0;
  const rowsHtml = [];

  const sorted = sortJobs(JOBS);

  for (const j of sorted) {
    const age = relativeAge(j.posted);
    const dateStr = formatDate(j.posted);
    const haystack = [j.company, j.title, j.location, j.remote, dateStr, age, j.salary, j.source]
      .filter(Boolean).join(' ').toLowerCase();
    if (q && !haystack.includes(q)) continue;
    shown++;
    const isRecent = age && (age === 'today' || age === '1 day ago' || (/^\\d+ days ago$/.test(age) && parseInt(age) <= 7));
    rowsHtml.push(
      '<tr>' +
        '<td class="company">' + escapeHtml(j.company) + '</td>' +
        '<td class="role">' + escapeHtml(j.title) + '</td>' +
        '<td>' + escapeHtml(j.location) + '</td>' +
        '<td><span class="badge ' + badgeClass(j.remote) + '">' + escapeHtml(j.remote) + '</span></td>' +
        '<td class="posted-date">' + escapeHtml(dateStr) +
          (age ? '<span class="posted-age' + (isRecent ? ' recent' : '') + '">' + escapeHtml(age) + '</span>' : '') +
        '</td>' +
        '<td class="salary">' + (j.salary ? escapeHtml(j.salary) : '&#8212;') + '</td>' +
        '<td><span class="source-tag">' + escapeHtml(j.source) + '</span></td>' +
        '<td><a class="apply" href="' + escapeHtml(j.apply_url) + '" target="_blank" rel="noopener noreferrer">Apply &rarr;</a></td>' +
      '</tr>'
    );
  }

  if (shown === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="8">No matching roles.</td></tr>';
  } else {
    tbody.innerHTML = rowsHtml.join('');
  }
  document.getElementById('count').textContent = shown + ' of ' + JOBS.length + ' roles shown';
}

document.getElementById('search').addEventListener('input', (e) => render(e.target.value));

document.querySelectorAll('th[data-key]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.getAttribute('data-key');
    if (sortState.key === key) {
      sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
    } else {
      sortState = { key, dir: key === 'posted' ? 'desc' : 'asc' };
    }
    updateHeaderArrows();
    render(document.getElementById('search').value);
  });
});

updateHeaderArrows();
render('');
</script>
"""

html_out = html_out.replace('__DATA_JSON__', data_json)

with open('/Users/andrea/jobboard-work/product-marketing-jobs.html', 'w') as f:
    f.write(html_out)

print("Wrote HTML with", len(rows), "rows")
