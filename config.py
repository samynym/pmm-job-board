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

# Where the job seeker can work from. Drives the access tier (access.access_tier)
# used to pick which new roles the daily email lists. Swap these values to target
# another region.
TARGET = {
    "name": "Africa",
    "open_regions": ["Worldwide", "Africa"],
    "open_countries": ["South Africa"],
    "try_regions": ["Europe", "UK"],
    # Location text that marks a remote role as open or worth a try. A remote role
    # whose location names anywhere else (e.g. "Remote (United States)") is closed.
    "open_location_terms": ["Worldwide", "Global", "Anywhere", "International", "EMEA", "Africa",
                            "Johannesburg", "Cape Town"],
    "try_location_terms": ["Europe", "European", "EU", "CET", "CEST", "UK", "United Kingdom",
                           "England", "Scotland", "Ireland", "London", "Dublin",
                           "Germany", "Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne", "Bonn", "Stuttgart",
                           "Manchester", "Edinburgh", "Rotterdam", "Lyon", "France", "Paris", "Spain", "Madrid",
                           "Barcelona", "Portugal", "Lisbon", "Netherlands", "Amsterdam",
                           "Belgium", "Brussels", "Switzerland", "Zurich", "Austria", "Vienna",
                           "Italy", "Milan", "Rome", "Poland", "Warsaw", "Krakow", "Czechia",
                           "Czech Republic", "Prague", "Sweden", "Stockholm", "Norway", "Oslo",
                           "Denmark", "Copenhagen", "Finland", "Helsinki", "Estonia", "Tallinn",
                           "Latvia", "Lithuania", "Romania", "Bucharest", "Bulgaria", "Greece",
                           "Athens", "Hungary", "Budapest", "Croatia", "Serbia", "Slovakia",
                           "Slovenia", "Luxembourg", "Cyprus", "Malta", "Iceland", "Ukraine"],
    "try_label": "worth a try (same time zone)",
}
