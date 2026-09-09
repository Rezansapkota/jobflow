const certificatePanel = document.createElement('div');
certificatePanel.className = 'panel';
certificatePanel.innerHTML = `<h2>Uploaded certificates</h2><p class="muted">Upload one certificate per file (PDF, DOCX, PNG or JPEG; up to 10 MB). Text and scanned pages are read locally. Files stay with the selected profile.</p>
<label>Certificate file<input id="certificate-file" type="file" accept=".pdf,.docx,.png,.jpg,.jpeg"></label>
<button type="button" id="upload-certificate" class="primary">Upload and read certificate</button>
<p id="certificate-progress" role="status"></p><div id="certificate-list"></div>
<label>Certification section used in applications<textarea id="combined-certifications" rows="5" readonly></textarea></label>
<p class="muted">This combines your manually entered certifications with readable, enabled uploads whose holder matches this profile. Review the details and expiry dates. The agent attaches matching certificates only when an application provides a suitable upload field.</p>`;
$('#profile-form').after(certificatePanel);
const certificateDialog = document.createElement('dialog');
certificateDialog.innerHTML = `<form id="certificate-details"><div class="dialog-title"><h2>Certificate details</h2><button type="button" id="close-certificate" aria-label="Close certificate details">×</button></div>
<input type="hidden" name="id"><input type="hidden" name="profile_id">
<label>Certificate name<input name="name" required maxlength="500"></label><label>Issuing organisation<input name="issuer" required maxlength="500"></label><label>Certificate holder<input name="holder" required maxlength="500"></label>
<div class="grid"><label>Issued date<input name="issued_on" placeholder="As shown on the certificate"></label><label>Expiry date<input name="expires_on" placeholder="YYYY-MM-DD, or leave blank if not stated"></label></div>
<label>Matching names, acronyms or course codes<input name="keywords" placeholder="First Aid, HLTAID011"></label><label>Use in applications<select name="enabled"><option value="true">Enabled when relevant</option><option value="false">Disabled</option></select></label>
<details><summary>Extracted source text</summary><pre id="certificate-source"></pre></details><button type="submit" class="primary">Save certificate details</button></form>`;
document.body.appendChild(certificateDialog);
$('#close-certificate').onclick = () => certificateDialog.close();
$('#upload-certificate').onclick = async () => {
    const file = $('#certificate-file').files[0];
    if (!file) return toast('Choose a certificate file first.');
    if (file.size > 10 * 1024 * 1024) return toast('The maximum file size is 10 MB.');
    const pid = state.profile.id;
    try {
        await saveProfileChanges();
        const data = await new Promise((resolve,reject) => {const reader = new FileReader();reader.onload = () => resolve(reader.result.split(',')[1]);reader.onerror = () => reject(Error('Could not read this file.'));reader.readAsDataURL(file);});
        await api('/api/certificates/upload', {profile_id: pid, filename: file.name, data});
        $('#certificate-file').value = '';
        await refresh();
        toast('Certificate uploaded. Local reading has started.');
    } catch (err) { toast(err.message); }
};
$('#certificate-list').onclick = async e => {
    const button = e.target.closest('button');
    if (!button) return;
    const record = (state.certificates || []).find(c => c.id === button.dataset.id);
    if (!record) return;
    if (button.dataset.action === 'edit') {
        const form = $('#certificate-details');
        for (const key of ['id','profile_id','name','issuer','holder','issued_on','expires_on','keywords']) form.elements[key].value = record[key] || '';
        form.elements.enabled.value = String(record.enabled);
        $('#certificate-source').textContent = record.text || 'No readable text was extracted. Enter details from the original certificate.';
        certificateDialog.showModal();
    } else {
        try {
            await saveProfileChanges();
            await api('/api/certificates/' + button.dataset.action, {id: record.id, profile_id: state.profile.id});
            await refresh();
        } catch (err) { toast(err.message); }
    }
};
$('#certificate-details').onsubmit = async e => {
    e.preventDefault();
    try {
        await saveProfileChanges();
        const values = Object.fromEntries(new FormData(e.target));
        values.enabled = values.enabled === 'true';
        await api('/api/certificates/save', values);
        certificateDialog.close(); await refresh();
        toast('Certificate details saved. Check its status before applying.');
    } catch (err) { toast(err.message); }
};
const beforeCertificatesRender = render;
render = function() {
    beforeCertificatesRender();
    const busy = Boolean(state.running || state.preparing);
    const records = (state.certificates || []).filter(c => c.status !== 'removed');
    $('#upload-certificate').disabled = busy;
    $('#certificate-file').disabled = busy;
    $('#certificate-progress').textContent = records.some(c => c.status === 'reading') ? 'Reading certificate with local text extraction / OCR and Qwen…' : '';
    $('#combined-certifications').value = state.combined_certifications || state.profile.certifications || '';
    $('#certificate-list').innerHTML = records.map(c => `<article class="certificate-card"><b>${esc(c.name || c.filename)}</b> <span class="badge">${esc(c.enabled ? c.status : 'disabled')}</span><p>${esc(c.note)}</p><p class="muted">${esc(c.issuer)} ${c.expires_on ? ' · Expires: ' + esc(c.expires_on) : ''}</p><div class="detail-actions"><a href="/api/certificates/file/${c.id}">Download original</a><button type="button" data-action="edit" data-id="${c.id}" ${busy?'disabled':''}>Edit details</button><button type="button" data-action="retry" data-id="${c.id}" ${busy?'disabled':''}>Read again</button><button type="button" data-action="remove" data-id="${c.id}" ${busy?'disabled':''}>Remove from profile</button></div></article>`).join('') || '<p class="muted">No certificate files uploaded yet.</p>';
};
const beforeCertificateDetails = detail;
detail = function(id) {
    beforeCertificateDetails(id);
    const job = state.jobs.find(j=>j.id===id);
    if (!job.certificate_ids?.length) return;
    const section = document.createElement('div');
    section.innerHTML = '<h3>Relevant certificate attachments</h3><p class="muted">These are selected for recognised certificate upload fields. Selection does not mean they were submitted.</p><ul>' + job.certificate_ids.map(cid => {const c=(state.certificates||[]).find(c=>c.id===cid);return `<li>${esc(c?.name || 'Certificate')} ${c?`<a href="/api/certificates/file/${cid}">Original file</a>`:''}</li>`;}).join('') + '</ul>';
    $('#detail-content').appendChild(section);
};
if (state.profile.id) render();
