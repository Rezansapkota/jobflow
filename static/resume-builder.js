'use strict';
const form = document.querySelector('#resume-form');
const profileSelect = document.querySelector('#resume-profile');
const statusMessage = document.querySelector('#builder-status');
const fields = ['name', 'email', 'phone', 'location', 'headline', 'summary', 'skills', 'experience', 'education', 'certifications'];
let workspace;
let source;
let draftKey;
let finalResult = null;
let pendingTask = null;
let tailoringBusy = false;
let aiAvailable = null;
const tailorForm = document.querySelector('#tailor-form');
const tailorStatus = document.querySelector('#tailor-status');
const downloadButtons = document.querySelectorAll('[data-download]');
const downloadStatus = document.querySelector('#download-status');
function setDownloadsDisabled(disabled) {
    downloadButtons.forEach(button => { button.disabled = disabled || tailoringBusy; });
}

function values() {
    return Object.fromEntries(fields.map(key => [key, form.elements[key].value]));
}
function resumeText() {
    if (finalResult) return finalResult.text;
    const data = values();
    const lines = [data.name.trim(), data.headline.trim(), [data.email, data.phone, data.location].map(s => s.trim()).filter(Boolean).join(' | ')].filter(Boolean);
    for (const [key, title] of [['summary', 'PROFESSIONAL SUMMARY'], ['skills', 'SKILLS'], ['experience', 'WORK EXPERIENCE'], ['education', 'EDUCATION'], ['certifications', 'CERTIFICATIONS']]) {
        if (data[key].trim()) lines.push('', title, data[key].trim());
    }
    return lines.join('\n');
}
function preview() {
    document.querySelector('#resume-preview').textContent = resumeText() || 'Add your details to start building your resume.';
    document.querySelector('#preview-heading').textContent = finalResult ? 'Final tailored resume' : 'Live preview';
    document.querySelector('#download-description').textContent = finalResult ? 'Download the final tailored resume shown below as PDF, Word or text.' : 'Download your current edits as a PDF, Word document or plain text.';
}
function saveDraft() {
    preview();
    try {
        localStorage.setItem(draftKey, JSON.stringify(values()));
        statusMessage.textContent = `Draft saved for ${workspace.profile.title}.`;
    } catch {
        statusMessage.textContent = 'Browser storage is unavailable. Download your resume to keep your edits.';
    }
}
function populate(data) {
    fields.forEach(key => { form.elements[key].value = typeof data[key] === 'string' ? data[key] : ''; });
    preview();
}
async function loadProfile() {
    const response = await fetch('/api/state');
    if (!response.ok) throw Error('Could not load your profile. Reload this page to try again.');
    workspace = await response.json();
    source = {...workspace.profile, certifications: workspace.combined_certifications ?? workspace.profile.certifications};
    renderApplicationContext();
    draftKey = `jobflow.resume.${source.id}`;
    profileSelect.replaceChildren(...workspace.profiles.map(p => new Option(p.title, p.id)));
    profileSelect.value = source.id;
    let draft;
    let storageUnavailable = false;
    try { draft = JSON.parse(localStorage.getItem(draftKey)); } catch { storageUnavailable = true; }
    const restored = draft && typeof draft === 'object' && !Array.isArray(draft);
    populate(restored ? draft : source);
    restoreTailoring();
    statusMessage.textContent = storageUnavailable ? 'Browser storage is unavailable. Download your resume to keep your edits.' : restored ? `Saved draft restored for ${source.title}. Use “Refill from saved profile” to load updated profile information.` : `Prefilled from ${source.title}. Add or edit any missing details below.`;
    document.querySelector('#resume-fields').disabled = false;
    setDownloadsDisabled(false);
    document.querySelector('#tailor-fields').disabled = false;
    if (pendingTask) pollTask(pendingTask);
}
form.addEventListener('input', event => {
    if (event.target !== profileSelect) { invalidateTailoring(); saveDraft(); }
});
document.querySelector('#resume-reset').onclick = async () => {
    if (!confirm('Replace this resume draft with the latest saved profile information?')) return;
    try {
        const response = await fetch('/api/state');
        if (!response.ok) throw Error('Could not load the latest profile. Try again.');
        const latest = await response.json();
        if (latest.profile.id !== source.id) throw Error('The active profile changed in another page. Reload this page first.');
        source = {...latest.profile, certifications: latest.combined_certifications ?? latest.profile.certifications};
        workspace.profile = latest.profile;
        renderApplicationContext();
        invalidateTailoring();
        populate(source);
        saveDraft();
        saveTailoring();
    } catch (error) { statusMessage.textContent = error.message; }
};
profileSelect.onchange = async () => {
    document.querySelector('#resume-fields').disabled = true;
    document.querySelector('#tailor-fields').disabled = true;
    setDownloadsDisabled(true);
    try {
        const response = await fetch('/api/profiles/select', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session-Token': workspace.token}, body: JSON.stringify({id: profileSelect.value})});
        if (!response.ok) throw Error((await response.json()).error);
        await loadProfile();
    } catch (error) {
        profileSelect.value = source.id;
        statusMessage.textContent = error.message;
    } finally {
        document.querySelector('#resume-fields').disabled = tailoringBusy;
        document.querySelector('#tailor-fields').disabled = tailoringBusy;
        setDownloadsDisabled(false);
    }
};
form.onsubmit = async event => {
    event.preventDefault();
    const format = event.submitter?.dataset.download || 'docx';
    setDownloadsDisabled(true);
    downloadStatus.textContent = 'Preparing your download…';
    try {
        const response = await fetch('/api/resume-builder/download', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session-Token': workspace.token}, body: JSON.stringify({text: resumeText(), format})});
        if (!response.ok) throw Error((await response.json()).error);
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url;
        link.download = `resume.${format}`;
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        downloadStatus.textContent = `Your ${{docx: 'Word', pdf: 'PDF', txt: 'text'}[format]} resume download has started.`;
    } catch (error) { downloadStatus.textContent = error.message; }
    finally { setDownloadsDisabled(false); }
};
function jobValues() {
    return {title: document.querySelector('#target-title').value,
        description: document.querySelector('#target-description').value,
        engine: document.querySelector('#tailor-engine').value,
        preferences: {length: document.querySelector('#resume-length').value,
            tone: document.querySelector('#resume-tone').value,
            emphasis: document.querySelector('#resume-emphasis').value,
            max_skills: Number(document.querySelector('#resume-max-skills').value)}};
}
function savedContext() {
    const p = workspace?.profile || {};
    return {roles: p.roles || '', search_location: p.search_location || '', work_rights: p.work_rights || '', constraints: p.constraints || '', answers: p.answers || {}};
}
function renderApplicationContext() {
    const p = savedContext();
    document.querySelector('#analysis-context').textContent = [
        `Target roles: ${p.roles || 'Not provided'}`, `Search area: ${p.search_location || 'Not provided'}`,
        `Work rights: ${p.work_rights || 'Not provided'}`, `Availability and other constraints: ${p.constraints || 'Not provided'}`,
        `Saved application answers: ${JSON.stringify(p.answers, null, 2)}`
    ].join('\n\n');
}
function fingerprint() { return JSON.stringify({candidate: values(), context: savedContext(), ...jobValues()}); }
function saveTailoring() {
    try {
        localStorage.setItem(`${draftKey}.tailoring`, JSON.stringify({...jobValues(), result: finalResult, task: pendingTask, fingerprint: fingerprint()}));
    } catch {
        tailorStatus.textContent = 'Browser storage is unavailable. Keep this page open and download your final resume.';
    }
}
function renderAnalysis() {
    document.querySelector('#tailor-results').hidden = !finalResult;
    document.querySelector('#final-edit').hidden = !finalResult;
    document.querySelector('#final-resume-text').value = finalResult?.text || '';
    if (!finalResult) { preview(); return; }
    const labels = {evidenced: 'Evidence found — verify', partial: 'Partial evidence', not_found: 'Not evidenced in profile', review: 'Check wording overlap'};
    document.querySelector('#analysis-note').textContent = `${finalResult.engine === 'ollama' ? 'Local AI analysis.' : 'Basic wording analysis; it cannot verify eligibility.'} ${finalResult.note}`;
    const preferences = finalResult.preferences;
    document.querySelector('#analysis-settings').textContent = preferences
        ? `${finalResult.model || 'Basic matching'} · ${preferences.length} detail · ${preferences.tone} style · ${preferences.emphasis.replaceAll('_', ' ')} · Up to ${preferences.max_skills} skills`
        : '';
    document.querySelector('#analysis-skills').textContent = finalResult.skills.join(', ') || 'No relevant saved skills identified.';
    const tbody = document.querySelector('#analysis-requirements');
    tbody.replaceChildren();
    for (const requirement of finalResult.requirements) {
        const row = document.createElement('tr');
        const target = document.createElement('td');
        target.textContent = requirement.requirement;
        const evidence = document.createElement('td');
        evidence.textContent = requirement.evidence.length ? requirement.evidence.join('\n\n') : 'No supporting evidence identified. Add details only if true.';
        const review = document.createElement('td');
        const label = document.createElement('strong');
        label.textContent = labels[requirement.status] || 'Needs review';
        const note = document.createElement('p');
        note.textContent = requirement.note;
        review.append(label, note);
        row.append(target, evidence, review);
        tbody.append(row);
    }
    for (const [selector, items] of [['#analysis-warnings', [...finalResult.warnings, 'Verify the generated summary, selected experience, credential validity and all job requirements before applying.']], ['#analysis-ats', finalResult.ats]]) {
        document.querySelector(selector).replaceChildren(...items.map(item => {
            const li = document.createElement('li'); li.textContent = item; return li;
        }));
    }
    preview();
}
function invalidateTailoring() {
    if (finalResult) tailorStatus.textContent = 'Your details changed. Run analysis again to create an updated tailored resume.';
    finalResult = null;
    pendingTask = null;
    downloadStatus.textContent = '';
    updateEngineNote();
    renderAnalysis();
    saveTailoring();
}
function restoreTailoring() {
    finalResult = null;
    pendingTask = null;
    tailorStatus.textContent = '';
    let saved;
    try { saved = JSON.parse(localStorage.getItem(`${draftKey}.tailoring`)); } catch { /* Keep source form available. */ }
    document.querySelector('#target-title').value = typeof saved?.title === 'string' ? saved.title : '';
    document.querySelector('#target-description').value = typeof saved?.description === 'string' ? saved.description : '';
    document.querySelector('#tailor-engine').value = saved?.engine === 'basic' ? 'basic' : 'ollama';
    for (const [id, key, fallback] of [['resume-length', 'length', 'balanced'], ['resume-tone', 'tone', 'direct'], ['resume-emphasis', 'emphasis', 'role_fit'], ['resume-max-skills', 'max_skills', '12']]) {
        const select = document.getElementById(id);
        const value = String(saved?.preferences?.[key] ?? fallback);
        select.value = [...select.options].some(option => option.value === value) ? value : fallback;
    }
    updateEngineNote();
    if (saved?.fingerprint === fingerprint()) {
        if (saved.result && typeof saved.result.text === 'string' && ['skills', 'requirements', 'warnings', 'ats'].every(key => Array.isArray(saved.result[key]))) finalResult = saved.result;
        if (typeof saved.task === 'string') pendingTask = saved.task;
    }
    renderAnalysis();
    if (finalResult) tailorStatus.textContent = 'Your saved tailored resume is ready to review and download.';
}
function setTailoringBusy(busy) {
    tailoringBusy = busy;
    document.querySelector('#resume-fields').disabled = busy;
    document.querySelector('#tailor-fields').disabled = busy;
    document.querySelector('#resume-use-source').disabled = busy;
    document.querySelector('#final-resume-text').disabled = busy;
    document.querySelector('#tailor-submit').textContent = busy ? 'Analyzing and tailoring…' : 'Analyze job & tailor resume';
    setDownloadsDisabled(busy);
}
async function pollTask(id) {
    setTailoringBusy(true);
    try {
        while (true) {
            const response = await fetch(`/api/resume-builder/tasks/${encodeURIComponent(id)}`);
            const task = await response.json();
            if (!response.ok) throw Error(task.error);
            tailorStatus.textContent = task.message;
            if (task.status === 'error') throw Error(task.message);
            if (task.status === 'complete') {
                finalResult = task.result;
                pendingTask = null;
                saveTailoring();
                renderAnalysis();
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 1500));
        }
    } catch (error) {
        pendingTask = null;
        saveTailoring();
        tailorStatus.textContent = `${error.message} Your source information and any previous final resume are preserved.`;
    } finally { setTailoringBusy(false); }
}
tailorForm.addEventListener('input', invalidateTailoring);
tailorForm.onsubmit = async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    setTailoringBusy(true);
    tailorStatus.textContent = 'Starting analysis. Local AI can take a few minutes; your progress is saved if you reload.';
    try {
        const response = await fetch('/api/resume-builder/tailor', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Session-Token': workspace.token},
            body: JSON.stringify({profile_id: source.id, candidate: values(), ...jobValues()})});
        const task = await response.json();
        if (!response.ok) throw Error(task.error);
        pendingTask = task.id;
        saveTailoring();
        await pollTask(task.id);
    } catch (error) {
        tailorStatus.textContent = error.message;
    } finally { setTailoringBusy(false); }
};
document.querySelector('#resume-use-source').onclick = () => {
    invalidateTailoring();
    tailorStatus.textContent = 'Using your untailored source resume. Your job description is saved for the next analysis.';
};
document.querySelector('#final-resume-text').oninput = event => {
    if (!finalResult) return;
    finalResult.text = event.target.value;
    preview();
    saveTailoring();
    tailorStatus.textContent = 'Final resume edits saved. Review your changes before downloading.';
};
loadProfile().catch(error => { statusMessage.textContent = error.message; });
function updateEngineNote() {
    const basic = document.querySelector('#tailor-engine').value === 'basic';
    for (const id of ['resume-length', 'resume-tone', 'resume-emphasis']) document.getElementById(id).disabled = basic;
    document.querySelector('#tailor-engine-note').textContent = document.querySelector('#tailor-engine').value === 'basic'
        ? 'Basic matching selects source facts using wording overlap. It runs without AI and cannot assess eligibility.'
        : aiAvailable === true ? 'Local Qwen AI is ready. Analysis and rewriting stay on this computer.'
        : aiAvailable === false ? 'Local Qwen AI is unavailable. Start Ollama with qwen3:8b, or select Basic matching to continue without AI.'
        : 'Local AI uses Qwen on this computer. Checking availability…';
}
async function checkLocalModel() {
    const button = document.querySelector('#refresh-model');
    const status = document.querySelector('#local-model-status');
    button.disabled = true;
    status.textContent = 'Checking local model...';
    try {
        const response = await fetch('/api/ai');
        if (!response.ok) throw Error('Could not check the local model. Try again.');
        const ai = await response.json();
        aiAvailable = Boolean(ai.available);
        status.textContent = aiAvailable ? `${ai.model} is ready through Ollama. Your information stays on this computer.`
            : `${ai.model || 'qwen3:8b'} is not ready. Start Ollama and run: ollama pull qwen3:8b. Then check the connection again.`;
    } catch (error) { aiAvailable = false; status.textContent = error.message; }
    finally { button.disabled = false; updateEngineNote(); }
}
document.querySelector('#refresh-model').onclick = checkLocalModel;
checkLocalModel();
