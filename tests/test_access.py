import pytest
from access import access_tier


@pytest.mark.parametrize("label,location", [
    ("On-site", "Cape Town, South Africa"), ("Hybrid", "Johannesburg, South Africa")])
def test_role_located_in_open_country_is_open(label, location):
    assert access_tier([], [], label, location=location) == "open"


def test_non_remote_role_is_closed():
    assert access_tier(["Worldwide"], [], "Hybrid", location="London, UK") == "closed"
    assert access_tier([], [], "On-site", location=None) == "closed"
    assert access_tier([], [], "Unknown", location="UK") == "closed"


@pytest.mark.parametrize("location,stated,regions,countries,tier", [
    ("Remote (United States)", False, [], None, "closed"),
    ("U.S. Remote", False, [], None, "closed"),
    ("New York, San Francisco, Seattle, Remote", False, ["Europe"], None, "closed"),
    ("San Francisco", False, ["Europe", "UK"], None, "closed"),
    ("Remote", False, [], None, "unknown"),
    ("Remote job", False, ["Europe"], None, "try"),
    ("Remote - EMEA", False, [], None, "open"),
    ("Anywhere", False, [], None, "open"),
    ("Cardiff, London or Remote (UK)", False, [], None, "try"),
    ("Berlin, Germany", False, [], None, "try"),
    ("Hyderabad, Telangana, India", True, [], ["India"], "closed"),
    ("London, UK", True, [], ["United Kingdom"], "try"),
    ("New York", True, ["Europe"], [], "try"),
])
def test_location_decides_remote_tier(location, stated, regions, countries, tier):
    assert access_tier(regions, countries, "Remote", location=location, stated=stated) == tier
