const profileSwitch = document.createElement('div');
profileSwitch.className = 'profile-switch';
profileSwitch.innerHTML = '<label>Active career profile<select id="career-select"></select></label><button id="new-career" type="button">＋ New profile</button>';
$('header').after(profileSwitch);
const profileFields = document.createElement('div');
profileFields.innerHTML = '<input type="hidden" name="id"><label>Profile title<input name="title" maxlength="100" placeholder="Rejan IT profile or Rejan Aged Care profile"></label>';
$('#profile-form').prepend(profileFields);
const certificateField = document.createElement('label');
certificateField.innerHTML = 'Certifications and licences<textarea name="certifications" rows="5" placeholder="One certification per line: name | issuing organisation | awarded date | expiry date or no expiry. Include conditions or expired status where relevant."></textarea>';
$('#profile-form details').before(certificateField);
const creationDialog = document.createElement('dialog');
creationDialog.id = 'career-dialog';
creationDialog.innerHTML = '<form id="career-form"><div class="dialog-title"><h2>Create a career profile</h2><button type="button" id="close-career" aria-label="Close profile dialog">×</button></div><label>New profile title<input name="title" required maxlength="100" placeholder="Rejan Aged Care profile"></label><label>Starting information<select name="copy_current"><option value="false">Start with a blank profile</option><option value="true">Copy the current profile</option></select></label><button class="primary" type="submit">Create profile</button></form>';
document.body.appendChild(creationDialog);
$('#new-career').onclick = () => creationDialog.showModal();
$('#close-career').onclick = () => creationDialog.close();
async function saveProfileChanges() {
    const values = Object.fromEntries(new FormData($('#profile-form')));
    values.answers = JSON.parse(values.answers || '{}');
    const changed = Object.keys(values).some(key => JSON.stringify(values[key]) !== JSON.stringify(state.profile[key] ?? ''));
    if (changed) await api('/api/profile', values);
}
async function activateProfile(id) {
    await saveProfileChanges();
    await api('/api/profiles/select', {id});
    selected.clear();
    await refresh(true);
    $('#profile-saved').textContent = '';
    toast(`Using ${state.profile.title}.`);
}
$('#career-select').onchange = async e => {
    try { await activateProfile(e.target.value); }
    catch (err) { toast(err.message); e.target.value = state.profile.id; }
};
$('#career-form').onsubmit = async e => {
    e.preventDefault();
    try {
        await saveProfileChanges();
        const values = Object.fromEntries(new FormData(e.target));
        await api('/api/profiles/create', {title: values.title, copy_current: values.copy_current === 'true'});
        selected.clear();
        await refresh(true);
        e.target.reset(); creationDialog.close(); view('profile');
        toast('Profile created. Add its relevant experience and certifications.');
    } catch (err) { toast(err.message); }
};
const beforeProfilesRender = render;
render = function() {
    beforeProfilesRender();
    const select = $('#career-select');
    select.innerHTML = (state.profiles || []).map(p => `<option value="${esc(p.id)}">${esc(p.title)}</option>`).join('');
    select.value = state.profile.id || '';
    select.disabled = Boolean(state.running || state.preparing);
    $('#new-career').disabled = select.disabled;
};
for (const key of ['id', 'title', 'certifications']) $('#profile-form').elements[key].value = state.profile[key] || '';
if (state.profiles) render();
