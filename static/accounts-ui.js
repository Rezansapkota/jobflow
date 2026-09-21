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
    const reviewButton = $('[data-review-approve]');
    if (reviewButton) {
        const job = state.jobs.find(j => j.id === reviewButton.dataset.reviewApprove);
        if (job) updateReviewApproval(reviewButton, job);
        else reviewButton.disabled = true;
    }
    const handoff = $('[data-review-handoff]');
    if (handoff) {
        const job = state.jobs.find(j => j.id === handoff.dataset.reviewHandoff);
        handoff.hidden = Boolean(job?.submission_requested || job?.submission_in_progress);
        handoff.disabled = Boolean(state.running || state.preparing || job?.status !== 'ready' || pendingApprovals.has(job?.id));
    }
    const prepare = $('[data-review-prepare]');
    if (prepare) prepare.disabled = Boolean(state.running || state.preparing || pendingDocumentJobs.has(prepare.dataset.reviewPrepare));
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
        panel.innerHTML = '<h3>Review before submission</h3><p>Read the tailored resume and cover letter above. Approval applies to these documents and attachments. Approve &amp; apply immediately queues this job for automatic submission. The agent uses your saved answers and pauses for anything it cannot complete.</p>';
        const approve = document.createElement('button');
        approve.dataset.reviewApprove = id;
        updateReviewApproval(approve, job);
        approve.onclick = async () => {
            try { await approveJob(id); }
            catch (err) { toast(err.message); }
        };
        panel.appendChild(approve);
        const handoff = document.createElement('button');
        handoff.textContent = 'Apply manually in Chrome';
        handoff.dataset.reviewHandoff = id;
        handoff.hidden = Boolean(job.submission_requested || job.submission_in_progress);
        handoff.disabled = Boolean(state.running || state.preparing);
        handoff.onclick = async () => {
            handoff.disabled = true;
            try {
                await api('/api/run', {ids: [id], submit: false});
                $('#detail-dialog').close();
                toast('Opening the application in Chrome for you to complete.');
                await refresh();
            } catch (err) { toast(err.message); }
            finally { render(); }
        };
        panel.appendChild(handoff);
    } else if (['saved', 'needs_input', 'ready'].includes(job.status)) {
        const gaps = [...new Set(job.input_questions || [...(job.assessment?.missing_requirements || []), ...(job.assessment?.unknown_requirements || [])])];
        if (job.status === 'needs_input' && gaps.length) {
            const answersForm = document.createElement('form');
            const heading = document.createElement('h3');
            heading.textContent = 'Details still needed';
            const explanation = document.createElement('p');
            explanation.textContent = 'The saved information could not resolve these requirements. Add your actual details, including no or not held where appropriate. Saved answers will be reused when checking jobs.';
            answersForm.append(heading, explanation);
            const fields = gaps.map(question => {
                const label = document.createElement('label');
                label.textContent = question;
                const input = document.createElement('textarea');
                input.rows = 2;
                input.maxLength = 2000;
                input.value = state.profile.answers?.[question] || '';
                label.appendChild(input);
                answersForm.appendChild(label);
                return {question, input};
            });
            const save = document.createElement('button');
            save.type = 'submit';
            save.textContent = 'Save answers & retry';
            save.disabled = Boolean(state.running || state.preparing);
            answersForm.appendChild(save);
            answersForm.onsubmit = async event => {
                event.preventDefault();
                save.disabled = true;
                try {
                    const answers = {...state.profile.answers};
                    for (const {question, input} of fields) {
                        if (input.value.trim()) answers[question] = input.value.trim();
                    }
                    if (JSON.stringify(answers) === JSON.stringify(state.profile.answers)) throw Error('Add an answer to at least one missing detail.');
                    await api('/api/profile', {...state.profile, answers});
                    await refresh(true);
                    await prepareJobDocuments(id);
                } catch (err) { toast(err.message); }
                finally { save.disabled = Boolean(state.running || state.preparing); }
            };
            panel.appendChild(answersForm);
        }
        const editProfile = document.createElement('button');
        editProfile.textContent = 'Update my profile';
        editProfile.onclick = () => { $('#detail-dialog').close(); view('profile'); };
        panel.appendChild(editProfile);
        const prepare = document.createElement('button');
        prepare.textContent = job.resume && job.cover_letter ? 'Rebuild documents after review' : 'Prepare documents after review';
        prepare.dataset.reviewPrepare = id;
        prepare.disabled = Boolean(state.running || state.preparing || pendingDocumentJobs.has(id));
        prepare.onclick = async () => {
            try { await prepareJobDocuments(id); }
            catch (err) { toast(err.message); }
        };
        panel.appendChild(prepare);
    }
    const reason = document.createElement('p');
    reason.className = 'approval-reason';
    reason.textContent = approvalReason(job);
    panel.appendChild(reason);
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
