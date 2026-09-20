const accountFields = document.createElement('div');
accountFields.innerHTML = `<h2>Job site accounts</h2><p class="muted">Add your profile links, or leave them blank to open each site's account page. Sign in directly to LinkedIn or SEEK using the email sign-in option offered by that site. Google sign-in may be blocked in the automated browser; signing into Chrome itself is not required. Each career profile keeps its own local browser session.</p><div class="grid"><label>LinkedIn profile link<input name="linkedin_url" type="url" placeholder="https://www.linkedin.com/in/your-name/"></label><label>SEEK profile link<input name="seek_url" type="url" placeholder="https://www.seek.com.au/profile/me"></label></div>`;
$('#profile-form details').before(accountFields);
for (const key of ['linkedin_url', 'seek_url']) $('#profile-form').elements[key].value = state.profile[key] || '';
const accountBanner = document.createElement('div');
accountBanner.className = 'panel'; accountBanner.hidden = true;
accountBanner.innerHTML = '<h2>Confirm your job site account</h2><p id="account-instructions"></p><p class="muted">If Google says this browser may not be secure, go back to the job site and use its own email sign-in option if available. Use your job-site password, not your Google password. Google-only accounts may need an alternative sign-in method set up through the job site in ordinary Chrome.</p><button type="button" id="account-continue" class="primary">Account ready — continue</button><button type="button" id="account-stop">Cancel run</button>';
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
render = function() {
    beforeAccountsRender();
    const pending = state.account_pending;
    accountBanner.hidden = !pending;
    if (pending) $('#account-instructions').textContent = `In the Chrome window, finish sign-in or verification for ${pending.source}. Then click Account ready below to save that browser session. After connecting your sites, start your search again.`;
};
const beforeReviewDetail = detail;
detail = function(id) {
    beforeReviewDetail(id);
    const job = state.jobs.find(j => j.id === id);
    const panel = document.createElement('div');
    panel.className = 'panel';
    if (job.status === 'ready' && job.resume && job.cover_letter) {
        panel.innerHTML = '<h3>Review before submission</h3><p>Read the tailored resume and cover letter above. Approval applies to these documents and attachments. In Automatic submission mode, Approve queues this job immediately. In Manual handoff mode, approval saves your decision.</p>';
        const approve = document.createElement('button');
        approve.textContent = job.documents_approved ? 'Documents approved' : 'I reviewed both documents - approve';
        approve.disabled = Boolean(job.submission_requested || job.submission_in_progress || state.preparing || (job.documents_approved && $('#mode').value !== 'auto'));
        approve.onclick = async () => {
            try {
                await approveJob(id);
                await refresh();
                approve.textContent = 'Documents approved'; approve.disabled = true;
                toast($('#mode').value === 'auto' ? 'Approved and queued for automatic submission.' : 'Documents approved.');
            } catch (err) { toast(err.message); }
        };
        panel.appendChild(approve);
    } else if (!job.cover_letter || !job.resume) {
        panel.textContent = 'Build both a resume and cover letter before reviewing and approving submission.';
    }
    $('#detail-content').appendChild(panel);
};
const connectionControls = $('#login');
connectionControls.querySelectorAll('.site-login').forEach(form => {
    form.onsubmit = async e => {
        e.preventDefault();
        const button = form.querySelector('button');
        button.disabled = true;
        let credentials = Object.fromEntries(new FormData(form));
        form.elements.password.value = '';
        try {
            await api('/api/accounts/connect', {source: form.dataset.source, ...credentials});
            toast('Opening the site and signing in. Complete any verification in Chrome.');
            await refresh();
        } catch (err) { toast(err.message); }
        finally { credentials = null; button.disabled = Boolean(state.running || state.preparing); }
    };
});
const beforeConnectionRender = render;
render = function() {
    beforeConnectionRender();
    $('#connection-note').textContent = state.connection_note || 'Choose a site to sign in. Sessions are saved separately for each career profile.';
    connectionControls.querySelectorAll('[data-connect]').forEach(b => b.disabled = Boolean(state.running || state.preparing));
};
