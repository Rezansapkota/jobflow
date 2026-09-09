const accountFields = document.createElement('div');
accountFields.innerHTML = `<h2>Job site accounts</h2><p class="muted">Add your profile links, or leave them blank to open each site's account page. Enter your ID and password directly in the agent browser when it opens. Each career profile keeps its own local browser session.</p><div class="grid"><label>LinkedIn profile link<input name="linkedin_url" type="url" placeholder="https://www.linkedin.com/in/your-name/"></label><label>SEEK profile link<input name="seek_url" type="url" placeholder="https://www.seek.com.au/profile/me"></label></div>`;
$('#profile-form details').before(accountFields);
for (const key of ['linkedin_url', 'seek_url']) $('#profile-form').elements[key].value = state.profile[key] || '';
const accountBanner = document.createElement('div');
accountBanner.className = 'panel'; accountBanner.hidden = true;
accountBanner.innerHTML = '<h2>Confirm your job site account</h2><p id="account-instructions"></p><button type="button" id="account-continue" class="primary">Account ready — continue</button><button type="button" id="account-stop">Cancel run</button>';
document.querySelector('header').after(accountBanner);
$('#account-continue').onclick = async () => {
    try {
        await api('/api/accounts/confirm', {id: state.account_pending?.id});
        toast('Account confirmation sent. The agent will continue after sign-in.');
        await refresh();
    } catch (err) { toast(err.message); }
};
$('#account-stop').onclick = async () => { try { await api('/api/stop', {}); } catch (err) { toast(err.message); } };
const beforeAccountsRender = render;
const documentSummary = document.createElement('p');
documentSummary.className = 'mode-note';
$('#ai-status').after(documentSummary);
const prepareMissing = document.createElement('button');
prepareMissing.type = 'button';
prepareMissing.textContent = 'Build missing resumes + cover letters';
$('#prepare').after(prepareMissing);
prepareMissing.onclick = async () => {
    try {
        await saveProfileChanges();
        await refresh();
        const ids = state.jobs.filter(j => ['saved', 'needs_input', 'ready'].includes(j.status) && (!j.resume || !j.cover_letter)).slice(0, 10).map(j => j.id);
        if (!ids.length) throw Error('All eligible jobs already have both documents.');
        await api('/api/prepare', {ids, engine: 'ollama'});
        await refresh();
        toast(`Qwen is creating documents for ${ids.length} saved jobs. This does not submit applications.`);
    } catch (err) { toast(err.message); }
};
render = function() {
    beforeAccountsRender();
    const pairs = state.jobs.filter(j => j.resume && j.cover_letter).length;
    documentSummary.textContent = `${pairs} of ${state.jobs.length} pipeline jobs have a resume and cover letter.${state.preparing ? ' Qwen is writing documents now.' : ' Open a job to preview or download its documents.'} The Job agent activity counts refer only to its last search run.`;
    prepareMissing.disabled = Boolean(state.running || state.preparing);
    const pending = state.account_pending;
    accountBanner.hidden = !pending;
    if (pending) $('#account-instructions').textContent = `In the agent browser, sign in to ${pending.source} and check that it is the account you want to use for ${state.profile.title}. Then continue here. Search and applications start after both selected accounts are confirmed.`;
};
const startWithSavedProfile = $('#agent-form').onsubmit;
$('#agent-form').onsubmit = async e => {
    e.preventDefault();
    try { await saveProfileChanges(); await startWithSavedProfile(e); }
    catch (err) { toast(err.message); }
};
