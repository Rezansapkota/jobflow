"""Select saved facts without changing the master profile or employment attribution."""
import re

VERSION = 4


def confirmed_fact(text):
    return not re.search(r'\b(if applicable|if required|available upon request|to be confirmed|not yet obtained)\b', text, re.I)


def normalized_fact(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def requirements_text(description):
    """Exclude explicitly labelled employer/benefit sections from matching."""
    excluded = {'about us', 'about the company', 'about the employer', 'our company', 'benefits',
                'what we offer', 'equal opportunity', 'equal opportunities', 'why join us', 'who we are'}
    included = {'responsibilities', 'key responsibilities', 'your responsibilities', 'requirements',
                'qualifications', 'essential criteria', 'selection criteria', 'duties', 'about the role',
                'the role', 'about you', 'skills and experience', 'what you bring', 'what you will do',
                "what you'll do", "what we're looking for", 'what will you do', 'more about you'}
    headings = '|'.join(re.escape(value) for value in sorted(excluded | included, key=len, reverse=True))
    text = re.sub(r'(?i)\b(' + headings + r')\s*:\s*', r'\n\1:\n', description)
    keep = True
    result = []
    for line in text.splitlines():
        heading = line.strip().strip('#*: ?').casefold()
        if heading in excluded:
            keep = False
        elif heading in included:
            keep = True
        elif keep:
            result.append(line)
    return '\n'.join(result).strip()


def relevant_fact(text, job):
    """Require job wording to support a selected skill, credential or duty."""
    if off_topic(text, job):
        return False
    generic = {'the', 'and', 'with', 'for', 'from', 'this', 'that', 'have', 'has', 'are', 'was', 'were',
               'will', 'can', 'our', 'your', 'their', 'into', 'work', 'working', 'experience', 'skills',
               'certificate', 'certification', 'diploma', 'degree', 'qualification', 'qualified', 'training',
               'valid', 'until', 'current', 'staff', 'team', 'role', 'job', 'required', 'preferred',
               'good', 'strong', 'excellent', 'ability', 'able', 'environment', 'company', 'business',
               'maintain', 'maintained', 'provide', 'provided', 'assist', 'assisted', 'including', 'within'}
    def terms(value):
        forms = {'communication': 'communicate', 'communicating': 'communicate', 'communicated': 'communicate',
                 'cleanliness': 'clean', 'cleaning': 'clean', 'cleaner': 'clean', 'cleaned': 'clean', 'hygienic': 'hygiene',
                 'teamwork': 'collaborate', 'collaboration': 'collaborate', 'collaborative': 'collaborate',
                 'collaboratively': 'collaborate', 'compassionate': 'compassion',
                 'supervised': 'supervision', 'supervising': 'supervision', 'respectfully': 'respectful'}
        return {forms.get(word, forms.get(word.rstrip('s'), word.rstrip('s'))) for word in re.findall(r'[a-z]{3,}', value.lower()) if word not in generic}
    return bool(terms(text) & terms(job.get('title', '') + ' ' + job.get('description', '')))


def off_topic(text, job):
    # General hygiene or teamwork does not make clinical care duties relevant
    # to a kitchen application. Keep the actual occupation distinct.
    hospitality = re.search(r'\b(kitchen|steward|chef|cook|dishwasher|hospitality)\b', job.get('title', ''), re.I)
    care = re.search(r'\b(aged[ -]care|disability|elderly|older residents|personal care|person.centred care|care plans|medication|ndis|ochre card)\b', text, re.I)
    return bool(hospitality and care)


def sections(profile):
    return {key: profile.get(key, '').splitlines() for key in ('education', 'certifications', 'experience')}


def experience_selection(lines, selected, job=None):
    """Keep source attribution for selected duties without restoring other jobs."""
    groups = []
    headings, duties = [], []
    for i, line in enumerate(lines):
        text = line.strip()
        if not text:
            continue
        is_duty = bool(re.match(r'^[-*•]\s+', text) or
                       ('|' not in text and (text.endswith('.') or len(text.split()) >= 10)))
        if is_duty:
            duties.append(i)
        else:
            if duties or ('|' in text and headings):
                groups.append((headings, duties))
                headings, duties = [], []
            headings.append(i)
    groups.append((headings, duties))
    kept = set()
    for headings, duties in groups:
        if job and off_topic(' '.join(lines[i] for i in headings), job):
            continue
        relevant_duties = selected.intersection(duties)
        if relevant_duties or selected.intersection(headings):
            kept.update(headings)
            kept.update(relevant_duties)
    return kept


def focused_profile(profile, draft):
    result = dict(profile)
    selection = draft.get('selection')
    if selection is None:
        return result
    source = sections(profile)
    if not isinstance(selection, dict) or type(selection.get('headline')) is not bool:
        raise ValueError('Invalid selection of profile facts.')
    for key, lines in source.items():
        indexes = selection.get(key)
        if not isinstance(indexes, list) or any(type(i) is not int or i < 0 or i >= len(lines) for i in indexes):
            raise ValueError('Qwen selected a fact outside your profile. Try preparing again.')
        chosen = set(indexes)
        if key == 'experience':
            chosen = experience_selection(lines, chosen, draft.get('target_job'))
        result[key] = '\n'.join(line for i, line in enumerate(lines) if i in chosen).strip()
    result['headline'] = profile.get('headline', '') if selection['headline'] else ''
    result['summary'] = draft['summary']
    result['skills'] = ', '.join(draft['skills'])
    result['_job_priorities'] = draft.get('job_priorities', [])
    return result
