$('#agent-profile').onclick = () => view('profile');
$('#agent-results').onclick = () => view('board');
const searchConnections = document.createElement('div');
searchConnections.className = 'detail-actions';
searchConnections.hidden = true;
searchConnections.innerHTML = '<button type="button" data-search-connect="LinkedIn">Connect LinkedIn</button><button type="button" data-search-connect="SEEK">Connect SEEK</button>';
$('#agent-error').after(searchConnections);
searchConnections.onclick = async e => {
    const source = e.target.dataset.searchConnect;
    if (!source) return;
    view('login');
    document.querySelector(`#login form[data-source="${source}"] input[name=username]`).focus();
};
const sourceSelect = $('#agent-form select[name=source]');
function updateSearchLabel() {
    $('#agent-start').textContent = 'Search ' + (sourceSelect.value === 'both' ? 'LinkedIn + SEEK' : sourceSelect.value);
}
sourceSelect.onchange = updateSearchLabel;
updateSearchLabel();
const eligibility = document.createElement('div');
eligibility.innerHTML = '<label>Work rights<textarea name="work_rights" rows="2" placeholder="Countries you may work in, visa conditions, or sponsorship needs"></textarea></label><label>Other job requirements and preferences<textarea name="constraints" rows="3" placeholder="Availability, work arrangements, salary preferences, excluded roles or employers, travel limits"></textarea></label>';
$('#profile-form details').before(eligibility);
for (const key of ['work_rights', 'constraints']) $('#profile-form').elements[key].value = state.profile[key] || '';
$('#profile-form').elements.experience.placeholder = 'Most recent role first.\n\nJob title | Employer | Jan 2023 - Present\n- Describe an achievement or responsibility.\n\nPrevious job title | Employer | Jan 2021 - Dec 2022\n- Describe an achievement or responsibility.';
$('#agent-form').onsubmit = async e => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.target));
    const config = {sources: values.source === 'both' ? ['LinkedIn', 'SEEK'] : [values.source], submit: false};
    config.keywords = values.keywords.trim();
    config.posted_days = Number(values.posted_days);
    config.sort_order = values.sort_order;
    config.browser_mode = values.browser_mode;
    for (const key of ['max_jobs', 'min_score', 'pages']) config[key] = Number(values[key]);
    $('#agent-start').disabled = true;
    try {
        await saveProfileChanges();
        await refresh();
        await api('/api/automation/start', config);
        toast('Search started. Resumes and cover letters will be created automatically afterwards.');
        await refresh(); await refreshAgent();
    } catch (err) { toast(err.message); }
    finally { await refreshAgent().catch(() => {}); }
};
$('#agent-stop').onclick = async () => {
    try { await api('/api/stop', {}); toast('Stopping after the current browser or Qwen operation.'); }
    catch (err) { toast(err.message); }
};
async function refreshAgent() {
    $('#agent-criteria').textContent = `Profile: ${state.profile.title || 'Default profile'} · Target roles: ${state.profile.roles || 'Add target roles in My profile'} · Location: ${state.job_search_location || 'Add a city or search area in My profile'}`;
    const response = await fetch('/api/automation');
    if (!response.ok) return;
    const run = await response.json();
    const issues = run.source_issues || [];
    const blockedSources = ['LinkedIn', 'SEEK'].filter(source => issues.some(issue => issue.includes(source) && /sign-in|verification/i.test(issue)));
    searchConnections.hidden = !blockedSources.length;
    searchConnections.querySelectorAll('button').forEach(button => {
        button.hidden = !blockedSources.includes(button.dataset.searchConnect);
        button.disabled = Boolean(state.running || state.preparing);
    });
    const networkDenied = issues.some(issue => issue.includes('ERR_NETWORK_ACCESS_DENIED') || issue.includes('Chrome cannot access the internet'));
    const sourceSummaries = ['LinkedIn', 'SEEK'].flatMap(source => {
        const related = issues.filter(issue => issue.includes(source) || issue.toLowerCase().includes(source === 'SEEK' ? 'seek.com' : 'linkedin.com'));
        if (!related.length) return [];
        if (related.some(issue => /Visible Chrome|saved login/i.test(issue))) return [`${source} requires browser verification. Your saved login may still be valid. Choose Visible Chrome in Search options and retry.`];
        if (related.some(issue => /sign-in|verification/i.test(issue))) return [`${source} needs sign-in or verification. Open Login to sign in, then retry.`];
        return [`${source}: some listings could not be read. See Activity details.`];
    });
    const errorMessage = networkDenied ? 'Search was blocked: Chrome could not access the internet. Restart Jobflow with network access, then try again.' : sourceSummaries.join(' ');
    $('#agent-error').textContent = errorMessage || (run.status === 'needs_input' ? run.events?.at(-1)?.message || 'Open activity details to check what needs your attention.' : '');
    $('#agent-error').hidden = !$('#agent-error').textContent;
    $('#agent-results').hidden = !(run.prepared > 0 || run.found > 0 || run.revisited > 0);
    $('#agent-results').textContent = run.prepared > 0 ? 'Review jobs and documents' : 'Review saved jobs';
    $('#agent-stop').hidden = !state.running;
    $('#agent-start').disabled = Boolean(state.running || state.preparing);
    $('#agent-stop').disabled = !state.running;
    $('#agent-summary').textContent = run.status === 'idle' ? 'Your search activity will appear here.' : `${run.status.replaceAll('_', ' ')} / ${run.found || 0} jobs saved / ${run.skipped || 0} excluded or needing review / ${run.prepared || 0} document pairs ready`;
    $('#agent-events').innerHTML = (run.events || []).slice().reverse().map(event => `<li><small>${esc(new Date(event.time).toLocaleTimeString())}</small> ${esc(event.message)}</li>`).join('');
}
const resumeDetail = detail;
detail = function(id) {
    resumeDetail(id);
    const job = state.jobs.find(j => j.id === id);
    if (job.resume) {
        const textLink = document.createElement('a');
        textLink.href = `/api/resume/${job.id}?format=txt`;
        textLink.textContent = 'Download plain text (.txt)';
        $('#detail-content .detail-actions').appendChild(textLink);
    }
    if (job.documents_outdated && ['ready', 'saved', 'needs_input'].includes(job.status)) {
        const refreshDraft = document.createElement('div');
        refreshDraft.innerHTML = '<p class="muted">These documents use older tailoring. Unapproved drafts refresh automatically during your next search.</p>';
        const button = document.createElement('button');
        button.textContent = 'Refresh these documents';
        button.disabled = Boolean(state.running || state.preparing);
        button.onclick = async () => {
            try {
                await api('/api/prepare', {ids: [id], engine: 'ollama'});
                $('#detail-dialog').close();
                await refresh();
                toast('Refreshing this resume and cover letter against the job description. Review the new documents before approving.');
            } catch (err) { toast(err.message); }
        };
        refreshDraft.appendChild(button);
        $('#detail-content').appendChild(refreshDraft);
    }
    const extra = document.createElement('div');
    if (job.date_posted || job.posted_label) {
        const posted = document.createElement('p');
        posted.className = 'muted';
        posted.textContent = 'Posted: ' + (job.date_posted || job.posted_label) + (job.date_posted ? ' (as reported by the site)' : ' (as shown when this job was collected)');
        $('#detail-content').prepend(posted);
    }
    const match = job.assessment;
    extra.innerHTML = (match ? `<h3>Suitability assessment · ${esc(match.score)}/100</h3><p>${esc(match.reason)}</p><p>Missing requirements: ${esc(match.missing_requirements.join('; ') || 'None identified')}</p><p>Needs clarification: ${esc(match.unknown_requirements.join('; ') || 'None identified')}</p>` : '') +
        (job.cover_letter ? `<h3>Cover letter</h3><a href="/api/cover-letter/${job.id}">Download cover letter (.docx)</a><pre>${esc(job.cover_letter)}</pre>` : '');
    if (job.resume?.job_priorities?.length) {
        extra.innerHTML += `<details><summary>Job requirements used for these drafts</summary><ul>${job.resume.job_priorities.map(item => `<li>${esc(item)}</li>`).join('')}</ul></details>`;
    }
    $('#detail-content').appendChild(extra);
};
refreshAgent().catch(() => {});
setInterval(() => refreshAgent().catch(() => {}), 4000);

$('#relevant-only').onchange = () => { selected.clear(); render(); };
