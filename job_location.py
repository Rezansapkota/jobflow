"""Conservative locality matching without guessing travel or relocation preferences."""
import json
import re

REGIONS = {
    'northern territory': 'nt', 'new south wales': 'nsw', 'south australia': 'sa',
    'western australia': 'wa', 'australian capital territory': 'act',
    'queensland': 'qld', 'victoria': 'vic', 'tasmania': 'tas',
}


def profile_location(profile):
    location = (profile.get('location') or '').strip()
    search = (profile.get('search_location') or '').strip()
    # Contact addresses can include a house number. Use the user's saved search
    # area for these rather than guessing which metro area a suburb belongs to.
    street_address = re.search(r'\d', location) and re.search(
        r'\b(street|st|road|rd|crescent|cres|avenue|ave|drive|dr|lane|ln|court|ct|terrace|tce|highway|hwy|parade|pde)\b', location, re.I)
    if street_address:
        return search
    return location or search


def tokens(value):
    value = value.casefold()
    for name, short in REGIONS.items():
        value = re.sub(r'\b' + name + r'\b', short, value)
    return set(re.findall(r'\b[\w]+\b', value)) - {'australia', 'au'}


def matches(profile, job):
    target = tokens(profile_location(profile))
    if not target or not job.get('location', '').strip():
        return False
    regions = set(REGIONS.values())
    target_regions = target & regions
    locality = target - regions
    # A postcode complements a named locality; it is required for postcode-only searches.
    if any(not word.isdigit() for word in locality):
        locality = {word for word in locality if not word.isdigit()}
    for place in job['location'].split(';'):
        try:
            address = json.loads(place.strip())
            if isinstance(address, dict):
                place = ' '.join(str(address.get(k, '')) for k in ('addressLocality', 'addressRegion', 'postalCode', 'addressCountry'))
        except (ValueError, TypeError):
            pass
        actual = tokens(place)
        if target_regions and actual & regions and not target_regions <= actual:
            continue
        if locality and locality <= actual:
            return True
        if not locality and target_regions and target_regions <= actual:
            return True
    return False
