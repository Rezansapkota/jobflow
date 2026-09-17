"""Background, profile-scoped resume analysis using the existing local tailor."""
import copy
import json
import re
import threading
import time
import uuid

from tailoring import confirmed_fact, focused_profile, relevant_fact, requirements_text, sections

FIELDS = ('name', 'email', 'phone', 'location', 'headline', 'summary', 'skills', 'experience', 'education', 'certifications')
TASKS = {}
LOCK = threading.Lock()


def normalized(text):
    return ' '.join(text.casefold().split())


def application_context(profile, candidate):
    context = {key: str(profile.get(key, '') or '') for key in ('roles', 'search_location', 'work_rights', 'constraints')}
    context['location'] = candidate.get('location', '')
    context['saved_application_answers'] = json.dumps(profile.get('answers', {}), ensure_ascii=False)
    return context


def analysis(profile, job, engine, preferences=None):
    """Every displayed requirement and piece of evidence must be traceable."""
    description = requirements_text(job['description'])
    facts = {key: profile[key] for key in ('headline', 'summary', 'skills', 'experience', 'education', 'certifications')}
    facts.update(profile.get('_application_context', {}))
    if engine == 'ollama':
        from local_ai import structured
        # Fit analysis needs the full advertisement, including salary/roster
        # details that may appear alongside benefits or company information.
        description = job['description']
        item = {'type': 'object', 'properties': {
            'requirement': {'type': 'string'},
            'evidence': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 3},
            'status': {'type': 'string', 'enum': ['evidenced', 'partial', 'not_found']},
            'note': {'type': 'string'},
        }, 'required': ['requirement', 'evidence', 'status', 'note'], 'additionalProperties': False}
        result = structured(
            'Read the complete advertisement. Distinguish actual applicant requirements and working conditions '
            'from company marketing or benefits; do not treat company capabilities as applicant skills. '
            'Compare the main responsibilities, essential and preferred criteria, tools, qualifications, '
            'experience, and working conditions in the job against the candidate facts. Return up to 20 '
            'distinct requirements, retaining mandatory/preferred conditions. Each requirement must be '
            'an EXACT quotation from the description. Evidence must be short EXACT quotations from '
            'candidate fields, never from the job. Use evidenced only for explicit supporting facts; '
            'partial for transferable or incomplete evidence; not_found for absent or uncertain evidence. '
            'An expired credential does not satisfy a current requirement. Do not infer qualifications '
            'from generic duties or count negated/conditional facts as evidence. Briefly explain gaps '
            'and what factual information the applicant should verify. Check work rights, location, availability, '
            'salary or roster constraints and saved screening answers when the job specifies them. A target role '
            'is a preference, not evidence of experience; a home address does not prove willingness to relocate. '
            'Respect limitations in application answers. No scores or hiring predictions.',
            {'candidate': facts, 'job': {**job, 'description': description}, 'writing_preferences': preferences or {}},
            {'type': 'object', 'properties': {'requirements': {'type': 'array', 'items': item, 'minItems': 1, 'maxItems': 20}},
             'required': ['requirements'], 'additionalProperties': False}, max_tokens=3200)
        rows = result.get('requirements')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
            raise ValueError('The requirement analysis was incomplete. Try again or choose Basic matching.')
        verified = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('Invalid requirement analysis. Try again.')
            requirement, evidence = row.get('requirement'), row.get('evidence')
            status, note = row.get('status'), row.get('note')
            if (not isinstance(requirement, str) or not 8 <= len(requirement) <= 1200
                    or normalized(requirement) not in normalized(description)
                    or not isinstance(evidence, list) or len(evidence) > 3
                    or status not in ('evidenced', 'partial', 'not_found')
                    or not isinstance(note, str) or len(note) > 1500):
                raise ValueError('The analysis could not be traced to the job description. Try again.')
            # Keep the surrounding source line so a short quote cannot hide
            # "not yet obtained", expiry dates or other credential conditions.
            supported = []
            for quote in evidence:
                if not isinstance(quote, str) or not quote.strip():
                    continue
                for value in facts.values():
                    context = next((line.strip() for line in value.splitlines()
                                    if normalized(quote) in normalized(line) and confirmed_fact(line)), None)
                    if context:
                        supported.append(context)
                        break
            if len(supported) != len(evidence) or (status != 'not_found' and not supported):
                status, supported = 'not_found', []
                note = 'The proposed evidence could not be verified. Check this requirement against your real experience.'
            verified.append({'requirement': requirement, 'evidence': supported, 'status': status, 'note': note})
        return verified

    # Basic mode reports wording overlap, never claims that a qualification is met.
    lines = [line.strip(' \t-*•') for line in re.split(r'\n+|(?<=[.!?])\s+', description)]
    requirements = list(dict.fromkeys(line for line in lines if len(line) >= 12))[:20]
    evidence_lines = [line.strip() for key, value in facts.items()
                      for line in (re.split(r'\n|,', value) if key == 'skills' else value.splitlines()) if line.strip()]
    return [{'requirement': line,
             'evidence': [fact for fact in evidence_lines if confirmed_fact(fact) and relevant_fact(fact, {'description': line})][:3],
             'status': 'review',
             'note': 'Wording overlap only. Verify the full requirement, dates and conditions.'}
            for line in requirements]


def basic_draft(profile, job):
    """Extract relevant source facts; leave prose and achievements uninvented."""
    from local_ai import factual_summary
    focused_job = {**job, 'description': requirements_text(job['description'])}
    selection = {key: [i for i, line in enumerate(lines) if confirmed_fact(line) and relevant_fact(line, focused_job)]
                 for key, lines in sections(profile).items()}
    # Keep issuer/date/condition lines attached to selected credentials.
    for key in ('education', 'certifications'):
        for i, line in enumerate(sections(profile)[key]):
            if i - 1 in selection[key] and re.match(r'^\s*(issued|issuer|expiry|expires|awarded|valid|condition|\d{4})\b', line, re.I):
                selection[key].append(i)
    selection['headline'] = bool(profile['headline'] and relevant_fact(profile['headline'], focused_job))
    skills = list(dict.fromkeys(skill.strip() for skill in re.split(r'[,\n]', profile['skills'])
                               if skill.strip() and confirmed_fact(skill) and relevant_fact(skill, focused_job)))
    draft = {'summary': '', 'skills': skills, 'selection': selection, 'target_job': job, 'job_priorities': []}
    draft['summary'] = factual_summary(focused_profile(profile, draft))
    return draft


def generate(profile, job, engine, progress=lambda message: None, preferences=None):
    import app
    from local_ai import rewrite, resume_preferences, MODEL
    settings = resume_preferences(preferences)
    progress('Analyzing job requirements and checking your evidence…')
    requirements = analysis(profile, job, engine, settings)
    progress('Selecting relevant facts and tailoring your summary…')
    draft = rewrite(profile, job, preferences=settings) if engine == 'ollama' else basic_draft(profile, job)
    draft['skills'] = draft['skills'][:settings['max_skills']]
    focused = focused_profile(profile, draft)
    resume = app.tailor(profile, job, draft)
    warnings = []
    if engine == 'basic':
        warnings.append('Basic matching applies the skills limit. Writing style, length and emphasis require Local AI.')
    if not focused['experience'].strip():
        warnings.append('No relevant work history was selected. Add genuine transferable duties to your source information before using this resume.')
    if not draft['skills']:
        warnings.append('No relevant saved skills were found. Add relevant skills only if you actually have them.')
    if not profile['email'].strip() and not profile['phone'].strip():
        warnings.append('Add an email address or phone number so employers can contact you.')
    if not re.search(r'\d', focused['experience']):
        warnings.append('Check that each role includes its employer, title and dates. Add verified achievements where available.')
    return {'text': resume['text'], 'requirements': requirements, 'skills': draft['skills'],
            'warnings': warnings, 'engine': engine, 'model': MODEL if engine == 'ollama' else None,
            'preferences': settings,
            'reviewed_inputs': ['Job duties and selection criteria', 'Profile summary, skills and work history',
                                'Education and certifications', 'Location, target roles and search area',
                                'Saved work rights, availability constraints and application answers'],
            'note': 'Review the summary and requirement analysis for accuracy. Missing requirements are not added to your resume.',
            'ats': ['Single column with standard section headings', 'Selectable text in PDF and Word',
                    'Original employers, role titles and dates retained for selected experience',
                    'No tables, images, text boxes or keyword stuffing']}


def start(body, active_profile):
    import app
    from local_ai import resume_preferences
    settings = resume_preferences(body.get('preferences'))
    if body.get('profile_id') != active_profile['id']:
        raise ValueError('The active profile changed. Reload the builder before tailoring.')
    engine = body.get('engine', 'ollama')
    if engine not in ('ollama', 'basic'):
        raise ValueError('Choose Local AI or Basic matching.')
    candidate = body.get('candidate')
    if not isinstance(candidate, dict) or any(not isinstance(candidate.get(key, ''), str) for key in FIELDS):
        raise ValueError('Resume fields must contain text.')
    candidate = {key: candidate.get(key, '').strip() for key in FIELDS}
    context = application_context(active_profile, candidate)
    title, description = body.get('title', ''), body.get('description', '')
    if not isinstance(title, str) or not isinstance(description, str) or not 40 <= len(description.strip()) <= 16000 or len(title) > 200:
        raise ValueError('Paste a job description between 40 and 16,000 characters and a title under 200 characters.')
    if sum(len(value) for value in candidate.values()) + len(description) + len(json.dumps(context)) > 22000:
        raise ValueError('The resume, saved application context and job description are too long. Keep their combined length under 22,000 characters.')
    if not candidate['name'] or not any(candidate[key] for key in ('experience', 'education', 'skills')):
        raise ValueError('Add your name and real experience, education or skills before tailoring.')
    if not requirements_text(description):
        raise ValueError('Add job duties and requirements, not only company information or benefits.')
    candidate['_application_context'] = context
    if app.RUN_LOCK.locked():
        raise ValueError('Wait for the current browser run to finish before tailoring.')
    if not app.AI_LOCK.acquire(blocking=False):
        raise ValueError('Another analysis is running. Wait for it to finish and try again.')
    task_id = uuid.uuid4().hex
    with LOCK:
        for old_id, task in list(TASKS.items()):
            if time.monotonic() - task['created'] > 3600 or (len(TASKS) >= 20 and task['status'] != 'running'):
                del TASKS[old_id]
        TASKS[task_id] = {'id': task_id, 'profile_id': active_profile['id'], 'created': time.monotonic(),
                          'status': 'running', 'message': 'Starting resume analysis…'}

    def update(**changes):
        with LOCK:
            TASKS[task_id].update(changes)

    def work():
        try:
            result = generate(candidate, {'title': title.strip(), 'description': description.strip()}, engine,
                              lambda message: update(message=message), preferences=settings)
            update(status='complete', result=result, message='Your tailored resume is ready to review.')
        except Exception as exc:
            update(status='error', message=str(exc) if isinstance(exc, ValueError) else 'Tailoring failed. Try again or choose Basic matching.')
        finally:
            app.AI_LOCK.release()

    try:
        threading.Thread(target=work, daemon=True).start()
    except Exception:
        app.AI_LOCK.release()
        with LOCK:
            del TASKS[task_id]
        raise
    return {'id': task_id, 'status': 'running'}


def get(task_id, profile_id):
    with LOCK:
        task = TASKS.get(task_id)
        if not task or task['profile_id'] != profile_id:
            raise ValueError('Analysis not found for this profile. Run the analysis again.')
        return copy.deepcopy({key: value for key, value in task.items() if key != 'created'})
