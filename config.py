# Editable config for the Product Marketing job board harvest.
# Add more ATS domains or keyword variants here, then re-run the Google-dork
# search phase (via a real browser, since Google blocks automated requests)
# for any new (domain, keyword) combos, saving results into raw/<tag>.txt.
# Then re-run dedupe.py and scrape.py to rebuild final_jobs_sorted.json,
# and finally regenerate the HTML with build_html.py.

ATS_DOMAINS = [
    "jobs.ashbyhq.com",
    "jobs.lever.co",
    "jobs.smartrecruiters.com",
    "jobs.jobvite.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "breezy.hr",              # Breezy HR ({company}.breezy.hr and app.breezy.hr)
    "apply.workable.com",     # Workable
    "recruitee.com",          # Recruitee ({company}.recruitee.com)
    "teamtailor.com",         # Teamtailor ({company}.teamtailor.com)
    "myworkdayjobs.com",      # Workday ({tenant}.wd*.myworkdayjobs.com)
    "icims.com",              # iCIMS (careers-{company}.icims.com)
    "bamboohr.com",           # BambooHR ({company}.bamboohr.com/careers)
    "applytojob.com",         # JazzHR ({company}.applytojob.com)
    "ats.rippling.com",       # Rippling ATS
    "jobs.personio.de",       # Personio ({company}.jobs.personio.de)
]

KEYWORDS = [
    "product marketing",
    "product marketer",
    # add more keyword variants here, e.g.:
    # "senior product marketing manager",
    # "PMM",
]

# Per-query Google results page cap (10 results/page). Set higher for more
# exhaustive (but slower, more CAPTCHA-prone) coverage.
MAX_PAGES_PER_QUERY = 10
