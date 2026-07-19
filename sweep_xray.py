"""Fill missing employee_distribution entries in company_research.json.

Runs the LinkedIn ccTLD X-ray (company_research.xray_one) for every researched
company that doesn't yet have a distribution — verification-relevant companies
first. Saves incrementally. Reusable any time; no-ops when nothing is missing.
"""

import json, os, sys, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import llm
from company_research import CACHE_PATH, xray_one

BASE = os.path.dirname(os.path.abspath(__file__))
MAX_WORKERS = int(os.environ.get('XRAY_WORKERS', '6'))


def main():
    if not llm.available():
        print("no LLM API key — skipping", file=sys.stderr)
        return
    with open(CACHE_PATH) as f:
        research = json.load(f)

    # priority: Africa yes/likely first (they gate the leads page)
    def prio(item):
        b, v = item
        africa = (v.get('region_eligibility') or {}).get('Africa', 'unknown')
        return {'yes': 0, 'likely': 1}.get(africa, 2)

    todo = sorted(((b, v) for b, v in research.items()
                   if not v.get('employee_distribution')), key=prio)
    print(f"X-ray sweep: {len(todo)} companies via {llm.provider()}", file=sys.stderr)

    lock = threading.Lock()
    done = [0]

    def save():
        with open(CACHE_PATH, 'w') as f:
            json.dump(research, f, indent=1, sort_keys=True)

    def work(b, v):
        x = xray_one(v.get('company') or b)
        with lock:
            v['employee_distribution'] = x['distribution']
            v['distribution_summary'] = x['summary']
            done[0] += 1
            if done[0] % 10 == 0:
                save()
        print(f"  [{done[0]}] {v.get('company')}: {x['summary'][:90]}", file=sys.stderr, flush=True)

    errs = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(work, b, v): b for b, v in todo}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                errs += 1
                print(f"  error [{futs[fut]}]: {str(e)[:80]}", file=sys.stderr, flush=True)
    save()
    print(f"SWEEP DONE: {done[0]} filled, {errs} errors", file=sys.stderr)


if __name__ == '__main__':
    main()
