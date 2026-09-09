"""One bounded search → assess → draft → apply run, sharing a signed-in browser."""
import json
import re
import uuid
from datetime import datetime, timezone


def validate_config(profile, body):
    for key in ('name', 'email', 'experience', 'skills', 'roles', 'search_location'):
        if not profile.get(key, '').strip():
            raise ValueError(f'Complete {key.replace("_", " ")} in My profile before starting discovery.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', profile['email']):
        raise ValueError('Save a valid email in My profile.')
    sources = body.get('sources', ['LinkedIn', 'SEEK'])
    if not isinstance(sources, list) or not sources or any(s not in ('LinkedIn', 'SEEK') for s in sources):
        raise ValueError('Select LinkedIn, SEEK, or both.')
    config = {'sources': list(dict.fromkeys(sources)), 'submit': body.get('submit') is True}
    for key, default, maximum in [('max_jobs', 10, 30), ('max_applications', 3, 10), ('pages', 1, 3), ('min_score', 80, 100)]:
        value = body.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f'{key.replace("_", " ")} must be between 1 and {maximum}.')
        config[key] = value
    config['roles'] = [r.strip() for r in re.split(r'[,\n]', profile['roles']) if r.strip()][:5]
    if not config['roles']:
        raise ValueError('Enter at least one target role.')
    if config['submit'] and not profile.get('work_rights', '').strip():
        raise ValueError('Enter your work rights in My profile before automatic submission.')
    return config


def suitable(assessment, minimum):
    return (assessment['score'] >= minimum and assessment['role_match'] and assessment['location_match']
            and not assessment['missing_requirements'] and not assessment['unknown_requirements'])


def current():
    import app
    with app.connect() as c:
        row = c.execute("SELECT value FROM settings WHERE key='automation'").fetchone()
    return json.loads(row[0]) if row else {'status': 'idle', 'events': []}


def write(run):
    import app
    with app.connect() as c:
        c.execute("INSERT OR REPLACE INTO settings VALUES ('automation', ?)", (json.dumps(run),))


def run(profile, config):
    import app
    from browser_agent import BrowserAgent
    from discovery import discover
    from local_ai import assess, rewrite, cover_letter
    from certificates import select_for_job
    from accounts import browser_data
    record = {'id': uuid.uuid4().hex, 'profile_id': profile.get('id', 'default'), 'profile_title': profile.get('title', 'Default profile'), 'status': 'running', 'stage': 'starting', 'config': config, 'found': 0, 'revisited': 0, 'prepared': 0, 'skipped': 0, 'errors': 0, 'attempted': 0, 'submitted': 0, 'events': [], 'source_issues': []}
    def event(message, stage=None):
        if stage:
            record['stage'] = stage
        elif message.startswith('Searching '):
            record['stage'] = 'searching'
        elif message.startswith('Sign in or complete'):
            record['stage'] = 'waiting_for_sign_in'
        record['events'].append({'time': datetime.now(timezone.utc).isoformat(), 'message': message})
        record['events'] = record['events'][-100:]
        write(record)
    def process(job):
        try:
            event(f'Checking suitability: {job["title"]}.', 'matching')
            assessment = assess(profile, job)
            job['assessment'] = assessment
            if not suitable(assessment, config['min_score']):
                record['skipped'] += 1
                job.update(status='needs_input' if assessment['unknown_requirements'] else 'saved', note='Not selected: ' + assessment['reason'])
                app.save_job(job)
                event(f'Skipped {job["title"]}: {assessment["reason"]}')
                return
            if app.STOP.is_set():
                return
            event(f'Writing resume: {job["title"]}.', 'writing_resume')
            draft = rewrite(profile, job)
            if app.STOP.is_set():
                return
            event(f'Writing cover letter: {job["title"]}.', 'writing_cover_letter')
            letter = cover_letter(profile, job)
            job.update(approved_documents=None, resume=app.tailor(profile, job, draft), cover_letter=letter, profile_snapshot=profile, certificate_ids=select_for_job(profile, job), status='ready', note='Resume and cover letter ready. Open this job to review and approve.')
            app.save_job(job)
            record['prepared'] += 1
            event(f'{job["title"]}: ready for your document review.', 'review_ready')
        except Exception as exc:
            record['errors'] += 1
            job.update(status='needs_input', note=f'Document preparation failed: {str(exc)[:350]}')
            app.save_job(job)
            event(f'{job["title"]}: {job["note"]}')
        finally:
            write(record)
    try:
        event('Starting combined search. No applications will be submitted during discovery.')
        existing = [j for j in app.jobs() if j.get('profile_id', 'default') == profile.get('id', 'default') and j['status'] in ('saved', 'needs_input', 'ready') and not (j.get('resume') and j.get('cover_letter'))]
        for job in existing[:config['max_jobs']]:
            if app.STOP.is_set():
                break
            record['revisited'] += 1
            process(job)
        if not app.STOP.is_set():
            with BrowserAgent(browser_data(profile), app.STOP) as agent:
                agent.progress = event
                agent.source_issues = []
                seen = {job['url'] for job in app.jobs()}
                stream = discover(agent, profile, config, seen)
                try:
                    for found in stream:
                        if app.STOP.is_set():
                            break
                        record['found'] += 1
                        job = {**found, 'id': uuid.uuid4().hex, 'profile_id': profile.get('id', 'default'), 'status': 'saved', 'resume': None, 'note': 'Found by combined search.'}
                        app.save_job(job)
                        process(job)
                finally:
                    if hasattr(stream, 'close'):
                        stream.close()
                    record['source_issues'] = agent.source_issues
        if app.STOP.is_set():
            record['status'] = 'stopped'
        elif record['errors'] or record['source_issues']:
            record['status'] = 'partial' if record['found'] or record['prepared'] else 'needs_input'
        else:
            record['status'] = 'complete' if record['found'] or record['revisited'] else 'no_results'
        event(f'Run {record["status"]}: {record["found"]} new jobs, {record["revisited"]} saved jobs checked, {record["prepared"]} document pairs prepared, {record["skipped"]} unsuitable, {record["errors"]} preparation errors.', record['status'])
        if not record['found']:
            event('No new listings were collected. Check the site messages below; existing pipeline jobs and their documents are preserved.')
    except Exception as exc:
        record['status'] = 'stopped' if app.STOP.is_set() else 'needs_input'
        message = str(exc)[:350]
        if 'closed' in message.lower():
            message = 'Chrome was closed. Keep the agent window open while searching, then start again. Saved jobs and documents are preserved.'
        event(message, record['status'])
    finally:
        app.RUN_LOCK.release()
