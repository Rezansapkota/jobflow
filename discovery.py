"""Bounded browser discovery. Does not bypass login or bot challenges."""
import json
import re
from urllib.parse import urlencode, quote, urljoin
from html.parser import HTMLParser


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_html(value):
    parser = PlainText()
    parser.feed(str(value))
    return ' '.join(parser.parts).strip()


def search_url(source, role, location, page=0):
    if source == 'LinkedIn':
        return 'https://www.linkedin.com/jobs/search/?' + urlencode({'keywords': role, 'location': location, 'start': page * 25})
    slug = lambda value: quote(re.sub(r'\s+', '-', value.strip()), safe='')
    return f'https://www.seek.com.au/{slug(role)}-jobs/in-{slug(location)}?page={page + 1}'


def posting_from_json(value):
    if isinstance(value, list):
        for item in value:
            result = posting_from_json(item)
            if result:
                return result
    if isinstance(value, dict):
        kind = value.get('@type', [])
        if kind == 'JobPosting' or isinstance(kind, list) and 'JobPosting' in kind:
            return value
        if '@graph' in value:
            return posting_from_json(value['@graph'])
    return None


def extract_job(page, source, canonical_url):
    for script in page.locator('script[type="application/ld+json"]').all():
        try:
            posting = posting_from_json(json.loads(script.inner_text()))
            if posting:
                org = posting.get('hiringOrganization', {})
                title = clean_html(posting.get('title', ''))
                company = clean_html(org.get('name', '')) if isinstance(org, dict) else ''
                description = clean_html(posting.get('description', ''))
                locations = posting.get('jobLocation', [])
                locations = locations if isinstance(locations, list) else [locations]
                location = '; '.join(clean_html(json.dumps(x.get('address', {}), ensure_ascii=False)) for x in locations if isinstance(x, dict))
                if posting.get('jobLocationType'):
                    location += ' ' + str(posting['jobLocationType'])
                if title and company and len(description) >= 100:
                    return dict(url=canonical_url, source=source, title=title, company=company, description=description, location=location)
        except (ValueError, TypeError):
            continue
    selectors = {
        'LinkedIn': (['h1'], ['.job-details-jobs-unified-top-card__company-name', '.topcard__org-name-link'], ['#job-details', '.show-more-less-html__markup'], ['.job-details-jobs-unified-top-card__primary-description-container', '.topcard__flavor--bullet']),
        'SEEK': (['[data-automation="job-detail-title"]', 'h1'], ['[data-automation="advertiser-name"]'], ['[data-automation="jobAdDetails"]'], ['[data-automation="job-detail-location"]'])
    }
    def first_text(options):
        for selector in options:
            node = page.locator(selector).first
            if node.count() and node.is_visible():
                value = node.inner_text().strip()
                if value:
                    return value
        return ''
    title, company, description, location = [first_text(s) for s in selectors[source]]
    if not title or not company or len(description) < 100:
        raise ValueError('Could not extract a complete job title, company and description. No application prepared.')
    return dict(url=canonical_url, source=source, title=title, company=company, description=description, location=location)


def challenged(page):
    return bool(re.search(r'/login|/checkpoint|/authwall|/sign-in', page.url)
                or re.search(r'just a moment|security check|verify.*human|access denied', page.title(), re.I)
                or page.locator('input[type="password"]:visible, iframe[src*="captcha"]:visible').count())


def wait_for_access(agent, page, target=None):
    if not challenged(page):
        return
    agent.progress('Sign in or complete verification in the browser. Discovery resumes afterwards (up to 5 minutes).')
    for _ in range(150):
        if agent.stopped() or page.is_closed():
            raise ValueError('Discovery stopped during sign-in.')
        page.wait_for_timeout(2000)
        if not challenged(page):
            if target:
                page.goto(target, wait_until='domcontentloaded', timeout=45000)
                if challenged(page):
                    continue
            return
    raise ValueError('Sign-in or verification was not completed. Start another run after signing in.')


def discover(agent, profile, config, seen):
    """Merge sites in turn so the first site cannot consume the entire limit."""
    streams = [discover_site(agent, profile, {**config, 'sources': [source]}, seen)
               for source in config['sources']]
    active = list(streams)
    count = 0
    try:
        while active and count < config['max_jobs'] and not agent.stopped():
            for stream in list(active):
                if count >= config['max_jobs'] or agent.stopped():
                    return
                try:
                    job = next(stream)
                except StopIteration:
                    active.remove(stream)
                    continue
                count += 1
                yield job
    finally:
        for stream in streams:
            stream.close()


def discover_site(agent, profile, config, seen):
    """Yield extracted jobs, at most max_jobs across up to 3 pages per source/role."""
    from app import validate_url
    count = 0
    for source in config['sources']:
        for role in config['roles']:
            for index in range(config['pages']):
                if agent.stopped() or count >= config['max_jobs']:
                    return
                agent.progress(f'Searching {source}: {role}, {profile["search_location"]} (page {index + 1}).')
                search = agent.context.new_page()
                try:
                    target = search_url(source, role, profile['search_location'], index)
                    search.goto(target, wait_until='domcontentloaded', timeout=45000)
                    wait_for_access(agent, search, target)
                    search.wait_for_timeout(2000)
                    # Scroll only loaded results. Never repeatedly hammer blocked pages.
                    for _ in range(2):
                        search.mouse.wheel(0, 800)
                        search.wait_for_timeout(500)
                    links = search.locator('a[href*="/jobs/view/"]' if source == 'LinkedIn' else 'a[href*="/job/"]').evaluate_all('(nodes) => nodes.map(n => n.href)')
                    candidates = []
                    for link in links:
                        try:
                            url, actual_source = validate_url(link)
                            if actual_source == source and url not in seen:
                                seen.add(url)
                                candidates.append(url)
                        except ValueError:
                            continue
                    if not candidates:
                        agent.progress(f'{source}: no new accessible job links on this page. It may be empty, require sign-in, or have changed layout.')
                        break
                    for url in candidates:
                        if agent.stopped() or count >= config['max_jobs']:
                            return
                        count += 1
                        detail = agent.context.new_page()
                        try:
                            detail.goto(url, wait_until='domcontentloaded', timeout=45000)
                            wait_for_access(agent, detail, url)
                            detail.wait_for_timeout(1500)
                            yield extract_job(detail, source, url)
                        except Exception as exc:
                            agent.progress(f'Could not read {url}: {str(exc)[:180]}')
                        finally:
                            detail.close()
                except Exception as exc:
                    agent.progress(f'{source} search stopped: {str(exc)[:180]}')
                    break
                finally:
                    search.close()
