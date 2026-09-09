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
    record = {'id': uuid.uuid4().hex, 'profile_id': profile.get('id', 'default'), 'profile_title': profile.get('title', 'Default profile'), 'status': 'running', 'config': config, 'found': 0, 'prepared': 0, 'attempted': 0, 'submitted': 0, 'events': []}
    def event(message):
        record['events'].append({'time': datetime.now(timezone.utc).isoformat(), 'message': message})
        record['events'] = record['events'][-100:]
        write(record)
    try:
        event('Starting browser discovery. Search preferences and profile are fixed for this run.')
        with BrowserAgent(app.DATA, app.STOP) as agent:
            agent.progress = event
            seen = {job['url'] for job in app.jobs()}
            for found in discover(agent, profile, config, seen):
                if app.STOP.is_set():
                    break
                record['found'] += 1
                job = {**found, 'id': uuid.uuid4().hex, 'profile_id': profile.get('id', 'default'), 'status': 'saved', 'resume': None, 'note': 'Found by browser discovery.'}
                app.save_job(job)
                try:
                    event(f'Assessing {job["title"]} at {job["company"]}.')
                    assessment = assess(profile, found)
                    job['assessment'] = assessment
                    if not suitable(assessment, config['min_score']):
                        job.update(status='needs_input' if assessment['unknown_requirements'] else 'saved', note='Not selected for automatic application: ' + assessment['reason'])
                        app.save_job(job)
                        event(f'Skipped {job["title"]}: {assessment["reason"]}')
                        continue
                    if app.STOP.is_set():
                        break
                    event(f'Preparing resume and cover letter for {job["title"]}.')
                    draft = rewrite(profile, job)
                    if app.STOP.is_set():
                        break
                    letter = cover_letter(profile, job)
                    job.update(resume=app.tailor(profile, job, draft), cover_letter=letter, profile_snapshot=profile, status='ready', note='Matched by Qwen; resume and cover letter prepared locally.')
                    app.save_job(job)
                    record['prepared'] += 1
                    if app.STOP.is_set():
                        break
                    if config['submit'] and record['attempted'] < config['max_applications']:
                        record['attempted'] += 1
                        # Persist the uncertain boundary before any browser action.
                        app.set_status(job['id'], 'running', 'Automatic application in progress.')
                        event(f'Applying to {job["title"]} ({record["attempted"]}/{config["max_applications"]}).')
                        resume_path, letter_path = app.write_documents(job)
                        status, note = agent.apply(job, profile, resume_path, True, letter_path)
                        app.set_status(job['id'], status, note)
                        if status == 'submitted':
                            record['submitted'] += 1
                        event(f'{job["title"]}: {status}. {note}')
                        if record['attempted'] >= config['max_applications']:
                            event('Application limit reached for this run.')
                            break
                except Exception as exc:
                    latest = app.get_job(job['id'])
                    latest.update(status='uncertain' if latest['status'] == 'running' else 'needs_input', note=f'Automation stopped for this job: {str(exc)[:350]}')
                    app.save_job(latest)
                    event(f'{job["title"]}: {latest["note"]}')
                finally:
                    write(record)
        record['status'] = 'stopped' if app.STOP.is_set() else 'complete'
        event(f'Run {record["status"]}: {record["found"]} found, {record["prepared"]} prepared, {record["submitted"]} confirmed submitted.')
    except Exception as exc:
        record['status'] = 'failed'
        event('Run failed: ' + str(exc)[:350])
    finally:
        app.RUN_LOCK.release()
