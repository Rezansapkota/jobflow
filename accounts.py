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


def login_credentials(body):
    username, password = body.get('username', ''), body.get('password', '')
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError('Enter a valid login ID and password.')
    if not username and not password:
        return None
    if not username.strip() or not password or len(username) > 320 or len(password) > 1024:
        raise ValueError('Enter both your login ID and password.')
    return {'username': username.strip(), 'password': password}


def fill_login(page, source, credentials):
    """Only fill recognised controls on the selected site's HTTPS origin."""
    import re
    hosts = ('linkedin.com', 'www.linkedin.com') if source == 'LinkedIn' else ('seek.com.au', 'www.seek.com.au', 'au.seek.com')
    def trusted():
        parsed = urlparse(page.url)
        return parsed.scheme == 'https' and parsed.hostname in hosts and parsed.port in (None, 443)
    if not trusted():
        return False
    user = page.locator('input[name="session_key"]:visible, input[autocomplete="username"]:visible, input[type="email"]:visible, input[name="username"]:visible')
    if user.count() != 1:
        return False
    user.fill(credentials['username'])
    password = page.locator('input[type="password"]:visible')
    if not password.count():
        next_button = page.get_by_role('button', name=re.compile(r'^(continue|next|continue with email)$', re.I))
        if next_button.count() != 1 or not trusted():
            return False
        next_button.click()
        try:
            password.wait_for(state='visible', timeout=8000)
        except Exception:
            return False
    if not trusted() or password.count() != 1:
        return False
    password.fill(credentials['password'])
    submit = page.get_by_role('button', name=re.compile(r'^(sign in|log in|login)$', re.I))
    if submit.count() != 1 or not trusted():
        return False
    submit.click()
    return True


def connect_worker(profile, source, credentials=None):
    import app
    from browser_agent import BrowserAgent
    CONNECTION_NOTE[profile['id']] = f'Opening {source} in Chrome...'
    try:
        with BrowserAgent(browser_data(profile), app.STOP) as agent:
            prepare(agent, profile, [source], credentials)
        CONNECTION_NOTE[profile['id']] = f'{source} account confirmed. Start combined search when ready.'
        from submission_verification import recheck
        uncertain = [job['id'] for job in app.jobs() if job.get('profile_id', 'default') == profile['id']
                     and job['source'] == source and job['status'] == 'uncertain'][:10]
        recheck(uncertain, profile)
    except Exception as exc:
        CONNECTION_NOTE[profile['id']] = f'{source} connection stopped. Retry login or complete sign-in in the browser.'
    finally:
        if credentials:
            credentials.clear()
        app.RUN_LOCK.release()


def confirm(token, profile_id):
    with LOCK:
        if not PENDING or PENDING['id'] != token or PENDING['profile_id'] != profile_id:
            raise ValueError('This sign-in request is no longer active.')
        CONFIRMED.set()


def prepare(agent, profile, sources, credentials=None):
    global PENDING
    from discovery import challenged
    for source in sources:
        if agent.stopped():
            raise ValueError('Account setup stopped.')
        page = agent.context.new_page()
        try:
            target = ('https://www.linkedin.com/login' if source == 'LinkedIn' else DEFAULTS['SEEK']) if credentials else account_url(profile, source)
            page.goto(target, wait_until='domcontentloaded', timeout=45000)
            if credentials:
                try:
                    page.wait_for_timeout(1500)
                    filled = fill_login(page, source, credentials)
                    CONNECTION_NOTE[profile['id']] = ('Login submitted. Complete any verification in Chrome, then confirm Account ready.' if filled else 'Complete login in Chrome: the site requires verification or a different sign-in step.')
                except Exception:
                    CONNECTION_NOTE[profile['id']] = 'Complete login in Chrome. Automatic login could not finish.'
                finally:
                    credentials.clear()
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
