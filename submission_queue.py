"""Submit explicitly approved jobs once, serially through the shared browser lock."""
import threading


def decide(job_id, action, token=None, submit=False):
    """Called with the application's mutation lock held."""
    import app
    from review import fingerprint
    job = app.get_job(job_id)
    app.require_profile(job, app.profile())
    if job.get('submission_in_progress') or job['status'] in ('running', 'submitted', 'uncertain', 'interview'):
        raise ValueError('This application is active or already attempted. Review its outcome first.')
    if action == 'reject':
        if app.AI_LOCK.locked() or (app.RUN_LOCK.locked() and job['status'] != 'ready'):
            raise ValueError('Wait for document preparation to finish before rejecting this job.')
        job.update(status='rejected', user_rejected=True, approved_documents=None, submission_requested=None,
                   note='Rejected by you. This job will not be submitted.')
        app.save_job(job)
        return
    if action != 'approve':
        raise ValueError('Choose Approve or Reject.')
    current_token = fingerprint(job)
    if job['status'] != 'ready' or not current_token or current_token != token:
        raise ValueError('Documents changed or are incomplete. Review the current resume and cover letter first.')
    if app.AI_LOCK.locked():
        raise ValueError('Wait for document preparation to finish before approving.')
    if submit and app.STOP.is_set() and app.RUN_LOCK.locked():
        raise ValueError('The current run is stopping. Approve again once it has stopped.')
    already_queued = job.get('submission_requested') == current_token
    job.update(approved_documents=current_token, user_rejected=False,
               note='Approved and queued for automatic submission.' if submit else 'Documents approved. Choose Automatic submission to apply.')
    if submit:
        job['submission_requested'] = current_token
    app.save_job(job)
    if submit and not already_queued:
        if not app.RUN_LOCK.locked():
            app.STOP.clear()
        threading.Thread(target=submit_when_idle, args=(job_id, current_token), daemon=True).start()


def submit_when_idle(job_id, token):
    import app
    from review import fingerprint, approved
    while not app.STOP.is_set():
        with app.MUTATION_LOCK:
            job = app.get_job(job_id)
            if job.get('submission_requested') != token:
                return
            if job['status'] != 'ready' or fingerprint(job) != token or not approved(job):
                job.update(submission_requested=None, note='Queued submission cancelled because the job or documents changed.')
                app.save_job(job)
                return
            if not app.AI_LOCK.locked() and app.RUN_LOCK.acquire(blocking=False):
                job.update(submission_requested=None, submission_in_progress=True, note='Starting approved automatic application.')
                try:
                    app.save_job(job)
                except Exception:
                    app.RUN_LOCK.release()
                    raise
                break
        app.STOP.wait(0.25)
    else:
        return
    try:
        app.run_queue([job_id], True, job.get('profile_id', 'default'))
    finally:
        with app.MUTATION_LOCK:
            job = app.get_job(job_id)
            job['submission_in_progress'] = False
            app.save_job(job)


def cancel_pending():
    import app
    for job in app.jobs():
        if job.get('submission_requested'):
            job.update(submission_requested=None, note='Automatic submission cancelled by Stop. Approve again to queue it.')
            app.save_job(job)
