"""Conservative browser assistant. No stealth, CAPTCHA bypass or inferred answers."""
import re
import time
import os
from pathlib import Path


class BrowserAgent:
    def __init__(self, data, stop=None):
        self.data = data
        self.progress = lambda note: None
        self.stop = stop

    def stopped(self):
        return self.stop is not None and self.stop.is_set()

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                str(self.data / 'chrome-browser'), channel='chrome', headless=False, viewport={'width': 1280, 'height': 900})
            self.context.set_default_timeout(6000)
        except Exception:
            self.playwright.stop()
            raise
        return self

    def __exit__(self, *args):
        self.context.close()
        self.playwright.stop()

    @staticmethod
    def confirmed(page):
        # Avoid matching "application submitted" in the underlying job description.
        return page.get_by_role('heading', name=re.compile(r'^(application (sent|submitted)|your application (was|has been) (sent|submitted)|you successfully applied|application complete)[.!]?$', re.I)).count() > 0

    def handoff(self, page, reason):
        # The user may submit while the agent is waiting in this visible window.
        self.submission_possible = True
        self.progress(reason + ' The browser stays open for up to 5 minutes.')
        # Keep the visible browser available for the user to log in or finish.
        for _ in range(150):
            if self.stopped():
                return 'needs_input', 'Run stopped. Check the site if you submitted manually.'
            if page.is_closed():
                return 'needs_input', reason + ' Browser was closed; update the status if you applied.'
            if self.confirmed(page):
                return 'submitted', 'Submission confirmation observed in the browser.'
            page.wait_for_timeout(2000)
        return 'needs_input', reason + ' Manual handoff timed out after 5 minutes. Check the site before retrying.'

    def apply(self, job, p, resume, submit, cover_letter=None):
        self.submission_possible = False
        try:
            return self._apply(job, p, resume, submit, cover_letter)
        finally:
            if getattr(self, 'application_page', None) and not self.application_page.is_closed():
                self.application_page.close()

    def _apply(self, job, p, resume, submit, cover_letter=None):
        if self.stopped():
            return 'needs_input', 'Run stopped before opening the application.'
        page = self.context.new_page()
        self.application_page = page
        from certificates import attachments
        certificate_files = attachments(job, p) if job.get('certificate_ids') else []
        page.goto(job['url'], wait_until='domcontentloaded', timeout=45000)
        page.wait_for_timeout(1500)
        if not submit:
            # Manual mode never clicks form controls or uploads files.
            return self.handoff(page, 'Manual mode: complete the application in the browser; your resume is in data/' + resume.name + '.')
        if page.locator('input[type=password]:visible').count() or re.search(r'/login|/checkpoint|/authwall', page.url):
            from discovery import wait_for_access
            wait_for_access(self, page, job['url'])
        if job['source'] == 'LinkedIn':
            button = page.get_by_role('button', name=re.compile(r'^Easy Apply(?:\s|$)', re.I)).first
        else:
            button = page.get_by_role('link', name=re.compile(r'^Apply(?: now)?$', re.I)).first
            if not button.count():
                button = page.get_by_role('button', name=re.compile(r'^Apply(?: now)?$', re.I)).first
        if not button.count():
            return self.handoff(page, 'No supported application entry found. Complete the application manually.')
        button.click()
        page.wait_for_timeout(1500)
        for _ in range(10):
            if self.stopped():
                return 'needs_input', 'Run stopped before submission.'
            from urllib.parse import urlparse
            host = urlparse(page.url).hostname or ''
            if host not in ('www.linkedin.com', 'linkedin.com', 'www.seek.com.au', 'seek.com.au') and not re.fullmatch(r'[a-z]{2,3}\.linkedin\.com', host):
                return self.handoff(page, 'Application moved to an external site. Complete it manually.')
            if page.locator('iframe[src*="captcha"]:visible, iframe[title*="challenge" i]:visible, input[type=password]:visible').count():
                return self.handoff(page, 'Login or verification needs your input.')
            dialogs = page.get_by_role('dialog').filter(visible=True)
            scope = dialogs.last if dialogs.count() else page.locator('main:visible')
            if not scope.count():
                return self.handoff(page, 'Application form could not be identified.')
            missing = self.fill(scope, p, resume, cover_letter, job.get('cover_letter', ''), certificate_files)
            if missing:
                return self.handoff(page, 'Please answer: ' + ', '.join(missing[:4]) + '.')
            if scope.locator('input:invalid:visible, textarea:invalid:visible, select:invalid:visible').count():
                return self.handoff(page, 'A field failed the site validation. Correct it in the browser before submitting.')
            final = scope.get_by_role('button', name=re.compile(r'^(Submit application|Send application)$', re.I))
            if final.count() == 1 and final.is_visible():
                if self.stopped():
                    return 'needs_input', 'Run stopped before submission.'
                # Record ambiguity before any network submission; the caller never retries it.
                self.submission_possible = True
                final.click()
                for _ in range(15):
                    if self.confirmed(page):
                        return 'submitted', 'Submission confirmation observed in the browser.'
                    page.wait_for_timeout(1000)
                return 'uncertain', 'Submit was clicked but confirmation was not recognised. Check the site before retrying.'
            next_button = scope.get_by_role('button', name=re.compile(r'^(Next|Continue|Review|Review application)$', re.I))
            if next_button.count() != 1 or not next_button.is_visible():
                return self.handoff(page, 'Next application step could not be identified. Complete it manually.')
            next_button.click()
            page.wait_for_timeout(1200)
        return self.handoff(page, 'Application exceeded 10 steps. Complete it manually.')

    @staticmethod
    def fill(scope, profile, resume, cover_letter=None, cover_text='', certificate_files=None):
        known = {'full name': profile['name'], 'name': profile['name'], 'email': profile['email'],
                 'email address': profile['email'], 'phone': profile['phone'], 'phone number': profile['phone'],
                 'mobile phone number': profile['phone']}
        known.update({k.strip().lower().rstrip(' *:'): v for k, v in profile['answers'].items()})
        for label in ('certifications', 'certifications held', 'list your certifications'):
            known.setdefault(label, profile.get('certifications', ''))
        missing = []
        fields = scope.locator('input, textarea, select')
        for field in fields.all():
            kind = field.get_attribute('type') or ''
            if kind in ('hidden', 'submit', 'button') or field.is_disabled():
                continue
            if kind != 'file' and not field.is_visible():
                continue
            label = field.evaluate("el => ((el.labels && Array.from(el.labels).map(l=>l.innerText).join(' ')) || el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.name || '').trim()")
            key = label.lower().rstrip(' *:')
            if kind == 'file':
                # Never mistake a cover letter or other document for a resume upload.
                if re.search(r'cover.?letter', key, re.I) and cover_letter:
                    field.set_input_files(str(cover_letter))
                elif re.search(r'resume|résumé|cv\b', key, re.I) and not re.search(r'cover.?letter', key, re.I):
                    field.set_input_files(str(resume))
                elif re.search(r'certificat|certificate|licen[cs]|qualification|training|supporting document|additional document', key, re.I):
                    from certificates import field_files
                    paths, error = field_files(certificate_files or [], key, field.get_attribute('accept') or '', field.get_attribute('multiple') is not None)
                    if paths:
                        field.set_input_files(paths)
                    else:
                        missing.append((label or 'Certificate upload') + ': ' + error)
                else:
                    missing.append(label or 'document upload')
            elif kind in ('checkbox', 'radio'):
                if kind == 'radio' and field.evaluate("el => !!el.name && Array.from(document.getElementsByName(el.name)).some(other => other.type === 'radio' && other.form === el.form && other.checked)"):
                    continue
                # Consent and declarations must be answered explicitly on the form.
                if not field.is_checked():
                    missing.append(label or 'selection / consent')
            elif cover_text and re.search(r'cover.?letter', key, re.I):
                field.fill(cover_text)
            elif field.input_value().strip():
                continue
            elif key in known and known[key]:
                if field.evaluate('el => el.tagName') == 'SELECT':
                    field.select_option(label=known[key])
                else:
                    field.fill(known[key])
            else:
                missing.append(label or 'unlabelled field')
        return missing
