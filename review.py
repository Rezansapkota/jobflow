"""Approval is tied to the exact documents and application facts reviewed."""
import hashlib
import json


def fingerprint(job):
    if not job.get('resume') or not job.get('cover_letter'):
        return None
    data = {k: job.get(k) for k in ('url', 'resume', 'cover_letter', 'profile_snapshot', 'certificate_ids')}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def approved(job):
    return bool(fingerprint(job) and job.get('approved_documents') == fingerprint(job))


def require_approval(job):
    if not approved(job):
        raise ValueError('Open this job, review its resume and cover letter, and approve the documents before automatic submission.')
