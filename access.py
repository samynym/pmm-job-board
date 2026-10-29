"""Access tier for a role against the target region config (config.TARGET)."""
import re

import config


def location_signal(location, target=None):
    """open | try | other | None from a role's location text, against the target config.
    None when the text says nothing beyond "remote"; other when it pins the role
    somewhere outside the target and try regions (e.g. "Remote (United States)")."""
    t = target or config.TARGET
    loc = (location or "").lower()
    if not loc:
        return None
    for name, key in (("open", "open_location_terms"), ("try", "try_location_terms")):
        if any(re.search(r"\b" + re.escape(term.lower()) + r"\b", loc) for term in t.get(key, [])):
            return name
    if _FILLER.sub("", loc).strip(" ,;:/|()-–"):
        return "other"
    return None


_FILLER = re.compile(r"\b(?:remote|job|jobs|not specified|fully|100%|work from home|wfh|flexible|"
                     r"home|based|first|location|locations|multiple|or|and)\b|[\s,;:/|()\-–]+")


def access_tier(regions, countries, remote_label, target=None, location=None, stated=True):
    """open | try | closed | unknown for a role, against the target region config.
    A role located in an open country is open whatever its remote label. Without
    stated eligibility, a location naming somewhere else (e.g. "San Francisco")
    closes the role whatever the company-level regions say."""
    t = target or config.TARGET
    open_countries = {c.lower() for c in t["open_countries"]}
    loc = (location or "").lower()
    if any(c in loc for c in open_countries):
        return "open"
    if (remote_label or "").strip().lower() != "remote":
        return "closed"
    sig = location_signal(location, t)
    if not stated and sig == "other":
        return "closed"
    rs = set(regions or [])
    cs = [(c or "").strip() for c in countries or []]
    if rs & set(t["open_regions"]) or any(c.lower() in open_countries for c in cs) or sig == "open":
        return "open"
    if rs & set(t["try_regions"]) or sig == "try" or any(
            location_signal(c, t) == "try" for c in cs):
        return "try"
    return "closed" if (rs or cs or sig == "other") else "unknown"
