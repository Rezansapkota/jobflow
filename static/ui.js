let state = {jobs: [], profile: {}};
let selected = new Set();
const pendingApprovals = new Set();
const pendingDocumentJobs = new Set();
const $ = s => document.querySelector(s);
const labels = {saved:'Saved',ready:'Ready',running:'Running',needs_input:'Needs input',submitted:'Submitted',uncertain:'Check submission',interview:'Interview',rejected:'Rejected'};
function jobStatusLabel(job){
    return job.status==='needs_input'?({processing_error:'Preparation failed',profile_information:'Profile details needed',job_match:'Review match'}[job.input_kind]||labels.needs_input):labels[job.status];
}
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let timer;
function toast(message){ $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(timer); timer=setTimeout(()=>$('#toast').hidden=true,6500); }
async function api(path,body,timeoutMs=0){
    const options={method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':state.token},body:JSON.stringify(body)};
    if(timeoutMs) options.signal=AbortSignal.timeout(timeoutMs);
    const r=await fetch(path,options);
    const data=await r.json(); if(!r.ok)throw Error(data.error); return data;
}
function approvalPresentation(job){
    const busy=pendingApprovals.has(job.id);
    const label=busy?'Approving...':job.submission_requested?'Queued':job.submission_in_progress?'Applying':job.documents_approved?'Apply approved':'Approve & apply';
    return {label,busy,disabled:Boolean(busy||job.status!=='ready'||!job.review_token||job.submission_requested||job.submission_in_progress||state.preparing)};
}
function approvalReason(job){
    if(pendingApprovals.has(job.id))return 'Saving your approval...';
    if(job.submission_requested)return 'Queued. Waiting for the current browser operation to finish.';
    if(job.submission_in_progress||job.status==='running')return 'Application in progress. Check the Chrome window for questions or sign-in.';
    if(job.status==='uncertain')return 'Check submission in Review before attempting this application again.';
    if(['submitted','interview'].includes(job.status))return 'Already submitted. No further approval is needed.';
    if(job.status==='rejected')return 'This job is rejected. Open Review to update its status if needed.';
    if(state.preparing)return 'Wait for document preparation to finish.';
    if(job.input_kind==='processing_error'&&job.status==='needs_input')return 'Document processing failed. Open Review issues to retry using your saved information.';
    if(job.input_kind==='profile_information'&&job.status==='needs_input')return 'Saved information was checked. Open Review issues to answer the specific details still missing.';
    if(job.status==='needs_input')return 'Open Review issues to check the job match and missing requirements, then prepare documents after review.';
    if(!job.resume||!job.cover_letter)return 'Use Prepare documents to build the resume and cover letter before approval.';
    if(job.status!=='ready')return 'Use Prepare documents to refresh this draft before approval.';
    if(job.documents_approved)return 'Documents already approved. Click Apply approved to start automatic submission.';
    return '';
}
function approvalButtonMarkup(job){
    if(!pendingApprovals.has(job.id)&&!job.submission_requested&&!job.submission_in_progress){
        let next='';
        if(job.status==='needs_input')next='Review issues';
        else if(job.status==='uncertain')next='Check submission';
        else if(['submitted','interview','rejected'].includes(job.status))next='View status';
        if(next)return `<button type="button" data-detail="${job.id}" aria-label="${next} ${esc(job.title)}">${next}</button>`;
        if(job.status==='saved'||(job.status==='ready'&&(!job.resume||!job.cover_letter)))return `<button type="button" data-prepare-job="${job.id}" aria-label="Prepare documents ${esc(job.title)}" ${state.running||state.preparing||pendingDocumentJobs.has(job.id)?'disabled':''}>Prepare documents</button>`;
    }
    const action=approvalPresentation(job);
    return `<button type="button" data-approve="${job.id}" aria-label="${action.label} ${esc(job.title)}" aria-describedby="approval-reason-${job.id}" aria-busy="${action.busy}" ${action.disabled?'disabled':''}>${action.label}</button>`;
}
async function prepareJobDocuments(id){
    if(pendingDocumentJobs.has(id))return;
    pendingDocumentJobs.add(id);render();
    try{
        await api('/api/prepare',{ids:[id],engine:'ollama'},12000);
        $('#detail-dialog').close();
        toast('Preparing this resume and cover letter. Review both documents when ready.');
        await refresh();
    }finally{pendingDocumentJobs.delete(id);render();}
}
function updateReviewApproval(button,job){
    const action=approvalPresentation(job);
    button.textContent=action.label;
    button.disabled=action.disabled;
    button.setAttribute('aria-busy',String(action.busy));
    const reason=button.parentElement?.querySelector('.approval-reason');
    if(reason)reason.textContent=approvalReason(job);
}
async function refresh(initial=false){const r=await fetch('/api/state',{signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Could not load workspace');state=await r.json();render();if(initial){for(const [k,v] of Object.entries(state.profile)){const field=$('#profile-form').elements[k];if(field)field.value=k==='answers'?JSON.stringify(v,null,2):v;}}}
function view(name){document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==name);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===name));$('#breadcrumb').textContent={board:'Applications',profile:'My profile',automation:'Job search',login:'Login'}[name];}
function render(){const all=state.jobs.filter(j=>!$('#relevant-only')?.checked||(j.location_matches_profile!==false&&(!j.assessment||((j.assessment.role_match!==false||j.assessment.role_match_unverified)&&j.assessment.location_match!==false))));$('#total').textContent=all.length;$('#ready').textContent=all.filter(j=>j.resume&&j.cover_letter).length;$('#sent').textContent=all.filter(j=>['submitted','interview','rejected'].includes(j.status)&&!j.user_rejected).length;$('#interviews').textContent=all.filter(j=>j.status==='interview').length;$('#count').textContent=all.length;$('#running').hidden=!state.running;$('#run').disabled=state.running;$('#prepare').disabled=state.running;const q=$('#filter').value.toLowerCase(),status=$('#status-filter').value;const filtered=all.filter(j=>(!status||(status==='attention'?['needs_input','uncertain','running'].includes(j.status):j.status===status))&&`${j.title} ${j.company}`.toLowerCase().includes(q));$('#job-list').innerHTML=filtered.length?filtered.map(j=>`<article class="job"><input type="checkbox" aria-label="Select ${esc(j.title)}" data-id="${j.id}" ${selected.has(j.id)?'checked':''}><div class="job-icon">${esc(j.company.slice(0,1).toUpperCase())}</div><div class="job-info"><button class="job-title" data-detail="${j.id}">${esc(j.title)}</button><p>${esc(j.company)} · ${esc(j.source)} &middot; ${esc(j.location||'Location not stated')}${j.resume?' · '+j.resume.matched.length+' matching skills':''}</p><p class="approval-reason" id="approval-reason-${j.id}">${esc(approvalReason(j))}</p></div><span class="badge ${j.status}">${j.submission_requested?'Queued':j.submission_in_progress?'Applying':j.documents_approved&&j.status==='ready'?'Approved':jobStatusLabel(j)}</span><div class="job-decisions">${approvalButtonMarkup(j)}<button type="button" data-reject="${j.id}" aria-label="Reject ${esc(j.title)}" ${['running','submitted','uncertain','interview','rejected'].includes(j.status)||j.submission_in_progress?'disabled':''}>Reject</button><button type="button" data-detail="${j.id}" aria-label="Review ${esc(j.title)}">Review</button></div><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer" aria-label="Open job">↗</a></article>`).join(''):`<div class="empty"><div class="symbol">⌁</div><h2>${all.length?'No matching applications':'Good things start with a first step.'}</h2><p>${all.length?'Try a different search or status.':'Add your first job to start building your application pipeline.'}</p>${all.length?'':'<button id="empty-add">＋ Add your first job</button>'}</div>`;$('#empty-add')?.addEventListener('click',()=>$('#job-dialog').showModal());}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>view(b.dataset.view));$('#add').onclick=()=>$('#job-dialog').showModal();document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.close).close());$('#filter').oninput=render;$('#status-filter').onchange=render;
$('#job-list').onchange=e=>{if(e.target.dataset.id)e.target.checked?selected.add(e.target.dataset.id):selected.delete(e.target.dataset.id);};$('#job-list').onclick=async e=>{
    const button=e.target.closest('button'); if(!button)return;
    try {
        if(button.dataset.detail) detail(button.dataset.detail);
        else if(button.dataset.prepareJob) { await prepareJobDocuments(button.dataset.prepareJob); }
        else if(button.dataset.approve) { button.disabled=true; await approveJob(button.dataset.approve); }
        else if(button.dataset.reject) { button.disabled=true; await api('/api/review/reject',{id:button.dataset.reject}); selected.delete(button.dataset.reject); await refresh(); toast('Rejected. This job will not be submitted.'); }
    } catch(err) { toast(err.message); render(); }
};
async function approveJob(id) {
    if(pendingApprovals.has(id))return;
    const job=state.jobs.find(j=>j.id===id);
    if(!job)throw Error('This job is no longer in the active profile. Refresh the page.');
    const submit=true;
    pendingApprovals.add(id);render();
    try {
        await api('/api/review/approve',{id,review_token:job.review_token,submit},12000);
        // The POST has succeeded even if the following status refresh fails.
        job.documents_approved=true;
        if(submit)job.submission_requested=job.review_token;
        try { await refresh(); }
        catch { toast('Approval saved. Status could not refresh; reload the page to check progress.');return; }
        toast('Approved and queued for automatic submission.');
    } catch(err) {
        if(err.name==='TimeoutError')throw Error('Approval response timed out. It may have been saved. Refresh to check its status before trying again.');
        throw err;
    } finally { pendingApprovals.delete(id);render(); }
}
$('#profile-form').onsubmit=async e=>{e.preventDefault();try{const data=Object.fromEntries(new FormData(e.target));data.answers=JSON.parse(data.answers||'{}');await api('/api/profile',data);await refresh();$('#profile-saved').textContent='Saved';toast('Profile saved. Prepare fresh resumes to use your changes.');}catch(err){toast(err.message);}};
$('#job-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/jobs',Object.fromEntries(new FormData(e.target)));e.target.reset();$('#job-dialog').close();await refresh();toast('Opportunity added.');}catch(err){toast(err.message);}};
$('#run').onclick=async()=>{try{const ids=[...selected].filter(id=>state.jobs.some(j=>j.id===id&&j.status==='ready'&&j.documents_approved&&!j.submission_requested&&!j.submission_in_progress));if(!ids.length)throw Error('Select approved, ready applications first. Use Approve & apply on each job to approve its documents.');await api('/api/run',{ids,submit:true});await refresh();toast('Browser opening. Downloads are also available inside each job.');}catch(err){toast(err.message);}};
function detail(id){const j=state.jobs.find(x=>x.id===id);$('#detail-title').textContent=j.title;$('#detail-content').innerHTML=`<p class="muted">${esc(j.company)} · ${esc(j.source)} · ${jobStatusLabel(j)}</p><p>${esc(j.note)}</p><div class="detail-actions"><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">Open application ↗</a>${j.resume?`<a href="/api/resume/${id}">Download resume (.docx)</a>`:''}<select id="manual-status" aria-label="Update application status"><option value="">Update status…</option>${['saved','submitted','interview','rejected','needs_input'].map(s=>`<option value="${s}">${labels[s]}</option>`).join('')}</select></div>${j.resume?`<h3>Tailored resume</h3><p class="muted">${esc(j.resume.note)}</p><pre>${esc(j.resume.text)}</pre>`:'<p>Save your profile, then select this job and choose Prepare selected.</p>'}<details><summary>Job description</summary><pre>${esc(j.description)}</pre></details>`;$('#manual-status').onchange=async e=>{if(!e.target.value)return;try{await api('/api/status',{id,status:e.target.value});await refresh();$('#detail-dialog').close();toast('Status updated.');}catch(err){toast(err.message);}};$('#detail-dialog').showModal();}
refresh(true).catch(e=>toast(e.message));setInterval(()=>refresh().catch(()=>{}),4000);
const stopButton=document.createElement('button');stopButton.textContent='Stop browser run';$('#running').appendChild(stopButton);stopButton.onclick=async()=>{try{await api('/api/stop',{});toast('Stopping after the current browser action.');}catch(err){toast(err.message);}};

const engineSelect=document.createElement('select');
engineSelect.id='resume-engine';
engineSelect.setAttribute('aria-label','Resume tailoring engine');
engineSelect.innerHTML='<option value="ollama">Local Qwen AI</option><option value="basic">Basic tailoring</option>';
$('#prepare').before(engineSelect);
const aiStatus=document.createElement('p');
aiStatus.className='mode-note';
aiStatus.id='ai-status';
aiStatus.textContent='Checking local Ollama…';
$('.mode-note').before(aiStatus);
const baseRender=render;
render=function(){
    baseRender();
    $('#prepare').disabled=state.running||state.preparing;
    $('#run').disabled=state.running||state.preparing;
    engineSelect.disabled=state.preparing;
    $('#prepare').textContent=state.preparing?'Qwen is writing…':'Prepare selected';
};
$('#prepare').onclick=async()=>{
    try{
        if(!selected.size)throw Error('Select at least one job.');
        await api('/api/prepare',{ids:[...selected],engine:engineSelect.value});
        await refresh();
        toast(engineSelect.value==='ollama'?'Qwen is preparing your resumes locally. Open each job for its result.':'Resumes prepared. Open a job to review.');
    }catch(err){toast(err.message);}
};
fetch('/api/ai').then(r=>r.json()).then(ai=>{
    aiStatus.textContent=ai.available?`Connected to Ollama · ${ai.model} · Resume generation stays on this computer.`:'Ollama unavailable. Start Ollama with qwen3:8b installed, or choose Basic tailoring.';
}).catch(()=>{aiStatus.textContent='Could not check Ollama. Refresh to retry, or choose Basic tailoring.';});

if (location.hash === '#profile') view('profile');
if (location.hash === '#automation') view('automation');

if (location.hash === '#login') view('login');
