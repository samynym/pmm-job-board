"""Adversarially verify high-stakes region-eligibility verdicts.

For every researched company whose TARGET_REGION verdict is yes/likely, runs a
skeptic pass (web-search-armed) that tries to refute the verdict and checks
that the cited evidence holds up. Downgrades are applied to region_eligibility
with an audit block. Region-generic: set TARGET_REGION env (default Africa).
"""

import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import llm
from company_research import CACHE_PATH, XRAY_PANEL

TARGET = os.environ.get('TARGET_REGION', 'Africa')
MAX_WORKERS = int(os.environ.get('VERIFY_WORKERS', '4'))
ORDER = {'no': 0, 'unlikely': 1, 'unknown': 2, 'likely': 3, 'yes': 4}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "refuted": {"type": "boolean"},
        "final": {"type": "string", "enum": ["yes", "likely", "unknown", "unlikely", "no"]},
        "reasoning": {"type": "string"},
        "new_evidence": {"type": "array",
                         "items": {"type": "object",
                                   "properties": {"quote": {"type": "string"},
                                                  "url": {"type": "string"}},
                                   "required": ["quote", "url"],
                                   "additionalProperties": False}},
    },
    "required": ["refuted", "final", "reasoning", "new_evidence"],
    "additionalProperties": False,
}

SYSTEM = f"""You are a skeptic verifying a claim that a company can hire remote employees located in {TARGET}. A job-seeker will spend real effort based on this verdict — a false positive wastes it, so lean toward refuting when evidence is thin; but do not refute what solid evidence supports (explicit hiring countries, employees living there, worldwide hiring via an EOR).

Do BOTH checks:
1. REFUTE ATTEMPT (web search): are their remote roles normally scoped away from {TARGET}? statements limiting hiring to specific countries/entities? hub-concentrated hiring? Also run the LinkedIn X-ray for {TARGET}: search site:{{cc}}.linkedin.com/in "at {{company}}" for cc in {', '.join(XRAY_PANEL.get(TARGET, []))} — real current-employee profiles there are strong CONFIRMING evidence (report in new_evidence); zero hits is a mild refuting signal.
2. EVIDENCE INTEGRITY: for each cited quote+URL given to you, check the page plausibly exists and the claim is a fair reading. Claims resting on misread or fabricated evidence are refuted.

final = your honest {TARGET} verdict after both checks."""


def main():
    if not llm.available():
        print("no LLM API key — skipping", file=sys.stderr)
        return
    with open(CACHE_PATH) as f:
        research = json.load(f)

    todo = [(b, v) for b, v in research.items()
            if (v.get('region_eligibility') or {}).get(TARGET) in ('yes', 'likely')
            and not (v.get('verification') or {}).get(TARGET)]
    print(f"verifying {len(todo)} {TARGET} verdicts via {llm.provider()}", file=sys.stderr)

    now_iso = datetime.now(timezone.utc).isoformat(timespec='seconds')
    lock = threading.Lock()

    def save():
        with open(CACHE_PATH, 'w') as f:
            json.dump(research, f, indent=1, sort_keys=True)

    def work(b, v):
        verdict = v['region_eligibility'][TARGET]
        ev = '\n'.join(f"- {e.get('claim')}: \"{e.get('quote')}\" ({e.get('url')})"
                       for e in (v.get('evidence') or []))
        dist = v.get('distribution_summary') or 'not collected'
        user = (f"Company: {v.get('company') or b}\n"
                f"Claimed {TARGET} verdict: {verdict} "
                f"(posture: {v.get('remote_posture')}, scope: {v.get('scope_basis')})\n"
                f"Employee-distribution finding: {dist}\n"
                f"Cited evidence:\n{ev or '(none)'}")
        r = llm.research_json(SYSTEM, user, VERDICT_SCHEMA, effort='medium')
        final = r['final'] if ORDER[r['final']] < ORDER[verdict] else verdict
        with lock:
            v.setdefault('verification', {})[TARGET] = {
                'original': verdict, 'final': final, 'refuted': r['refuted'],
                'reasoning': r['reasoning'][:400],
                'new_evidence': r['new_evidence'][:3], 'verified_at': now_iso}
            v['region_eligibility'][TARGET] = final
        arrow = '' if final == verdict else f" -> {final}"
        print(f"  {v.get('company')}: {verdict}{arrow}", file=sys.stderr, flush=True)

    errs = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(work, b, v): b for b, v in todo}
        for i, fut in enumerate(as_completed(futs)):
            try:
                fut.result()
            except Exception as e:
                errs += 1
                print(f"  error [{futs[fut]}]: {str(e)[:80]}", file=sys.stderr, flush=True)
            if (i + 1) % 5 == 0:
                with lock:
                    save()
    save()
    print(f"VERIFY DONE: {len(todo) - errs} verified, {errs} errors", file=sys.stderr)


if __name__ == '__main__':
    main()
