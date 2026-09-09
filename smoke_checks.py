"""Opt-in live read-only checks; never submits applications or saves a fake profile."""
import json
import sys


def model_check():
    from local_ai import assess, cover_letter
    from test_automation import PROFILE, JOB
    print('Assessment:', json.dumps(assess(PROFILE, JOB)), flush=True)
    print('Cover letter:', cover_letter(PROFILE, JOB), flush=True)


def search_check():
    from playwright.sync_api import sync_playwright
    from discovery import search_url, extract_job
    from app import validate_url
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge')
        for source in ['LinkedIn', 'SEEK']:
            page = browser.new_page()
            try:
                page.goto(search_url(source, 'customer service', 'Darwin'), wait_until='domcontentloaded', timeout=45000)
                page.wait_for_timeout(2500)
                links = page.locator('a[href*="/jobs/view/"]' if source == 'LinkedIn' else 'a[href*="/job/"]').evaluate_all('(nodes) => nodes.map(n => n.href)')
                valid = []
                for link in links:
                    try:
                        url, _ = validate_url(link)
                        if url not in valid:
                            valid.append(url)
                    except ValueError:
                        pass
                print(json.dumps({'source': source, 'title': page.title(), 'url': page.url, 'job_links': len(valid)}), flush=True)
                if valid:
                    page.goto(valid[0], wait_until='domcontentloaded', timeout=45000)
                    page.wait_for_timeout(2000)
                    job = extract_job(page, source, valid[0])
                    print(json.dumps({'source': source, 'extracted_title': job['title'], 'description_chars': len(job['description'])}), flush=True)
            except Exception as exc:
                print(source + ': ' + str(exc)[:300], flush=True)
            finally:
                page.close()
        browser.close()


if __name__ == '__main__':
    model_check() if '--model' in sys.argv else search_check()
