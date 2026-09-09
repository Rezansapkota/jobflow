// The same workflow works for any profile; no applicant details are built in.
const automationNav = document.createElement('button');
automationNav.dataset.view = 'automation';
automationNav.innerHTML = '↗ <span>Job agent</span>';
document.querySelector('nav').appendChild(automationNav);
automationNav.onclick = () => { view('automation'); $('#breadcrumb').textContent = 'Job agent'; };
const agentSection = document.createElement('section');
agentSection.id = 'automation'; agentSection.className = 'view'; agentSection.hidden = true;
agentSection.innerHTML = `<div class="eyebrow">FROM SEARCH TO APPLICATION</div>
<h1>One search. More possibilities.</h1>
<p class="muted">Search in your browser, match against your profile, and prepare a resume and cover letter with local Qwen.</p>
<form id="agent-form" class="panel">
<p>Target roles and location come from <button id="agent-profile" type="button" class="text-button">My profile ↗</button>. Separate multiple roles with commas.</p>
<div class="grid"><label>Job sites<select name="source"><option value="both">LinkedIn + SEEK</option></select></label>
<label>Run mode<select name="submit"><option value="true">Search, prepare and apply</option><option value="false">Search and prepare only</option></select></label></div>
<div class="grid"><label>Maximum jobs to inspect<input name="max_jobs" type="number" min="1" max="30" value="10" required></label>
<label>Maximum application attempts<input name="max_applications" type="number" min="1" max="10" value="3" required></label>
<label>Minimum Qwen match score<input name="min_score" type="number" min="1" max="100" value="80" required></label>
<label>Search pages per site and role<input name="pages" type="number" min="1" max="3" value="1" required></label></div>
<p class="muted">A score is an AI estimate. Mandatory requirements, target role and location must also match. Unknown eligibility needs your input. Sign-in, verification and unsupported forms pause in the browser.</p>
<button type="submit" class="primary" id="agent-start">Search LinkedIn + SEEK ↗</button>
<button type="button" id="agent-stop">Stop run</button>
</form><div class="panel"><h2>Run activity</h2><p id="agent-summary">No run started.</p><ol id="agent-events" class="agent-events"></ol></div>`;
$('footer').before(agentSection);
$('#agent-profile').onclick = () => view('profile');
const eligibility = document.createElement('div');
eligibility.innerHTML = '<label>Work rights<textarea name="work_rights" rows="2" placeholder="Countries you may work in, visa conditions, or sponsorship needs"></textarea></label><label>Other job requirements and preferences<textarea name="constraints" rows="3" placeholder="Availability, work arrangements, salary preferences, excluded roles or employers, travel limits"></textarea></label>';
$('#profile-form details').before(eligibility);
for (const key of ['work_rights', 'constraints']) $('#profile-form').elements[key].value = state.profile[key] || '';
$('#profile-form').elements.experience.placeholder = 'Most recent role first.\n\nJob title | Employer | Jan 2023 - Present\n- Describe an achievement or responsibility.\n\nPrevious job title | Employer | Jan 2021 - Dec 2022\n- Describe an achievement or responsibility.';
$('#agent-form').onsubmit = async e => {
    e.preventDefault();
    const values = Object.fromEntries(new FormData(e.target));
    const config = {sources: ['LinkedIn', 'SEEK'], submit: values.submit === 'true'};
    for (const key of ['max_jobs', 'max_applications', 'min_score', 'pages']) config[key] = Number(values[key]);
    try {
        await api('/api/automation/start', config);
        toast('Job agent started. Use the browser if sign-in is required.');
        await refresh(); await refreshAgent();
    } catch (err) { toast(err.message); }
};
$('#agent-stop').onclick = async () => {
    try { await api('/api/stop', {}); toast('Stopping after the current browser or Qwen operation.'); }
    catch (err) { toast(err.message); }
};
async function refreshAgent() {
    const response = await fetch('/api/automation');
    if (!response.ok) return;
    const run = await response.json();
    $('#agent-start').disabled = Boolean(state.running || state.preparing);
    $('#agent-stop').disabled = !state.running;
    $('#agent-summary').textContent = run.status === 'idle' ? 'No run started.' : `${run.status} · ${run.found || 0} found · ${run.prepared || 0} prepared · ${run.attempted || 0} attempted · ${run.submitted || 0} confirmed submitted`;
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
    const extra = document.createElement('div');
    const match = job.assessment;
    extra.innerHTML = (match ? `<h3>Suitability assessment · ${esc(match.score)}/100</h3><p>${esc(match.reason)}</p><p>Missing requirements: ${esc(match.missing_requirements.join('; ') || 'None identified')}</p><p>Needs clarification: ${esc(match.unknown_requirements.join('; ') || 'None identified')}</p>` : '') +
        (job.cover_letter ? `<h3>Cover letter</h3><a href="/api/cover-letter/${job.id}">Download cover letter (.docx)</a><pre>${esc(job.cover_letter)}</pre>` : '');
    $('#detail-content').appendChild(extra);
};
refreshAgent().catch(() => {});
setInterval(() => refreshAgent().catch(() => {}), 4000);

// One shared search screen for both job sites.
automationNav.remove();
const combinedSearchNav = document.querySelector('nav [data-view=search]');
combinedSearchNav.querySelector('span').textContent = 'Job search';
combinedSearchNav.dataset.view = 'automation';
combinedSearchNav.onclick = () => { view('automation'); $('#breadcrumb').textContent = 'Combined job search'; };
$('#agent-form input[name=max_applications]').closest('label').hidden = true;
const combinedSearchNote = document.createElement('p');
combinedSearchNote.className = 'muted';
combinedSearchNote.textContent = 'One run searches LinkedIn and SEEK in Chrome, alternates results from both sites, and adds new jobs to one pipeline. Suitable jobs get a tailored resume and cover letter for your review.';
$('#agent-form').before(combinedSearchNote);
const dashboardSearch = document.createElement('button');
dashboardSearch.className = 'primary';
dashboardSearch.textContent = 'Search jobs';
dashboardSearch.onclick = combinedSearchNav.onclick;
const dashboardActions = document.createElement('div');
dashboardActions.className = 'dashboard-actions';
$('#add').before(dashboardActions);
dashboardActions.append(dashboardSearch, $('#add'));
