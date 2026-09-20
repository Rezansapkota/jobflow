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


def search_url(source, role, location, page=0, posted_days=0, sort_order='relevance'):
    if source == 'LinkedIn':
        params = {'keywords': role, 'location': location, 'start': page * 25}
        if posted_days:
            params['f_TPR'] = f'r{posted_days * 86400}'
        if sort_order == 'newest':
            params['sortBy'] = 'DD'
        return 'https://www.linkedin.com/jobs/search/?' + urlencode(params)
    slug = lambda value: quote(re.sub(r'\s+', '-', value.strip()), safe='')
    params = {'page': page + 1}
    if posted_days:
        params['daterange'] = posted_days
    if sort_order == 'newest':
        params['sortmode'] = 'ListedDate'
    return f'https://www.seek.com.au/{slug(role)}-jobs/in-{slug(location)}?' + urlencode(params)


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
                    return dict(url=canonical_url, source=source, title=title, company=company, description=description, location=location, date_posted=str(posting.get('datePosted') or ''))
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
    if source == 'LinkedIn' and (not title or not company or len(description) < 100):
        # New signed-in layout uses generated classes and no h1.
        about = page.get_by_role('heading', name='About the job', exact=True)
        parts = page.title().rsplit(' | ', 2)
        if about.count() == 1 and len(parts) == 3 and parts[-1] == 'LinkedIn':
            section = about.locator('../..')
            text = section.locator('[data-testid="expandable-text-box"]').first
            if text.count():
                description = text.inner_text().strip()
                title, company = parts[0].strip(), parts[1].strip()
                main_lines = [line.strip() for line in page.locator('main').inner_text().splitlines() if line.strip()]
                if title in main_lines:
                    position = main_lines.index(title)
                    location = main_lines[position + 1].split('\u00b7')[0].strip() if position + 1 < len(main_lines) else ''
    if not title or not company or len(description) < 100:
        raise ValueError('Could not extract a complete job title, company and description. No application prepared.')
    posted_label = first_text(['[data-automation="jobListingDate"]', '.posted-time-ago__text', '.jobs-unified-top-card__posted-date'])
    return dict(url=canonical_url, source=source, title=title, company=company, description=description, location=location, posted_label=posted_label)


def challenged(page):
    return bool(re.search(r'/login|/checkpoint|/authwall|/sign-in|/signup|/sign-up', page.url)
                or re.search(r'just a moment|security check|verify.*human|access denied|^(sign in|sign up|join).*linkedin', page.title(), re.I)
                or page.get_by_text(re.compile(r'confirm you are human|verify you are human|help us keep SEEK secure', re.I)).count()
                or page.locator('input[type="password"]:visible, iframe[src*="captcha"]:visible').count())


def wait_for_job(page):
    """Allow client-rendered descriptions or verification screens to finish loading."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    try:
        page.wait_for_function('''() => {
            const body = document.body?.innerText || '';
            return /confirm you are human|verify you are human|help us keep SEEK secure/i.test(body)
                || /just a moment|security check|access denied/i.test(document.title)
                || [...document.querySelectorAll('[data-automation="jobAdDetails"], #job-details, .show-more-less-html__markup, [data-testid="expandable-text-box"]')].some(n => n.innerText?.trim().length >= 100)
                || [...document.querySelectorAll('script[type="application/ld+json"]')].some(n => n.textContent.includes('JobPosting'));
        }''', timeout=8000)
    except PlaywrightTimeout:
        pass  # Extraction supplies the final, specific error.


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
    def issue(message):
        agent.progress(message)
        if hasattr(agent, 'source_issues'):
            agent.source_issues.append(message)
    for source in config['sources']:
        for role in config['roles']:
            for index in range(config['pages']):
                if agent.stopped() or count >= config['max_jobs']:
                    return
                agent.progress(f'Searching {source}: {role}, {profile["search_location"]} (page {index + 1}).')
                search = agent.context.new_page()
                try:
                    target = search_url(source, role, profile['search_location'], index, config.get('posted_days', 0), config.get('sort_order', 'relevance'))
                    search.goto(target, wait_until='domcontentloaded', timeout=45000)
                    if challenged(search):
                        if agent.headless is False:
                            wait_for_access(agent, search, target)
                        else:
                            issue(f'{source}: verification or sign-in required in the search browser. Your saved login may still be valid. Choose Visible Chrome in Search options to continue on the site.')
                            return
                    search.wait_for_timeout(2000)
                    # Scroll only loaded results. Never repeatedly hammer blocked pages.
                    for _ in range(2):
                        search.mouse.wheel(0, 800)
                        search.wait_for_timeout(500)
                    if challenged(search):
                        if agent.headless is False:
                            wait_for_access(agent, search, target)
                        else:
                            issue(f'{source}: verification or sign-in required in the search browser. Choose Visible Chrome in Search options to continue on the site.')
                            return
                    links = search.locator('a[href*="/jobs/view/"]' if source == 'LinkedIn' else 'a[href*="/job/"]').evaluate_all('(nodes) => nodes.map(n => n.href)')
                    listing_dates = {}
                    if source == 'SEEK':
                        cards = search.locator('article').evaluate_all('''nodes => nodes.map(n => ({
                            url: n.querySelector('a[data-automation="jobTitle"]')?.href,
                            posted: n.querySelector('[data-automation="jobListingDate"]')?.innerText
                        }))''')
                        for card in cards:
                            if not isinstance(card, dict) or not card.get('url') or not card.get('posted'):
                                continue
                            try:
                                card_url, card_source = validate_url(card['url'])
                                if card_source == source:
                                    listing_dates[card_url] = card['posted'].strip().splitlines()[0]
                            except ValueError:
                                continue
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
                        if links:
                            agent.progress(f'{source}: these listings are already tracked. Checking the next configured page.')
                            continue
                        issue(f'{source}: no readable job links found. The page may be empty, blocked, or have changed layout. Open the site to check your search.')
                        break
                    for url in candidates:
                        if agent.stopped() or count >= config['max_jobs']:
                            return
                        count += 1
                        detail = agent.context.new_page()
                        try:
                            detail.goto(url, wait_until='domcontentloaded', timeout=45000)
                            wait_for_job(detail)
                            if challenged(detail):
                                if agent.headless is False:
                                    wait_for_access(agent, detail, url)
                                    wait_for_job(detail)
                                else:
                                    issue(f'{source}: verification or sign-in required in the search browser. Choose Visible Chrome in Search options to continue on the site.')
                                    return
                            job = extract_job(detail, source, url)
                            if not job.get('date_posted') and not job.get('posted_label') and url in listing_dates:
                                job['posted_label'] = listing_dates[url]
                            yield job
                        except Exception as exc:
                            issue(f'Could not read {url}: {str(exc)[:180]}')
                        finally:
                            detail.close()
                except Exception as exc:
                    if 'ERR_NETWORK_ACCESS_DENIED' in str(exc):
                        issue(f'{source}: Chrome cannot access the internet. Restart Jobflow outside the restricted environment or allow its browser through your network security settings, then retry.')
                        return
                    issue(f'{source} search stopped: {str(exc)[:180]}')
                    break
                finally:
                    search.close()
