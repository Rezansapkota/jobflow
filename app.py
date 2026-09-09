"""Local job application workspace. Run: python app.py"""
import json
import os
import re
import secrets
import sys
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from documents import docx, plain_text
import runtime
BUILD_ID = runtime.build_id()

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
DB = DATA / 'workspace.db'
TOKEN = secrets.token_urlsafe(32)
RUN_LOCK = threading.Lock()
STOP = threading.Event()
AI_LOCK = threading.Lock()
MUTATION_LOCK = threading.Lock()
STATUSES = {'saved', 'ready', 'needs_input', 'submitted', 'uncertain', 'rejected', 'interview'}
DEFAULT_PROFILE = dict(title='Default profile', linkedin_url='', seek_url='', name='', email='', phone='', location='', headline='', summary='', skills='', experience='', education='', certifications='', roles='', search_location='', work_rights='', constraints='', answers={})


@contextmanager
def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init():
    with connect() as c:
        c.executescript('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT); CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, url TEXT UNIQUE, payload TEXT NOT NULL);')
        c.execute('CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        c.execute('CREATE TABLE IF NOT EXISTS certificates (id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, payload TEXT NOT NULL)')
        for row in c.execute('SELECT payload FROM certificates').fetchall():
            certificate = json.loads(row[0])
            if certificate['status'] == 'reading':
                certificate.update(status='needs_review', note='Reading was interrupted. Retry extraction or enter details manually.')
                c.execute('UPDATE certificates SET payload=? WHERE id=?', (json.dumps(certificate), certificate['id']))
        if not c.execute('SELECT 1 FROM profiles LIMIT 1').fetchone():
            legacy = c.execute("SELECT value FROM settings WHERE key='profile'").fetchone()
            initial = {**DEFAULT_PROFILE, **(json.loads(legacy[0]) if legacy else {}), 'id': 'default'}
            c.execute('INSERT INTO profiles VALUES (?,?)', ('default', json.dumps(initial)))
            c.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", ('default',))
        # A crash after clicking Submit must never cause an automatic retry.
        for row in c.execute('SELECT * FROM jobs').fetchall():
            job = json.loads(row['payload'])
            if job.get('status') == 'running':
                job.update(status='uncertain', note='Previous run was interrupted. Check the site before retrying.')
                c.execute('UPDATE jobs SET payload=? WHERE id=?', (json.dumps(job), job['id']))
        row = c.execute("SELECT value FROM settings WHERE key='automation'").fetchone()
        if row:
            run = json.loads(row[0])
            if run.get('status') == 'running':
                run['status'] = 'interrupted'
                run.setdefault('events', []).append({'time': datetime.now(timezone.utc).isoformat(), 'message': 'Server restarted. Run was interrupted; check uncertain applications before retrying.'})
                c.execute("UPDATE settings SET value=? WHERE key='automation'", (json.dumps(run),))


def profile(pid=None):
    with connect() as c:
        if pid is None:
            active = c.execute("SELECT value FROM settings WHERE key='active_profile'").fetchone()
            pid = active[0] if active else 'default'
        row = c.execute('SELECT payload FROM profiles WHERE id=?', (pid,)).fetchone()
    if not row:
        raise ValueError('Profile not found.')
    return {**DEFAULT_PROFILE, **json.loads(row[0]), 'id': pid}


def profiles():
    with connect() as c:
        return [{'id': r['id'], 'title': json.loads(r['payload']).get('title', 'Default profile')} for r in c.execute('SELECT * FROM profiles ORDER BY rowid')]


def require_profile(job, p):
    if job.get('profile_id', 'default') != p['id']:
        raise ValueError('This job belongs to a different profile. Switch profiles first.')


def invalidate_profile(pid):
    for job in jobs():
        if job.get('profile_id', 'default') == pid and job['status'] in ('ready', 'needs_input', 'saved'):
            job.update(status='saved', resume=None, cover_letter=None, assessment=None, profile_snapshot=None, certificate_ids=[], note='Profile or certificates updated. Prepare fresh documents.')
            save_job(job)


def application_profile():
    from certificates import effective_profile
    return effective_profile(profile())


def jobs():
    with connect() as c:
        return [json.loads(r[0]) for r in c.execute('SELECT payload FROM jobs ORDER BY rowid DESC')]


def get_job(jid):
    with connect() as c:
        row = c.execute('SELECT payload FROM jobs WHERE id=?', (jid,)).fetchone()
    if not row:
        raise ValueError('Job not found.')
    return json.loads(row[0])


def save_job(job):
    with connect() as c:
        c.execute('INSERT INTO jobs VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (job['id'], job['url'], json.dumps(job)))


def validate_url(url):
    p = urlparse(url.strip())
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Use an HTTPS LinkedIn or SEEK job link.')
    if (host == 'linkedin.com' or re.fullmatch(r'[a-z]{2,3}\.linkedin\.com', host)) and re.fullmatch(r'/jobs/view/(?:[^/]*-)?\d+/?', p.path):
        job_id = re.search(r'(\d+)/?$', p.path)[1]
        return f'https://www.linkedin.com/jobs/view/{job_id}/', 'LinkedIn'
    if host in ('seek.com.au', 'www.seek.com.au', 'au.seek.com') and re.fullmatch(r'/job/\d+/?', p.path):
        return f'https://www.seek.com.au{p.path.rstrip("/")}', 'SEEK'
    raise ValueError('Paste a LinkedIn /jobs/view/… or SEEK /job/… link.')


def words(text):
    return set(re.findall(r'[a-z0-9]+(?:[+#.][a-z0-9+#]*)?', text.lower()))


def tailor(p, job, ai_draft=None):
    """Extractive tailoring: keep facts verbatim; reorder skills, never invent claims."""
    description = job['description'].lower()
    skills = [s.strip() for s in re.split(r'[,\n]', p['skills']) if s.strip()]
    matched = [s for s in skills if re.search(r'(?<!\w)' + re.escape(s.lower()) + r'(?!\w)', description)]
    ordered = matched + [s for s in skills if s not in matched]
    if ai_draft:
        ordered = ai_draft['skills']
    lines = [p['name']] + [x for x in (p['email'], p['phone'], p['location']) if x]
    if p['headline']:
        lines += ['', p['headline']]
    for heading, value in [('PROFESSIONAL SUMMARY', ai_draft['summary'] if ai_draft else p['summary']), ('SKILLS', ', '.join(ordered)), ('WORK EXPERIENCE', p['experience']), ('EDUCATION', p['education']), ('CERTIFICATIONS', p.get('certifications', ''))]:
        if value.strip():
            lines += ['', heading, value.strip()]
    # Chronology and attribution in the source experience remain intact.
    return {'text': '\n'.join(lines), 'matched': matched, 'score': round(100 * len(matched) / len(skills)) if skills else 0,
            'engine': 'qwen3:8b' if ai_draft else 'basic',
            'format': 'ats-docx-v1',
            'note': ('Written locally with Qwen. Review the generated summary for accuracy. ' if ai_draft else 'Skill overlap, not a qualification score. ') + 'Single-column DOCX with standard headings and selectable text. Experience and education are preserved verbatim.'}


def prepare_ai(ids, p):
    from local_ai import rewrite, cover_letter
    from certificates import select_for_job
    try:
        for jid in ids:
            job = get_job(jid)
            try:
                draft = rewrite(p, job)
                letter = cover_letter(p, job)
                job.update(approved_documents=None, resume=tailor(p, job, draft), cover_letter=letter, profile_snapshot=p, certificate_ids=select_for_job(p, job), status='ready', note='Qwen resume and cover letter ready. Review before applying.')
            except Exception as exc:
                job['note'] = str(exc) if isinstance(exc, ValueError) else 'Local tailoring failed. Try again or choose Basic tailoring.'
            save_job(job)
    finally:
        AI_LOCK.release()


def set_status(jid, status, note):
    job = get_job(jid)
    job.update(status=status, note=note, updated=datetime.now(timezone.utc).isoformat())
    save_job(job)


def write_documents(job):
    resume = DATA / f'{job["id"]}.docx'
    resume.write_bytes(docx(job['resume']['text']))
    letter = None
    if job.get('cover_letter'):
        letter = DATA / f'{job["id"]}-cover-letter.docx'
        letter.write_bytes(docx(job['cover_letter'], kind='cover_letter'))
    return resume, letter


def run_queue(ids, submit):
    try:
        from browser_agent import BrowserAgent
        p = profile()
        from accounts import browser_data, prepare
        with BrowserAgent(browser_data(p), STOP) as agent:
            if submit:
                prepare(agent, p, list(dict.fromkeys(get_job(jid)['source'] for jid in ids)))
            for jid in ids:
                if STOP.is_set():
                    break
                job = get_job(jid)
                if job['status'] != 'ready':
                    continue
                if submit:
                    from review import require_approval
                    require_approval(job)
                set_status(jid, 'running', 'Opening application in the agent browser…')
                try:
                    resume, letter = write_documents(job)
                    agent.progress = lambda note: set_status(jid, 'running', note)
                    status, note = agent.apply(job, job.get('profile_snapshot') or p, resume, submit, letter)
                    set_status(jid, status, note)
                except Exception as exc:
                    uncertain = getattr(agent, 'submission_possible', False)
                    set_status(jid, 'uncertain' if uncertain else 'needs_input', f'Browser stopped: {type(exc).__name__}. ' + ('Check the site before retrying.' if uncertain else 'No submission was attempted. Reopen the job to continue.'))
    except Exception as exc:
        for jid in ids:
            if get_job(jid)['status'] in ('ready', 'running'):
                set_status(jid, 'needs_input', f'Browser or account setup stopped: {str(exc)[:250]}')
    finally:
        RUN_LOCK.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, content_type='application/json', filename=None):
        raw = json.dumps(data).encode() if content_type == 'application/json' else data
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(raw)

    def allowed_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def do_GET(self):
        if not self.allowed_host():
            return self.send(403, {'error': 'Invalid host'})
        path = urlparse(self.path).path
        if path == '/api/health':
            return self.send(200, {'app': 'jobflow', 'build': BUILD_ID})
        if path == '/api/state':
            p = profile()
            from certificates import rows, effective_profile
            return self.send(200, {'profile': p, 'profiles': profiles(), 'certificates': rows(p['id']), 'combined_certifications': effective_profile(p)['certifications'], 'jobs': [{**j, 'review_token': __import__('review').fingerprint(j), 'documents_approved': __import__('review').approved(j)} for j in jobs() if j.get('profile_id', 'default') == p['id']], 'running': RUN_LOCK.locked(), 'preparing': AI_LOCK.locked(), 'token': TOKEN, 'account_pending': __import__('accounts').pending(), 'connection_note': __import__('accounts').connection_note(p['id'])})
        if path.startswith('/api/certificates/file/'):
            try:
                from certificates import get, file_path, ALLOWED
                record = get(path.rsplit('/', 1)[1], profile()['id'])
                return self.send(200, file_path(record).read_bytes(), ALLOWED[record['extension']], 'certificate' + record['extension'])
            except (ValueError, OSError) as exc:
                return self.send(404, {'error': str(exc)})
        if path == '/api/ai':
            from local_ai import status
            return self.send(200, status())
        if path == '/api/automation':
            from automation import current
            return self.send(200, current())
        if path.startswith('/api/cover-letter/'):
            try:
                job = get_job(path.rsplit('/', 1)[1])
                if not job.get('cover_letter'):
                    raise ValueError('Prepare a cover letter with Local Qwen AI first.')
                return self.send(200, docx(job['cover_letter'], kind='cover_letter'), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'cover-letter.docx')
            except ValueError as exc:
                return self.send(404, {'error': str(exc)})
        if path.startswith('/api/resume/'):
            try:
                job = get_job(path.rsplit('/', 1)[1])
                if not job.get('resume'):
                    raise ValueError('Prepare this resume first.')
                if parse_qs(urlparse(self.path).query).get('format') == ['txt']:
                    return self.send(200, plain_text(job['resume']['text']).encode('utf-8'), 'text/plain; charset=utf-8', 'resume.txt')
                return self.send(200, docx(job['resume']['text']), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'resume.docx')
            except ValueError as exc:
                return self.send(404, {'error': str(exc)})
        files = {'/accounts-ui.js': ('accounts-ui.js', 'text/javascript'), '/': ('index.html', 'text/html; charset=utf-8'), '/style.css': ('style.css', 'text/css'), '/ui.js': ('ui.js', 'text/javascript'), '/automation-ui.js': ('automation-ui.js', 'text/javascript'), '/profiles-ui.js': ('profiles-ui.js', 'text/javascript'), '/certificates-ui.js': ('certificates-ui.js', 'text/javascript')}
        if path in files:
            name, mime = files[path]
            return self.send(200, (ROOT / 'static' / name).read_bytes(), mime)
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        with MUTATION_LOCK:
            self.handle_post()

    def handle_post(self):
        if not self.allowed_host() or self.headers.get('X-Session-Token') != TOKEN:
            return self.send(403, {'error': 'Refresh the app and try again.'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            limit = 14_100_000 if urlparse(self.path).path == '/api/certificates/upload' else 300_000
            if not 0 < length <= limit:
                raise ValueError('Request is empty or too large.')
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError('Expected an object.')
            if urlparse(self.path).path == '/api/stop':
                STOP.set()
                return self.send(200, {'ok': True})
            if urlparse(self.path).path == '/api/accounts/confirm':
                from accounts import confirm
                confirm(body.get('id'), profile()['id'])
                return self.send(200, {'ok': True})
            if RUN_LOCK.locked():
                raise ValueError('Wait for the current browser run to finish before editing.')
            if AI_LOCK.locked():
                raise ValueError('Qwen is preparing resumes. Wait for it to finish before editing.')
            path = urlparse(self.path).path
            if path.startswith('/api/certificates/'):
                import certificates
                p = profile()
                if body.get('profile_id') != p['id']:
                    raise ValueError('Active profile changed. Select the intended profile before uploading.')
                if path in ('/api/certificates/upload', '/api/certificates/retry'):
                    record = certificates.receive(p['id'], body.get('filename', ''), body.get('data', '')) if path.endswith('/upload') else certificates.get(body.get('id'), p['id'])
                    if not AI_LOCK.acquire(blocking=False):
                        raise ValueError('Another reading operation is active.')
                    record.update(status='reading', note='Reading certificate locally…')
                    certificates.store(record)
                    threading.Thread(target=certificates.read_worker, args=(record,), daemon=True).start()
                elif path == '/api/certificates/save':
                    record = certificates.get(body.get('id'), p['id'])
                    for key in ('name', 'issuer', 'holder', 'issued_on', 'expires_on', 'keywords'):
                        record[key] = str(body.get(key, '')).strip()[:500]
                    record['enabled'] = body.get('enabled') is True
                    record['status'], record['note'] = certificates.validate_record(record, p, manual=True)
                    certificates.store(record)
                    invalidate_profile(p['id'])
                elif path == '/api/certificates/remove':
                    record = certificates.get(body.get('id'), p['id'])
                    # Keep file evidence for old submitted applications; detach from active profile.
                    record.update(enabled=False, status='removed', note='Removed from active certifications.')
                    certificates.store(record)
                    invalidate_profile(p['id'])
                else:
                    return self.send(404, {'error': 'Not found'})
            elif path == '/api/profiles/create':
                title = str(body.get('title', '')).strip()[:100]
                if not title:
                    raise ValueError('Give the profile a title, such as Rejan IT.')
                base = profile() if body.get('copy_current') is True else DEFAULT_PROFILE
                p = {**base, 'id': uuid.uuid4().hex, 'title': title}
                with connect() as c:
                    c.execute('INSERT INTO profiles VALUES (?,?)', (p['id'], json.dumps(p)))
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", (p['id'],))
            elif path == '/api/profiles/select':
                p = profile(str(body.get('id', '')))
                with connect() as c:
                    c.execute("INSERT OR REPLACE INTO settings VALUES ('active_profile', ?)", (p['id'],))
            elif path == '/api/profile':
                previous = profile()
                if body.get('id') and body['id'] != previous['id']:
                    raise ValueError('Active profile changed. Refresh before saving.')
                p = {k: str(body.get(k, '')).strip()[:30000] for k in DEFAULT_PROFILE if k != 'answers'}
                p.update(id=previous['id'], title=(p['title'] or previous['title'])[:100])
                answers = body.get('answers', {})
                if not isinstance(answers, dict) or any(not isinstance(v, str) for v in answers.values()):
                    raise ValueError('Saved answers must be a JSON object of question: answer strings.')
                p['answers'] = answers
                from accounts import account_url
                for source in ('LinkedIn', 'SEEK'):
                    account_url(p, source)
                with connect() as c:
                    c.execute('UPDATE profiles SET payload=? WHERE id=?', (json.dumps(p), p['id']))
                document_fields = set(DEFAULT_PROFILE) - {'title', 'linkedin_url', 'seek_url'}
                if any(p.get(key) != previous.get(key) for key in document_fields):
                    invalidate_profile(p['id'])
            elif path == '/api/jobs':
                url, source = validate_url(str(body.get('url', '')))
                title, company, description = [str(body.get(k, '')).strip() for k in ('title', 'company', 'description')]
                if not title or not company or len(description) < 40:
                    raise ValueError('Add a title, company and a job description of at least 40 characters.')
                if any(j['url'] == url for j in jobs()):
                    raise ValueError('This job is already in your workspace.')
                save_job(dict(id=uuid.uuid4().hex, profile_id=profile()['id'], url=url, source=source, title=title, company=company, description=description, status='saved', note='', resume=None))
            elif path == '/api/prepare':
                p = application_profile()
                if not p['name'] or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', p['email']) or not p['experience']:
                    raise ValueError('Save your name, valid email and real experience in My profile first.')
                selected = body.get('ids', [])
                if not isinstance(selected, list) or not 1 <= len(selected) <= 10:
                    raise ValueError('Choose between 1 and 10 jobs to prepare.')
                selected = list(dict.fromkeys(selected))
                for jid in selected:
                    require_profile(get_job(jid), p)
                selected = [jid for jid in selected if get_job(jid)['status'] not in ('submitted', 'uncertain', 'interview', 'rejected')]
                if body.get('engine') == 'ollama':
                    if not selected:
                        raise ValueError('No eligible jobs selected.')
                    if not AI_LOCK.acquire(blocking=False):
                        raise ValueError('Qwen is already preparing resumes.')
                    threading.Thread(target=prepare_ai, args=(selected, p), daemon=True).start()
                    return self.send(200, {'ok': True})
                for jid in selected:
                    job = get_job(jid)
                    if job['status'] in ('submitted', 'uncertain', 'interview', 'rejected'):
                        continue
                    from certificates import select_for_job
                    job.update(approved_documents=None, resume=tailor(p, job), profile_snapshot=p, certificate_ids=select_for_job(p, job), status='ready', note='Tailored resume ready.')
                    save_job(job)
            elif path == '/api/review/approve':
                from review import fingerprint
                job = get_job(body['id'])
                require_profile(job, profile())
                token = fingerprint(job)
                if job['status'] != 'ready' or not token or token != body.get('review_token'):
                    raise ValueError('Documents changed or are incomplete. Reopen the job and review both documents.')
                job.update(approved_documents=token, note='Documents approved. Select this job and run automatic submission when ready.')
                save_job(job)
            elif path == '/api/status':
                job = get_job(body['id'])
                require_profile(job, profile())
                if body.get('status') not in STATUSES - {'ready'}:
                    raise ValueError('Invalid status.')
                job.update(status=body['status'], note='Status updated by you.')
                save_job(job)
            elif path == '/api/accounts/connect':
                from accounts import account_url, connect_worker
                p = profile()
                source = body.get('source')
                account_url(p, source)
                if not RUN_LOCK.acquire(blocking=False):
                    raise ValueError('A browser run is already active.')
                STOP.clear()
                threading.Thread(target=connect_worker, args=(p, source), daemon=True).start()
            elif path == '/api/automation/start':
                from automation import validate_config, run
                p = application_profile()
                config = validate_config(p, body)
                from local_ai import status as ai_status
                if not ai_status()['available']:
                    raise ValueError('Start Ollama with qwen3:8b before combined search. Your saved jobs are unchanged.')
                if not RUN_LOCK.acquire(blocking=False):
                    raise ValueError('A browser run is already active.')
                STOP.clear()
                threading.Thread(target=run, args=(p, config), daemon=True).start()
            elif path == '/api/run':
                ids = list(dict.fromkeys(body.get('ids', [])))
                for jid in ids:
                    require_profile(get_job(jid), profile())
                if body.get('submit') is True:
                    from review import require_approval
                    for jid in ids:
                        require_approval(get_job(jid))
                if not ids or len(ids) > 10 or any(get_job(j)['status'] != 'ready' for j in ids):
                    raise ValueError('Choose between 1 and 10 prepared applications.')
                if not RUN_LOCK.acquire(blocking=False):
                    raise ValueError('A browser run is already active.')
                STOP.clear()
                threading.Thread(target=run_queue, args=(ids, body.get('submit') is True), daemon=True).start()
            else:
                return self.send(404, {'error': 'Not found'})
            self.send(200, {'ok': True})
        except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as exc:
            self.send(400, {'error': str(exc)})
        except Exception:
            self.send(500, {'error': 'Unexpected error. Your saved data remains in data/workspace.db.'})


if __name__ == '__main__':
    # Worker modules import app; share this exact module's locks and stop event.
    sys.modules['app'] = sys.modules[__name__]
    init()
    port = int(os.environ.get('PORT', '8768'))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    runtime.MANIFEST.write_text(json.dumps({'port': port, 'build': BUILD_ID}))
    print(f'Jobflow is running at http://127.0.0.1:{port}', flush=True)
    server.serve_forever()
