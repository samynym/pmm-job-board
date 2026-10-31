"""Eval for the newsletter's "remote + open to US candidates" filter (notify.us_remote_reason).

Three modes:

  python evals/newsletter_eval.py
      Score the filter against the hand-labeled golden set (evals/newsletter_cases.json).
      Exits 1 if any case fails. A false INCLUDE (a non-remote / non-US role reaching
      the email) is the costly error and is reported first.

  python evals/newsletter_eval.py --audit
      Daily self-check on real traffic. For every role in new_jobs_latest.json that is
      plausibly in scope, an LLM judge reads the full posting and decides include/exclude
      independently of the filter. Disagreements are appended to evals/audit_queue.json
      for review. Needs OPENAI_API_KEY or ANTHROPIC_API_KEY; skips cleanly without one.

  python evals/newsletter_eval.py --promote <id> <include|exclude> ["why"]
      Move a reviewed audit-queue item into the golden set with your label. That case
      then guards against regressions forever. Rerun the plain eval after promoting.
"""

import json, os, sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from notify import us_remote_reason  # noqa: E402
from refresh import state_key  # noqa: E402

CASES = os.path.join(HERE, 'newsletter_cases.json')
QUEUE = os.path.join(HERE, 'audit_queue.json')


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write('\n')


def decide(job, elig):
    reason = us_remote_reason(job, elig)
    return ('exclude' if reason else 'include'), reason


# ---------------------------------------------------------------------------
# Golden-set scoring
# ---------------------------------------------------------------------------

def run_golden():
    cases = _load(CASES, [])
    false_inc, false_exc, known, fixed, ok = [], [], [], [], 0
    for c in cases:
        got, reason = decide(c['job'], c.get('eligibility'))
        if got == c['expected']:
            ok += 1
            if c.get('known_issue'):
                fixed.append(c)
        elif c.get('known_issue'):
            known.append((c, reason))
        elif got == 'include':
            false_inc.append((c, reason))
        else:
            false_exc.append((c, reason))

    n = len(cases)
    tp = sum(1 for c in cases if c['expected'] == 'include') - len(false_exc) \
        - sum(1 for c, _ in known if c['expected'] == 'include')
    fp = len(false_inc) + sum(1 for c, _ in known if c['expected'] == 'exclude')
    precision = tp / (tp + fp) if tp + fp else 1.0
    fn = len(false_exc) + sum(1 for c, _ in known if c['expected'] == 'include')
    recall = tp / (tp + fn) if tp + fn else 1.0
    print(f"Newsletter filter eval: {ok}/{n} correct  "
          f"precision={precision:.0%} (wrong roles kept out)  recall={recall:.0%} (good roles kept in)")
    for label, rows in (('FALSE INCLUDE (would wrongly be emailed)', false_inc),
                        ('FALSE EXCLUDE (good role dropped)', false_exc)):
        for c, reason in rows:
            j = c['job']
            print(f"  {label}: {j.get('title')} @ {j.get('company')} [{j.get('location')}] "
                  f"— expected {c['expected']} ({c['why']}); filter said: {reason or 'include'}")
    for c, reason in known:
        j = c['job']
        print(f"  known issue (not failing): {j.get('title')} @ {j.get('company')} — {c['known_issue']}")
    for c in fixed:
        print(f"  known issue now passes — drop its known_issue flag: {c['id']}")
    pending = _load(QUEUE, [])
    if pending:
        print(f"  {len(pending)} audit disagreement(s) awaiting review in evals/audit_queue.json")
    return 0 if not (false_inc or false_exc) else 1


# ---------------------------------------------------------------------------
# LLM audit of today's real decisions
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = (
    "You audit a job newsletter for people living in the United States who want fully "
    "remote roles. Decide from the posting alone whether a US-based candidate could take "
    "this role while working remotely from the US.\n"
    "include: the role is remote (not hybrid, not required office days) AND the posting "
    "allows hiring in the US (US explicitly, North America/Americas, or genuinely anywhere).\n"
    "exclude: on-site or hybrid; remote but limited to non-US countries/regions; or a "
    "non-US location where the US is mentioned only for customers, markets, working hours, "
    "or company-wide offices.\n"
    "unsure: the posting genuinely doesn't say. Do not guess. Quote the deciding text."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["include", "exclude", "unsure"]},
        "quote": {"type": "string", "description": "verbatim text from the posting that decides it"},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "quote", "reason"],
    "additionalProperties": False,
}
MAX_DESC = 12000


def run_audit():
    import llm
    if not llm.provider():
        print("audit: no LLM API key set — skipping")
        return 0
    from eligibility import fetch_description

    jobs = _load(os.path.join(ROOT, 'new_jobs_latest.json'), [])
    elig_all = _load(os.path.join(ROOT, 'eligibility.json'), {})
    queue = _load(QUEUE, [])
    known = {q['id'] for q in queue} | {c['id'] for c in _load(CASES, [])}

    # Only remote-labelled roles can be judged usefully; on-site/hybrid labels come
    # straight from the ATS and are excluded by the filter regardless.
    todo = [j for j in jobs if j.get('remote_label') == 'Remote']
    agree = disagree = errs = 0
    for j in todo:
        key = state_key(j.get('source_url') or '')
        elig = elig_all.get(key)
        got, reason = decide(j, elig)
        try:
            desc = fetch_description(j['source_url']) or ''
        except Exception as e:  # noqa: BLE001
            desc = ''
            print(f"  audit: couldn't fetch {j['source_url']}: {e}")
        if len(desc) > MAX_DESC:
            desc = desc[:MAX_DESC // 2] + "\n[...]\n" + desc[-MAX_DESC // 2:]
        user = (f"Title: {j.get('title')}\nCompany: {j.get('company')}\n"
                f"Location field: {j.get('location') or '(empty)'}\n"
                f"Workplace label: {j.get('remote_label')}\n\nPosting:\n{desc or '(description unavailable)'}")
        try:
            v = llm.extract_json(JUDGE_SYSTEM, user, JUDGE_SCHEMA, tier='judge')
        except Exception as e:  # noqa: BLE001
            errs += 1
            print(f"  audit: judge failed for {key}: {e}")
            continue
        if v['verdict'] == 'unsure' or v['verdict'] == got:
            agree += 1
            continue
        disagree += 1
        print(f"  DISAGREE: {j.get('title')} @ {j.get('company')} [{j.get('location')}] "
              f"filter={got} judge={v['verdict']} — {v['reason']}")
        if key in known:
            continue
        known.add(key)
        queue.append({
            'id': key,
            'job': {f: j.get(f) for f in ('title', 'company', 'location', 'remote_label', 'source_url')},
            'eligibility': ({f: elig.get(f) for f in ('eligibility_stated', 'countries', 'regions', 'evidence')}
                            if elig else None),
            'filter': got, 'filter_reason': reason,
            'judge': v['verdict'], 'judge_quote': v['quote'], 'judge_reason': v['reason'],
            'queued_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        })
    _save(QUEUE, queue)
    print(f"audit: {len(todo)} remote roles judged — {agree} agree, {disagree} disagree, "
          f"{errs} errors; {len(queue)} item(s) in review queue")
    return 0


def promote(case_id, label, why=None):
    if label not in ('include', 'exclude'):
        sys.exit("label must be include or exclude")
    queue = _load(QUEUE, [])
    item = next((q for q in queue if q['id'] == case_id), None)
    if not item:
        sys.exit(f"{case_id} not in audit queue")
    cases = _load(CASES, [])
    cases = [c for c in cases if c['id'] != case_id]
    cases.append({'id': case_id, 'job': item['job'], 'eligibility': item['eligibility'],
                  'expected': label, 'why': why or item.get('judge_reason') or '',
                  'source': f"audit {item.get('queued_at', '')[:10]}"})
    _save(CASES, cases)
    _save(QUEUE, [q for q in queue if q['id'] != case_id])
    print(f"promoted {case_id} as {label}; golden set now {len(cases)} cases")


if __name__ == '__main__':
    args = sys.argv[1:]
    if args[:1] == ['--audit']:
        sys.exit(run_audit())
    if args[:1] == ['--promote']:
        if len(args) < 3:
            sys.exit(__doc__)
        promote(args[1], args[2], args[3] if len(args) > 3 else None)
        sys.exit(0)
    sys.exit(run_golden())
