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
render = function() {
    beforeAccountsRender();
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
