"""User-confirmed account access; passwords remain in the site's browser."""
import threading
import time
import uuid
from urllib.parse import urlparse

LOCK = threading.Lock()
CONFIRMED = threading.Event()
PENDING = None
CONNECTION_NOTE = {}
DEFAULTS = {'LinkedIn': 'https://www.linkedin.com/me/', 'SEEK': 'https://www.seek.com.au/profile/me'}
FIELDS = {'LinkedIn': 'linkedin_url', 'SEEK': 'seek_url'}


def account_url(profile, source):
    if source not in DEFAULTS:
        raise ValueError('Choose LinkedIn or SEEK.')
    value = profile.get(FIELDS[source], '').strip() or DEFAULTS[source]
    parsed = urlparse(value)
    hosts = ('linkedin.com', 'www.linkedin.com') if source == 'LinkedIn' else ('seek.com.au', 'www.seek.com.au', 'au.seek.com')
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError(f'Use an HTTPS {source} profile link on its official website.')
    return value


def browser_data(profile):
    import app
    # Database-generated IDs only; never use a URL or user-supplied title as a path.
    pid = profile.get('id', 'default')
    if pid != 'default' and (len(pid) != 32 or any(c not in '0123456789abcdef' for c in pid)):
        raise ValueError('Invalid career profile ID.')
    path = app.DATA / 'browser-profiles' / pid
    path.mkdir(parents=True, exist_ok=True)
    return path


def pending():
    with LOCK:
        return dict(PENDING) if PENDING else None


def connection_note(profile_id):
    return CONNECTION_NOTE.get(profile_id, '')


def connect_worker(profile, source):
    import app
    from browser_agent import BrowserAgent
    CONNECTION_NOTE[profile['id']] = f'Opening {source} in Chrome...'
    try:
        with BrowserAgent(browser_data(profile), app.STOP) as agent:
            prepare(agent, profile, [source])
        CONNECTION_NOTE[profile['id']] = f'{source} account confirmed. Start combined search when ready.'
    except Exception as exc:
        CONNECTION_NOTE[profile['id']] = f'{source} connection stopped: {str(exc)[:250]}'
    finally:
        app.RUN_LOCK.release()


def confirm(token, profile_id):
    with LOCK:
        if not PENDING or PENDING['id'] != token or PENDING['profile_id'] != profile_id:
            raise ValueError('This sign-in request is no longer active.')
        CONFIRMED.set()


def prepare(agent, profile, sources):
    global PENDING
    from discovery import challenged
    for source in sources:
        if agent.stopped():
            raise ValueError('Account setup stopped.')
        page = agent.context.new_page()
        try:
            page.goto(account_url(profile, source), wait_until='domcontentloaded', timeout=45000)
            with LOCK:
                CONFIRMED.clear()
                PENDING = {'id': uuid.uuid4().hex, 'profile_id': profile.get('id', 'default'), 'source': source}
            agent.progress(f'Check the {source} account in the browser, sign in if needed, then click "Account ready — continue" in Jobflow. Waiting up to 5 minutes.')
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if agent.stopped() or page.is_closed():
                    raise ValueError('Account sign-in was stopped or its browser tab was closed.')
                if CONFIRMED.is_set():
                    if challenged(page) or urlparse(page.url).hostname not in (('linkedin.com', 'www.linkedin.com') if source == 'LinkedIn' else ('seek.com.au', 'www.seek.com.au', 'au.seek.com')):
                        CONFIRMED.clear()
                        agent.progress('Finish signing in on the job site before confirming the account.')
                    else:
                        agent.progress(f'{source} account confirmed. Browser session saved locally.')
                        break
                page.wait_for_timeout(250)
            else:
                raise ValueError('Account confirmation timed out. Start again when ready to sign in.')
        finally:
            with LOCK:
                PENDING = None
                CONFIRMED.clear()
            if not page.is_closed():
                page.close()
