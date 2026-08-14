let managedComponentSnapshot=null;

function componentStatusLabel(row){
  if(row.remote_error)return['Unavailable','missing'];
  if(!row.installed)return[row.optional?'Optional — not installed':'Not installed','missing'];
  if(row.status==='update_available')return[`Update available — v${row.latest_version}`,'missing'];
  if(row.status==='newer_local')return[`Local v${row.installed_version} is newer`,'ok'];
  return['Up to date','ok'];
}

function componentVersionText(row){
  const installed=row.installed_version?`v${row.installed_version}`:'Not installed';
  const latest=row.latest_version?`v${row.latest_version}`:'Unavailable';
  return `${installed} → ${latest}`;
}

function managedComponentAction(row){
  if(row.id==='installer'&&row.update_available)return'Update';
  if(!row.installed&&!row.optional)return'Install';
  if(!row.installed&&row.optional)return'Install';
  if(row.update_available)return'Update';
  return'';
}

function renderManagedComponents(){
  const host=$('components');
  const rows=managedComponentSnapshot?.components||[];
  if(!rows.length){host.innerHTML='<div class="component-manager-loading">Checking component versions…</div>';return;}
  host.innerHTML=rows.map(row=>{
    const [status,cls]=componentStatusLabel(row);
    const action=managedComponentAction(row);
    const dependency=row.dependency_note&&!row.dependency_ok?`<div class="component-dependency">${esc(row.dependency_note)}</div>`:'';
    const repoNote=row.legacy_repository?'<span class="component-repo-note">legacy repo alias active</span>':'';
    return `<div class="managed-component" data-component="${esc(row.id)}">
      <div class="managed-component-main">
        <div class="managed-component-title">${esc(row.label)} ${repoNote}</div>
        <div class="managed-component-version">${esc(componentVersionText(row))}</div>
        ${dependency}
      </div>
      <strong class="managed-component-state ${cls}">${esc(status)}</strong>
      <div class="managed-component-actions">
        <button class="secondary component-changelog" type="button" data-component="${esc(row.id)}">Changelog</button>
        ${action?`<button class="component-update" type="button" data-component="${esc(row.id)}" ${(!row.dependency_ok&&row.id==='discovery')?'disabled':''}>${esc(action)}</button>`:''}
      </div>
    </div>`;
  }).join('');
  const actionable=rows.filter(row=>row.update_available||(!row.installed&&!row.optional&&row.id!=='installer'));
  const updateAll=$('update-all-components');
  if(updateAll){
    const blocked=Boolean(managedComponentSnapshot?.update_all_blocked);
    updateAll.disabled=blocked||!actionable.length;
    updateAll.title=blocked?(managedComponentSnapshot?.update_all_blocked_reason||'Update All is blocked by a dependency.'):'';
    updateAll.textContent=blocked?'Update All blocked':(actionable.length?`Update All (${actionable.length})`:'Everything up to date');
  }
  const note=document.querySelector('.component-manager-note');
  if(note&&managedComponentSnapshot?.update_all_blocked){note.innerHTML=`<b>Update All blocked:</b> ${esc(managedComponentSnapshot.update_all_blocked_reason)}`;}
}

async function loadManagedComponents(){
  try{
    managedComponentSnapshot=await json('api/components');
    renderManagedComponents();
  }catch(error){
    $('components').innerHTML=`<div class="component-manager-error">Unable to check component versions: ${esc(error.message)}</div>`;
  }
}

async function openComponentChangelog(component){
  try{
    const data=await json(`api/component-changelog?component=${encodeURIComponent(component)}`);
    $('changelog-title').textContent=`${data.label} changelog`;
    const installed=data.installed_version?`Installed v${data.installed_version}`:'Not installed';
    const latest=data.latest_version?`Latest v${data.latest_version}`:'Latest unavailable';
    $('changelog-subtitle').textContent=`${installed} · ${latest}`;
    $('changelog-content').innerHTML=renderReleaseMarkdown(data.changelog);
    $('changelog-card').classList.remove('hidden');
    $('changelog-card').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(error){showResult(`Unable to load changelog: ${esc(error.message)}`,'error');}
}

async function requestComponentUpdate(component){
  try{
    await json('api/update-component',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({component})});
    pollOperation();
  }catch(error){showResult(`Component update failed: ${esc(error.message)}`,'error');}
}

const legacyRenderComponents=renderComponents;
renderComponents=function(){renderManagedComponents();};

const legacyRefresh=refresh;
refresh=async function(showLast=true){
  await legacyRefresh(showLast);
  await loadManagedComponents();
};

$('components').addEventListener('click',event=>{
  const changelog=event.target.closest('.component-changelog');
  if(changelog){openComponentChangelog(changelog.dataset.component);return;}
  const update=event.target.closest('.component-update');
  if(update){requestComponentUpdate(update.dataset.component);}
});

$('update-all-components')?.addEventListener('click',async()=>{
  try{await json('api/update-all',{method:'POST'});pollOperation();}
  catch(error){showResult(`Update All failed: ${esc(error.message)}`,'error');}
});

// The per-component changelog buttons supersede the old latest-Core-only control.
const legacyChangelog=$('show-changelog');
if(legacyChangelog){
  const clean=legacyChangelog.cloneNode(true);
  legacyChangelog.replaceWith(clean);
  clean.textContent='Core changelog';clean.disabled=false;
  clean.addEventListener('click',()=>openComponentChangelog('core'));
}

loadManagedComponents();
