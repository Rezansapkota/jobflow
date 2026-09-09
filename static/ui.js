let state = {jobs: [], profile: {}};
let selected = new Set();
const $ = s => document.querySelector(s);
const labels = {saved:'Saved',ready:'Ready',running:'Running',needs_input:'Needs input',submitted:'Submitted',uncertain:'Check submission',interview:'Interview',rejected:'Rejected'};
const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let timer;
function toast(message){ $('#toast').textContent=message; $('#toast').hidden=false; clearTimeout(timer); timer=setTimeout(()=>$('#toast').hidden=true,6500); }
async function api(path,body){ const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Session-Token':state.token},body:JSON.stringify(body)}); const data=await r.json(); if(!r.ok)throw Error(data.error); return data; }
async function refresh(initial=false){const r=await fetch('/api/state');if(!r.ok)throw Error('Could not load workspace');state=await r.json();render();if(initial){for(const [k,v] of Object.entries(state.profile)){const field=$('#profile-form').elements[k];if(field)field.value=k==='answers'?JSON.stringify(v,null,2):v;}$('#search-role').value=state.profile.roles;$('#search-location').value=state.profile.search_location;}}
function view(name){document.querySelectorAll('.view').forEach(e=>e.hidden=e.id!==name);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===name));$('#breadcrumb').textContent={board:'Applications',profile:'My profile',search:'Find opportunities'}[name];}
function render(){const all=state.jobs;$('#total').textContent=all.length;$('#ready').textContent=all.filter(j=>j.status==='ready').length;$('#sent').textContent=all.filter(j=>['submitted','interview','rejected'].includes(j.status)).length;$('#interviews').textContent=all.filter(j=>j.status==='interview').length;$('#count').textContent=all.length;$('#running').hidden=!state.running;$('#run').disabled=state.running;$('#prepare').disabled=state.running;const q=$('#filter').value.toLowerCase(),status=$('#status-filter').value;const filtered=all.filter(j=>(!status||(status==='attention'?['needs_input','uncertain','running'].includes(j.status):j.status===status))&&`${j.title} ${j.company}`.toLowerCase().includes(q));$('#job-list').innerHTML=filtered.length?filtered.map(j=>`<article class="job"><input type="checkbox" aria-label="Select ${esc(j.title)}" data-id="${j.id}" ${selected.has(j.id)?'checked':''}><div class="job-icon">${esc(j.company.slice(0,1).toUpperCase())}</div><div class="job-info"><button class="job-title" data-detail="${j.id}">${esc(j.title)}</button><p>${esc(j.company)} · ${esc(j.source)}${j.resume?' · '+j.resume.matched.length+' matching skills':''}</p></div><span class="badge ${j.status}">${labels[j.status]}</span><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer" aria-label="Open job">↗</a></article>`).join(''):`<div class="empty"><div class="symbol">⌁</div><h2>${all.length?'No matching applications':'Good things start with a first step.'}</h2><p>${all.length?'Try a different search or status.':'Add your first job to start building your application pipeline.'}</p>${all.length?'':'<button id="empty-add">＋ Add your first job</button>'}</div>`;$('#empty-add')?.addEventListener('click',()=>$('#job-dialog').showModal());}
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>view(b.dataset.view));$('#profile-link').onclick=()=>view('profile');$('#add').onclick=()=>$('#job-dialog').showModal();document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>document.getElementById(b.dataset.close).close());$('#filter').oninput=render;$('#status-filter').onchange=render;
$('#job-list').onchange=e=>{if(e.target.dataset.id)e.target.checked?selected.add(e.target.dataset.id):selected.delete(e.target.dataset.id);};$('#job-list').onclick=e=>{if(e.target.dataset.detail)detail(e.target.dataset.detail);};
$('#profile-form').onsubmit=async e=>{e.preventDefault();try{const data=Object.fromEntries(new FormData(e.target));data.answers=JSON.parse(data.answers||'{}');await api('/api/profile',data);await refresh();$('#search-role').value=data.roles;$('#search-location').value=data.search_location;$('#profile-saved').textContent='Saved';toast('Profile saved. Prepare fresh resumes to use your changes.');}catch(err){toast(err.message);}};
$('#job-form').onsubmit=async e=>{e.preventDefault();try{await api('/api/jobs',Object.fromEntries(new FormData(e.target)));e.target.reset();$('#job-dialog').close();await refresh();toast('Opportunity added.');}catch(err){toast(err.message);}};
$('#prepare').onclick=async()=>{try{if(!selected.size)throw Error('Select at least one job.');await api('/api/prepare',{ids:[...selected]});await refresh();toast('Eligible applications prepared. Open a job to review its resume.');}catch(err){toast(err.message);}};
$('#run').onclick=async()=>{try{const ids=[...selected].filter(id=>state.jobs.find(j=>j.id===id)?.status==='ready');if(!ids.length)throw Error('Select prepared applications first.');await api('/api/run',{ids,submit:$('#mode').value==='auto'});await refresh();toast('Browser opening. Downloads are also available inside each job.');}catch(err){toast(err.message);}};
function detail(id){const j=state.jobs.find(x=>x.id===id);$('#detail-title').textContent=j.title;$('#detail-content').innerHTML=`<p class="muted">${esc(j.company)} · ${esc(j.source)} · ${labels[j.status]}</p><p>${esc(j.note)}</p><div class="detail-actions"><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">Open application ↗</a>${j.resume?`<a href="/api/resume/${id}">Download resume (.docx)</a>`:''}<select id="manual-status" aria-label="Update application status"><option value="">Update status…</option>${['saved','submitted','interview','rejected','needs_input'].map(s=>`<option value="${s}">${labels[s]}</option>`).join('')}</select></div>${j.resume?`<h3>Tailored resume</h3><p class="muted">${esc(j.resume.note)}</p><pre>${esc(j.resume.text)}</pre>`:'<p>Save your profile, then select this job and choose Prepare selected.</p>'}<details><summary>Job description</summary><pre>${esc(j.description)}</pre></details>`;$('#manual-status').onchange=async e=>{if(!e.target.value)return;try{await api('/api/status',{id,status:e.target.value});await refresh();$('#detail-dialog').close();toast('Status updated.');}catch(err){toast(err.message);}};$('#detail-dialog').showModal();}
$('#linkedin-search').onclick=()=>{const q=new URLSearchParams({keywords:$('#search-role').value,location:$('#search-location').value});window.open('https://www.linkedin.com/jobs/search/?'+q,'_blank','noopener,noreferrer');};
$('#seek-search').onclick=()=>{const role=$('#search-role').value.trim(),loc=$('#search-location').value.trim();const slug=s=>encodeURIComponent(s.replace(/\s+/g,'-'));window.open('https://www.seek.com.au/'+(role?slug(role)+'-jobs':'jobs')+(loc?'/in-'+slug(loc):''),'_blank','noopener,noreferrer');};
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

const activityChart = document.createElement('section');
activityChart.className = 'activity-card';
activityChart.setAttribute('aria-label', 'Application progress graph');
activityChart.innerHTML = `<div class="chart-heading"><div><div class="eyebrow">THE BIG PICTURE</div><h2>Your application progress</h2></div><span class="chart-period">Current profile · All jobs</span></div><p class="chart-caption">See where things stand. Select a bar to explore those jobs.</p><div id="progress-bars" class="progress-bars"></div><p id="chart-empty" class="muted" hidden>Add your first job to start seeing your progress.</p>`;
$('.stats').after(activityChart);
const renderBeforeChart = render;
render = function() {
    renderBeforeChart();
    const groups = [
        {label: 'Saved', statuses: ['saved'], filter: 'saved', color: '#789293'},
        {label: 'For review', statuses: ['ready'], filter: 'ready', color: '#7c80bd'},
        {label: 'Needs attention', statuses: ['needs_input', 'uncertain', 'running'], filter: 'attention', color: '#ba874c'},
        {label: 'Submitted', statuses: ['submitted'], filter: 'submitted', color: '#4f9690'},
        {label: 'Interview', statuses: ['interview'], filter: 'interview', color: '#477e68'},
        {label: 'Rejected', statuses: ['rejected'], filter: 'rejected', color: '#a37886'}
    ];
    const counts = groups.map(g => state.jobs.filter(j => g.statuses.includes(j.status)).length);
    const maximum = Math.max(1, ...counts);
    $('#progress-bars').innerHTML = groups.map((g, i) => `<button class="graph-row" data-chart-filter="${g.filter}" aria-label="${g.label}: ${counts[i]} jobs. Filter pipeline."><span class="graph-label">${g.label}</span><span class="graph-track"><span class="graph-fill"></span></span><strong>${counts[i]}</strong></button>`).join('');
    document.querySelectorAll('.graph-fill').forEach((bar, i) => { bar.style.width = `${counts[i] / maximum * 100}%`; bar.style.backgroundColor = groups[i].color; });
    $('#ready').textContent = state.jobs.filter(j => j.resume && j.cover_letter).length;
    $('#chart-empty').hidden = state.jobs.length > 0;
};
const attentionOption = document.createElement('option');
attentionOption.value = 'attention'; attentionOption.textContent = 'Needs attention';
$('#status-filter').appendChild(attentionOption);
$('#progress-bars').onclick = e => {
    const row = e.target.closest('[data-chart-filter]');
    if (!row) return;
    $('#status-filter').value = row.dataset.chartFilter;
    $('#filter').value = '';
    render();
    $('.board-heading').scrollIntoView({behavior: 'smooth', block: 'start'});
};
