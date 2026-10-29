import notify


def _job(company, location, label="Remote"):
    url = f"https://jobs.ashbyhq.com/{company.lower()}/{company.lower()}-1"
    return {"title": "Product Marketing Manager", "company": company, "location": location,
            "remote_label": label, "source_url": url, "apply_url": url}


def _elig(job, regions, countries=()):
    return {notify.state_key(job["source_url"]): {
        "eligibility_stated": True, "regions": list(regions), "countries": list(countries)}}


def test_only_open_and_try_roles_are_listed_open_first():
    us, onsite, vague = _job("UsOnly", "United States"), _job("Okta", "Sydney", "On-site"), _job("NoInfo", "Remote")
    eu, emea, us_stated = _job("EuCo", "Berlin, Germany"), _job("EmeaCo", "Remote - EMEA"), _job("UsCo", "Remote")
    elig = _elig(us_stated, ["US"])
    rows = notify.select_jobs([us, onsite, vague, eu, emea, us_stated], elig, {})
    assert [(j["company"], t) for j, _, t in rows] == [("EmeaCo", "open"), ("EuCo", "try")]


def test_email_labels_tier_and_escapes():
    j = _job("<b>Co</b>", "London, UK")
    subject, body = notify.build_email(notify.select_jobs([j], {}, {}), total=907)
    assert "1 new role " in subject
    assert "worth a try" in body and "&lt;b&gt;Co&lt;/b&gt;" in body and "907" in body
