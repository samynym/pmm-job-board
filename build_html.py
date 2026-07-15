import json, html, os
from urllib.parse import urlparse

from refresh import state_key

BASE = os.path.dirname(os.path.abspath(__file__))

# Public by design: anon key only reaches two secret-checked RPCs (see README).
SUPABASE_URL = "https://wvtlhnyfgjkuontmpgoy.supabase.co"
SUPABASE_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Ind2dGxobnlmZ2prdW9udG1wZ295Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQxMzA3NzgsImV4cCI6MjA5OTcwNjc3OH0.zmWb1WB25bQalbn0dm54_9ckGrjD2QO5d-FPzBtHLSg"

with open(os.path.join(BASE, 'final_jobs_sorted.json')) as f:
    jobs = json.load(f)

refreshed_note = ''
try:
    with open(os.path.join(BASE, 'last_refresh.json')) as f:
        _lr = json.load(f)
    refreshed_note = ' Refreshed daily; last refresh: ' + _lr['refreshed_at'][:10] + '.'
except (FileNotFoundError, KeyError, ValueError):
    pass

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
        'key': state_key(j.get('source_url') or j.get('apply_url') or ''),
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
<meta name="viewport" content="width=device-width, initial-scale=1" />
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

  .toolbar-row { display: flex; align-items: center; gap: 12px; margin-top: 8px; flex-wrap: wrap; }
  .count { font-size: 12.5px; color: #857a68; }

  .chip {
    display: none;
    font-size: 12.5px;
    font-weight: 600;
    padding: 5px 12px;
    border-radius: 999px;
    border: 1.5px solid #ddd6c8;
    background: #fffdf9;
    color: #55503f;
    cursor: pointer;
    user-select: none;
  }
  body.tagging .chip { display: inline-block; }
  .chip.active { background: #e6f2ea; border-color: #21713f; color: #21713f; }

  #toast {
    position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%);
    background: #a33d2a; color: #fffdf9;
    font-size: 13px; font-weight: 600;
    padding: 10px 16px; border-radius: 10px;
    opacity: 0; pointer-events: none; transition: opacity .25s;
    z-index: 20; max-width: 90vw;
  }
  #toast.show { opacity: 1; }

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
    z-index: 1;
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

  /* Applied tagging (only visible with the private link) */
  .applied-col { display: none; }
  body.tagging .applied-col { display: table-cell; }
  .tagbtn {
    width: 30px; height: 30px;
    border-radius: 8px;
    border: 1.5px solid #ddd6c8;
    background: #fffdf9;
    color: transparent;
    font-size: 15px; font-weight: 700;
    cursor: pointer;
    line-height: 1;
  }
  .tagbtn:hover { border-color: #21713f; color: #d6cdbd; }
  .tagbtn.tagged { background: #e6f2ea; border-color: #21713f; color: #21713f; }
  .applied-meta { display: block; font-size: 11px; color: #8a8170; margin-top: 4px; white-space: nowrap; }
  tr.is-applied td:not(.applied-col) { opacity: 0.5; }

  ::-webkit-scrollbar { width: 10px; height: 10px; }
  ::-webkit-scrollbar-thumb { background: #ddd6c8; border-radius: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }

  /* Mobile: stacked cards instead of a wide table */
  @media (max-width: 720px) {
    .wrap { padding: 18px 12px 50px; }
    h1 { font-size: 19px; }
    .table-scroll {
      max-height: none;
      overflow: visible;
      border: none;
      background: transparent;
      margin-top: 10px;
    }
    table, tbody { display: block; width: 100%; }
    thead { display: none; }
    tbody tr {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px 8px;
      background: #fffdf9;
      border: 1px solid #ddd6c8;
      border-radius: 12px;
      padding: 12px 14px;
      margin-bottom: 10px;
    }
    tbody tr:hover { background: #fffdf9; }
    tbody td { display: block; padding: 0; border: none; }
    td.cell-role { order: 1; width: 100%; font-size: 15.5px; }
    td.cell-company { order: 2; width: 100%; font-size: 13.5px; }
    td.cell-location { order: 3; font-size: 12.5px; color: #6b6255; }
    td.cell-remote { order: 4; }
    td.cell-posted { order: 5; font-size: 12.5px; }
    td.cell-posted .posted-age { display: inline; margin-left: 4px; }
    td.cell-salary { order: 6; font-size: 12.5px; }
    td.cell-source { order: 7; }
    td.cell-apply { order: 8; margin-left: auto; }
    td.cell-apply a.apply {
      display: inline-block;
      background: #D97757; color: #fffdf9;
      padding: 8px 14px; border-radius: 9px;
      font-size: 13.5px;
    }
    body.tagging .applied-col { display: flex; align-items: center; gap: 8px; order: 0; width: 100%; padding-bottom: 6px; border-bottom: 1px dashed #eee8da; margin-bottom: 4px; }
    .tagbtn { width: 34px; height: 34px; }
    .applied-meta { margin-top: 0; }
    .empty-row { display: block; text-align: center; }
  }
</style>

<div class="wrap">
  <h1>Product Marketing Job Board</h1>
  <p class="subtitle">Sourced across 15 ATS platforms: Ashby, Lever, SmartRecruiters, Jobvite, Greenhouse, Breezy, Workable, Recruitee, Teamtailor, Workday, iCIMS, BambooHR, JazzHR, Rippling, and Personio. Click a column header to sort.__REFRESHED_NOTE__</p>

  <div class="toolbar">
    <input id="search" type="text" placeholder="Filter by company, role, location, remote, date, salary, or source..." autofocus />
    <div class="toolbar-row">
      <span class="chip" id="hide-applied">Hide applied</span>
      <div class="count" id="count"></div>
    </div>
  </div>

  <div class="table-scroll">
    <table>
      <thead>
        <tr>
          <th class="applied-col">Applied</th>
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
<div id="toast"></div>

<script>
const JOBS = __DATA_JSON__;
const SUPABASE_URL = '__SUPABASE_URL__';
const SUPABASE_ANON = '__SUPABASE_ANON__';

const hashParams = new URLSearchParams(location.hash.slice(1));
const TAG_SECRET = hashParams.get('k');
const ME = hashParams.get('me') || '';
let TAGS = {};          // job key -> {status, tagged_by, tagged_at}
let hideApplied = false;

let sortState = { key: 'posted', dir: 'desc' };

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

async function rpc(name, args) {
  const r = await fetch(SUPABASE_URL + '/rest/v1/rpc/' + name, {
    method: 'POST',
    headers: {
      'apikey': SUPABASE_ANON,
      'Authorization': 'Bearer ' + SUPABASE_ANON,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(args),
  });
  if (!r.ok) throw new Error('rpc ' + name + ' failed: ' + r.status);
  const text = await r.text();
  return text ? JSON.parse(text) : null;
}

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3500);
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

function appliedMeta(tag) {
  if (!tag) return '';
  const when = formatDate(tag.tagged_at);
  return (tag.tagged_by ? escapeHtml(tag.tagged_by) + ' \\u00b7 ' : '') + escapeHtml(when);
}

function render(filterText) {
  const tbody = document.getElementById('tbody');
  const q = (filterText || '').trim().toLowerCase();
  let shown = 0, appliedHidden = 0, appliedTotal = 0;
  const rowsHtml = [];

  const sorted = sortJobs(JOBS);

  for (const j of sorted) {
    const tag = TAGS[j.key];
    if (tag) appliedTotal++;
    const age = relativeAge(j.posted);
    const dateStr = formatDate(j.posted);
    const haystack = [j.company, j.title, j.location, j.remote, dateStr, age, j.salary, j.source]
      .filter(Boolean).join(' ').toLowerCase();
    if (q && !haystack.includes(q)) continue;
    if (hideApplied && tag) { appliedHidden++; continue; }
    shown++;
    const isRecent = age && (age === 'today' || age === '1 day ago' || (/^\\d+ days ago$/.test(age) && parseInt(age) <= 7));
    rowsHtml.push(
      '<tr' + (tag ? ' class="is-applied"' : '') + '>' +
        '<td class="applied-col">' +
          '<button class="tagbtn' + (tag ? ' tagged' : '') + '" data-key="' + escapeHtml(j.key) + '" ' +
            'aria-label="Toggle applied" title="' + (tag ? 'Applied \\u2014 click to undo' : 'Mark as applied') + '">\\u2713</button>' +
          (tag ? '<span class="applied-meta">' + appliedMeta(tag) + '</span>' : '') +
        '</td>' +
        '<td class="company cell-company">' + escapeHtml(j.company) + '</td>' +
        '<td class="role cell-role">' + escapeHtml(j.title) + '</td>' +
        '<td class="cell-location">' + escapeHtml(j.location) + '</td>' +
        '<td class="cell-remote"><span class="badge ' + badgeClass(j.remote) + '">' + escapeHtml(j.remote) + '</span></td>' +
        '<td class="posted-date cell-posted">' + escapeHtml(dateStr) +
          (age ? '<span class="posted-age' + (isRecent ? ' recent' : '') + '">' + escapeHtml(age) + '</span>' : '') +
        '</td>' +
        '<td class="salary cell-salary">' + (j.salary ? escapeHtml(j.salary) : '&#8212;') + '</td>' +
        '<td class="cell-source"><span class="source-tag">' + escapeHtml(j.source) + '</span></td>' +
        '<td class="cell-apply"><a class="apply" href="' + escapeHtml(j.apply_url) + '" target="_blank" rel="noopener noreferrer">Apply &rarr;</a></td>' +
      '</tr>'
    );
  }

  if (shown === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="9">No matching roles.</td></tr>';
  } else {
    tbody.innerHTML = rowsHtml.join('');
  }
  let countText = shown + ' of ' + JOBS.length + ' roles shown';
  if (TAG_SECRET && appliedTotal) countText += ' \\u00b7 ' + appliedTotal + ' applied';
  if (appliedHidden) countText += ' (' + appliedHidden + ' hidden)';
  document.getElementById('count').textContent = countText;
}

function currentFilter() {
  return document.getElementById('search').value;
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
    render(currentFilter());
  });
});

document.getElementById('hide-applied').addEventListener('click', (e) => {
  hideApplied = !hideApplied;
  e.target.classList.toggle('active', hideApplied);
  render(currentFilter());
});

document.getElementById('tbody').addEventListener('click', async (e) => {
  const btn = e.target.closest('.tagbtn');
  if (!btn || !TAG_SECRET) return;
  const key = btn.getAttribute('data-key');
  const prev = TAGS[key];
  if (prev) {
    delete TAGS[key];
  } else {
    TAGS[key] = { status: 'applied', tagged_by: ME, tagged_at: new Date().toISOString() };
  }
  render(currentFilter());
  try {
    await rpc('pmm_set_tag', { p_secret: TAG_SECRET, p_job_key: key, p_status: prev ? null : 'applied', p_who: ME });
  } catch (err) {
    if (prev) { TAGS[key] = prev; } else { delete TAGS[key]; }
    render(currentFilter());
    toast("Couldn't save the tag \\u2014 check your connection and try again.");
  }
});

async function initTags() {
  if (!TAG_SECRET) return;
  document.body.classList.add('tagging');
  try {
    const rows = await rpc('pmm_get_tags', { p_secret: TAG_SECRET });
    TAGS = Object.fromEntries((rows || []).map(r => [r.job_key, r]));
  } catch (err) {
    document.body.classList.remove('tagging');
    toast("Couldn't load applied tags \\u2014 wrong link key or no connection.");
  }
  render(currentFilter());
}

updateHeaderArrows();
render('');
initTags();
</script>
"""

html_out = html_out.replace('__DATA_JSON__', data_json)
html_out = html_out.replace('__REFRESHED_NOTE__', html.escape(refreshed_note))
html_out = html_out.replace('__SUPABASE_URL__', SUPABASE_URL)
html_out = html_out.replace('__SUPABASE_ANON__', SUPABASE_ANON)

for name in ('index.html', 'product-marketing-jobs.html'):
    with open(os.path.join(BASE, name), 'w') as f:
        f.write(html_out)

print("Wrote HTML with", len(rows), "rows")
