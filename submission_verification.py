"""Read-only reconciliation of uncertain outcomes, without application retries."""
from datetime import datetime, timezone


def worker(ids, profile):
    import app
    try:
        recheck(ids, profile)
    finally:
        app.RUN_LOCK.release()


def recheck(ids, profile):
    import app
    from browser_agent import BrowserAgent
    from accounts import browser_data
    pending = [jid for jid in ids if app.get_job(jid)['status'] == 'uncertain']
    if not pending or app.STOP.is_set():
        return
    def record(jid, confirmed, evidence):
        job = app.get_job(jid)
        if job['status'] != 'uncertain':
            return
        job['submission_check'] = {'checked_at': datetime.now(timezone.utc).isoformat(),
                                   'confirmed': confirmed, 'evidence': evidence, 'url': job['url']}
        job.update(status='submitted' if confirmed else 'uncertain',
                   note=('Submission verified automatically. ' if confirmed else 'Automatically checked; submission remains unverified. ') + evidence)
        app.save_job(job)
    try:
        with BrowserAgent(browser_data(profile), app.STOP, headless=True) as agent:
            for jid in pending:
                if app.STOP.is_set():
                    break
                job = app.get_job(jid)
                app.require_profile(job, profile)
                confirmed, evidence = agent.verify_submission(job)
                record(jid, confirmed, evidence)
    except Exception as exc:
        for jid in pending:
            record(jid, False, 'The status check could not finish: ' + type(exc).__name__)
