const UI_DEFAULTS={density:'comfortable',text_size:'normal',content_width:'standard'};
const UI_ALLOWED={density:new Set(['comfortable','compact','dense']),text_size:new Set(['normal','small']),content_width:new Set(['standard','wide','full'])};
function applyUiPreferences(raw={}){
  const values={...UI_DEFAULTS};
  for(const key of Object.keys(values)){
    const candidate=String(raw?.[key]??values[key]).trim().toLowerCase();
    if(UI_ALLOWED[key].has(candidate))values[key]=candidate;
  }
  document.body.classList.remove('density-comfortable','density-compact','density-dense','text-normal','text-small','width-standard','width-wide','width-full');
  document.body.classList.add(`density-${values.density}`,`text-${values.text_size}`,`width-${values.content_width}`);
  return values;
}
async function loadUiPreferences(){
  try{applyUiPreferences(await json('api/ui-preferences'));}
  catch(error){console.warn('Using default Installer UI preferences:',error);applyUiPreferences();}
}
const $=id=>document.getElementById(id); let currentStatus=null,currentRelease=null,backups=[],pollTimer=null;
const COLLAPSIBLE_SECTIONS=['readiness-section','activity-section','backups-section'];
let activityRestoreState=null;
function initialiseCollapsibleSections(){
  for(const id of COLLAPSIBLE_SECTIONS){
    const section=$(id);if(!section)continue;
    const saved=localStorage.getItem(`switch-vision-installer:${id}:open`);
    if(saved!==null)section.open=saved==='true';
    section.addEventListener('toggle',()=>{if(section.dataset.transientToggle==='true'){delete section.dataset.transientToggle;return;}localStorage.setItem(`switch-vision-installer:${id}:open`,String(section.open));});
  }
}
function openActivitySection(){const section=$('activity-section');if(!section)return;activityRestoreState=section.open;if(!section.open){section.dataset.transientToggle='true';section.open=true;}}
function restoreActivitySection(){const section=$('activity-section');if(!section||activityRestoreState===null)return;if(!activityRestoreState&&section.open){section.dataset.transientToggle='true';section.open=false;}activityRestoreState=null;}
async function json(url,options){const r=await fetch(url,options),raw=await r.text();let d={};if(raw){try{d=JSON.parse(raw);}catch{throw new Error(`Expected JSON but received ${r.headers.get('content-type')||'an unknown response type'} (HTTP ${r.status}).`);}}if(!r.ok)throw new Error(d.error||`HTTP ${r.status}`);return d;}
function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function renderReleaseMarkdown(raw){
  const lines=String(raw||'').replace(/\r\n?/g,'\n').split('\n');
  const out=[];let inList=false,inCode=false,code=[];
  const inline=value=>esc(value).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g,'<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  const closeList=()=>{if(inList){out.push('</ul>');inList=false;}};
  for(const line of lines){
    if(line.trim().startsWith('```')){
      closeList();
      if(inCode){out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);code=[];inCode=false;}else inCode=true;
      continue;
    }
    if(inCode){code.push(line);continue;}
    const heading=line.match(/^(#{1,3})\s+(.+)$/);
    if(heading){closeList();const level=heading[1].length;out.push(`<h${level}>${inline(heading[2])}</h${level}>`);continue;}
    const item=line.match(/^\s*[-*+]\s+(.+)$/);
    if(item){if(!inList){out.push('<ul>');inList=true;}out.push(`<li>${inline(item[1])}</li>`);continue;}
    closeList();
    if(!line.trim()){continue;}
    out.push(`<p>${inline(line.trim())}</p>`);
  }
  closeList();
  if(inCode)out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);
  return out.join('')||'<p>No changelog was published for this release.</p>';
}
function toggleChangelog(show){
  const card=$('changelog-card');
  if(show){
    $('changelog-title').textContent=currentRelease?.version?`Switch Vision v${currentRelease.version} changelog`:'Release changelog';
    $('changelog-subtitle').textContent=currentRelease?.name||'Latest GitHub release notes.';
    $('changelog-content').innerHTML=renderReleaseMarkdown(currentRelease?.changelog);
    card.classList.remove('hidden');
    card.scrollIntoView({behavior:'smooth',block:'start'});
  }else card.classList.add('hidden');
}
function fmtBytes(n){if(n===null||n===undefined||n==='')return'—';if(!Number.isFinite(Number(n)))return'—';const u=['B','KB','MB','GB'];let i=0,v=Number(n);while(v>=1024&&i<u.length-1){v/=1024;i++;}return`${v.toFixed(i?1:0)} ${u[i]}`;}
function fmtDate(v){if(!v)return'—';try{return new Date(v).toLocaleString();}catch{return v;}}
function setControls(on){['check','dry-run','install','create-backup','prune-backups','validate-backup','restore','delete-backup'].forEach(id=>{const needsBackup=['validate-backup','restore','delete-backup'].includes(id);$(id).disabled=on||(needsBackup&&!$('backups').value);});}
function showResult(html,cls='success'){const el=$('result');el.className=`result ${cls}`;el.innerHTML=html;}
function addonState({files,available,installed,state}){if(installed)return{label:state&&state!=='unknown'?`Installed (${state})`:'Installed',cls:'ok'};if(available||files)return{label:'Available — installation required',cls:'missing'};return{label:'Not available',cls:'missing'};}
function renderComponents(s){const discovery=addonState({files:s.discovery_present,available:s.discovery_available,installed:s.discovery_installed,state:s.discovery_state});const snmp=addonState({files:s.snmp2mqtt_present,available:s.snmp2mqtt_available,installed:s.snmp2mqtt_installed,state:s.snmp2mqtt_state});const unifi=addonState({files:s.unifi2mqtt_present,available:s.unifi2mqtt_available,installed:s.unifi2mqtt_installed,state:s.unifi2mqtt_state});const discoveryLabel=s.discovery_version?`Discovery add-on — v${s.discovery_version}`:'Discovery add-on';const snmpLabel=s.snmp2mqtt_version?`SNMP2MQTT add-on — v${s.snmp2mqtt_version}`:'SNMP2MQTT add-on';const unifiLabel=s.unifi2mqtt_version?`UniFi2MQTT add-on — v${s.unifi2mqtt_version}`:'UniFi2MQTT add-on (optional)';const rows=[['Custom component',s.component_present?'Installed':'Not installed',s.component_present?'ok':'missing'],['Dashboard frontend',s.frontend_present?'Installed':'Not installed',s.frontend_present?'ok':'missing'],[discoveryLabel,discovery.label,discovery.cls],[snmpLabel,snmp.label,snmp.cls],[unifiLabel,unifi.label,unifi.cls]];$('components').innerHTML=rows.map(([n,label,cls])=>`<div class="component"><span>${n}</span><strong class="${cls}">${label}</strong></div>`).join('');$('install-discovery').classList.toggle('hidden',!(s.discovery_available&&!s.discovery_installed));$('restart-discovery').classList.toggle('hidden',!s.discovery_installed);$('install-snmp2mqtt').classList.toggle('hidden',!(s.snmp2mqtt_available&&!s.snmp2mqtt_installed));$('restart-snmp2mqtt').classList.toggle('hidden',!s.snmp2mqtt_installed);$('install-unifi2mqtt').classList.toggle('hidden',!!s.unifi2mqtt_installed);$('restart-unifi2mqtt').classList.toggle('hidden',!s.unifi2mqtt_installed);}


function syncSystemActions(s={}){
  const discoveryInstalled=Boolean(s.discovery_installed);
  const snmpInstalled=Boolean(s.snmp2mqtt_installed);
  const unifiInstalled=Boolean(s.unifi2mqtt_installed);

  $('install-discovery').classList.toggle('hidden',discoveryInstalled||!s.discovery_available);
  $('restart-discovery').classList.toggle('hidden',!discoveryInstalled);

  $('install-snmp2mqtt').classList.toggle('hidden',snmpInstalled||!s.snmp2mqtt_available);
  $('restart-snmp2mqtt').classList.toggle('hidden',!snmpInstalled);

  $('install-unifi2mqtt').classList.toggle('hidden',unifiInstalled||!s.unifi2mqtt_available);
  $('restart-unifi2mqtt').classList.toggle('hidden',!unifiInstalled);
}

function renderGuidance(){const s=currentStatus||{},steps=[];if(!s.component_present||!s.frontend_present)steps.push('Install Switch Vision Core and dashboard files.');if(!s.discovery_installed)steps.push(s.discovery_available?'Install the Discovery add-on using the button below.':'Run the main installation so Discovery becomes available.');if(!s.snmp2mqtt_installed)steps.push(s.snmp2mqtt_available?'Install the SNMP2MQTT add-on using the button below.':'Run the main installation so SNMP2MQTT becomes available.');const el=$('first-run');if(steps.length){el.classList.remove('hidden');el.innerHTML=`<b>First-run guidance</b><ol>${steps.map(x=>`<li>${esc(x)}</li>`).join('')}</ol>`;}else{el.classList.add('hidden');el.innerHTML='';}}
function renderChecklist(){const s=currentStatus||{},items=[['Core installed',s.component_present],['Dashboard frontend installed',s.frontend_present],['Discovery installed',s.discovery_installed],['SNMP2MQTT installed',s.snmp2mqtt_installed],['Generated SNMP2MQTT YAML present',s.snmp2mqtt_generated_yaml],['Recovery backup available',backups.length>0]];$('checklist').innerHTML=items.map(([label,ok])=>`<div class="check-item ${ok?'pass':'pending'}"><span>${ok?'✓':'○'}</span><b>${esc(label)}</b></div>`).join('');}

function compare(a,b){const pa=String(a||'').split('.').map(Number),pb=String(b||'').split('.').map(Number);for(let i=0;i<Math.max(pa.length,pb.length);i++){const d=(pa[i]||0)-(pb[i]||0);if(d)return d;}return 0;}
function renderState(){const installed=currentStatus?.installed_version,latest=currentRelease?.version;$('installed').textContent=installed?`v${installed}`:'Not installed';$('latest').textContent=latest?`v${latest}`:'Unavailable';$('installer').textContent=`v${currentStatus?.installer_version||'1.9.10'}`;syncSystemActions(currentStatus||{});renderComponents(currentStatus||{});renderGuidance();renderChecklist();$('backup-location').textContent=`Backup location: ${currentStatus?.backup_path||'/share/switch-vision-backups/'}`;$('backup-retention').textContent=`Retention: newest ${currentStatus?.backup_retention||5} backups`;$('asset').textContent=currentRelease?.asset_name||'—';$('asset-size').textContent=fmtBytes(currentRelease?.asset_size);$('published').textContent=fmtDate(currentRelease?.published_at);const btn=$('install'),dry=$('dry-run'),badge=$('state-badge');dry.disabled=!latest;badge.className='badge';if(!latest){$('state-title').textContent='Release check unavailable';$('state-copy').textContent='The installer could not retrieve the latest public release.';badge.textContent='Unavailable';badge.classList.add('warn');btn.disabled=true;return;}if(!installed){$('state-title').textContent='Ready to install';$('state-copy').textContent=`Switch Vision v${latest} is available for first-time installation.`;badge.textContent='Not installed';badge.classList.add('warn');btn.textContent='Install Switch Vision';btn.disabled=false;return;}const c=compare(installed,latest);if(c<0){$('state-title').textContent='Update available';$('state-copy').textContent=`Switch Vision v${latest} is ready to replace v${installed}.`;badge.textContent='Update available';badge.classList.add('warn');btn.textContent=`Update to v${latest}`;btn.disabled=false;}else if(c===0){$('state-title').textContent='Switch Vision is up to date';$('state-copy').textContent='The installed version matches the latest public release.';badge.textContent='Up to date';badge.classList.add('okb');btn.textContent=`Reinstall v${latest}`;btn.disabled=false;}else{$('state-title').textContent='Installed version is newer';$('state-copy').textContent=`Installed v${installed}; latest public release is v${latest}.`;badge.textContent='Newer local build';badge.classList.add('neutral');btn.textContent=`Install public v${latest}`;btn.disabled=false;}}
function selectedBackup(){return backups.find(b=>b.name===$('backups').value);}
function renderBackupMeta(){const b=selectedBackup();$('validate-backup').disabled=!b;$('restore').disabled=!b;$('delete-backup').disabled=!b;$('backup-meta').innerHTML=b?`<b>${esc(b.name)}</b><br>Created: ${esc(fmtDate(b.created_at))}<br>Version: ${b.version?`v${esc(b.version)}`:'Unknown'}<br>Contains: ${esc((b.contents||[]).join(', ')||'Unknown')}<br>SNMP2MQTT options: ${b.snmp2mqtt_configuration_saved?'Saved':'Not saved'}<br>UniFi2MQTT options: ${b.unifi2mqtt_configuration_saved?'Saved':b.unifi2mqtt_configuration_skipped_unconfigured?'Not saved (not configured)':'Not saved'}<br>Generated YAML: ${b.snmp2mqtt_generated_yaml_saved?'Saved':'Not saved'}${b.legacy_location?'<br><b>Location:</b> Legacy backup folder':''}`:'No backup selected.';}
async function loadBackups(){const d=await json('api/backups');backups=d.backups||[];const sel=$('backups');sel.innerHTML=backups.length?backups.map(b=>`<option value="${esc(b.name)}">${esc(b.name)}${b.version?` — v${esc(b.version)}`:''}</option>`).join(''):'<option value="">No backups found</option>';renderBackupMeta();renderChecklist();}
function resultSummary(r){if(r.backup_created){return`<h3>Backup created successfully</h3><p><b>Backup:</b> ${esc(r.backup)}</p><p><b>Location:</b> <code>${esc(r.backup_path||'')}</code></p><p><b>Status:</b> ${r.verified?'Verified':'Not verified'}</p><p><b>Files checked:</b> ${esc(r.file_count||0)}</p>${r.version?`<p><b>Switch Vision version:</b> v${esc(r.version)}</p>`:''}${Number.isFinite(Number(r.configured_switches))?`<p><b>Discovery switches saved:</b> ${esc(r.configured_switches)}</p>`:''}`;}if(r.backup_validated){return`<h3>Backup validation passed</h3><p><b>Backup:</b> ${esc(r.backup)}</p><p><b>Status:</b> Verified</p><p><b>Files checked:</b> ${esc(r.file_count||0)}</p>`;}if(r.dry_run){const changes=(r.would_change||[]).map(x=>`<li>${esc(x)}</li>`).join(''),unchanged=(r.unchanged||[]).map(x=>`<li>${esc(x)}</li>`).join(''),preserve=(r.would_preserve||[]).map(x=>`<li>${esc(x)}</li>`).join(''),checks=(r.preflight||[]).map(x=>`<li><b>${esc(x.name)}:</b> ${x.ok?'Pass':'Advisory'} — ${esc(x.detail)}</li>`).join('');return`<h3>Dry run completed</h3><p>No files or settings were changed.</p><p><b>Target:</b> v${esc(r.version)}</p><p><b>SHA-256:</b> <code>${esc(r.checksum)}</code>${r.checksum_verified?' (verified against published checksum)':' (computed; no published checksum asset found)'}</p>${changes?`<p><b>Would change:</b></p><ul>${changes}</ul>`:'<p>No managed components would change.</p>'}${unchanged?`<p><b>Already current:</b></p><ul>${unchanged}</ul>`:''}${preserve?`<p><b>Would preserve:</b></p><ul>${preserve}</ul>`:''}<p><b>Backup:</b> ${r.would_create_backup?'Would be created and validated':'Not required'}</p>${checks?`<p><b>Preflight checks:</b></p><ul>${checks}</ul>`:''}`;}const installed=(r.installed||r.restored||[]).map(x=>`<li>${esc(x)}</li>`).join(''),skipped=(r.skipped||[]).map(x=>`<li>${esc(x)}</li>`).join(''),unchanged=(r.unchanged||[]).map(x=>`<li>${esc(x)}</li>`).join(''),preserved=(r.preserved||[]).map(x=>`<li>${esc(x)}</li>`).join(''),actions=(r.required_actions||[]).map(x=>`<li>${esc(x)}</li>`).join('');return`<h3>${r.restored?'Backup restored':'Operation completed successfully'}</h3>${r.version?`<p><b>Version:</b> v${esc(r.version)}</p>`:''}${r.backup?`<p><b>Backup:</b> ${esc(r.backup)}</p>`:''}${r.checksum?`<p><b>SHA-256:</b> <code>${esc(r.checksum)}</code></p>`:''}${installed?`<p><b>${r.restored?'Restored':'Changed'}:</b></p><ul>${installed}</ul>`:'<p>No managed component files required replacement.</p>'}${skipped?`<p><b>Skipped safely:</b></p><ul>${skipped}</ul>`:''}${unchanged?`<p><b>Already current:</b></p><ul>${unchanged}</ul>`:''}${preserved?`<p><b>Preserved custom assets:</b></p><ul>${preserved}</ul>`:''}${actions?`<p><b>Required next steps:</b></p><ol>${actions}</ol>`:''}`;}
function resultSummaryWithCoreRestart(r){
  const html=resultSummary(r);
  const needsRestart=(r.required_actions||[]).includes('Restart Home Assistant Core');
  if(!needsRestart)return html;
  return `${html}<div class="restart-required"><p class="warning"><b>Restart Home Assistant Core required</b><br>Switch Vision Core files were updated, but Home Assistant may still be running the previous integration version in memory.</p><button id="result-restart-core" class="danger" type="button">Restart Home Assistant Core</button></div>`;
}

async function refresh(showLast=true){setControls(true);try{[currentStatus,currentRelease]=await Promise.all([json('api/status'),json('api/latest')]);renderState();await loadBackups();if(showLast&&currentStatus.last_result)showResult(resultSummary(currentStatus.last_result),'success');else if(showLast)showResult('Ready.','muted');}catch(e){showResult(`Unable to check releases: ${esc(e.message)}`,'error');}finally{setControls(false);renderState();}}
async function pollOperation(){showResult('Operation in progress…','muted');openActivitySection();clearInterval(pollTimer);$('progress').classList.remove('hidden');$('progress-text').classList.remove('hidden');setControls(true);pollTimer=setInterval(async()=>{try{const op=await json('api/operation');$('progress-bar').style.width=`${op.percent||0}%`;$('progress-text').textContent=op.message||'Working…';$('progress-stage').classList.remove('hidden');$('progress-stage').textContent=`${esc(op.kind||'operation')} — ${op.percent||0}%`;if(!op.active){clearInterval(pollTimer);restoreActivitySection();$('progress').classList.add('hidden');$('progress-text').classList.add('hidden');$('progress-stage').classList.add('hidden');if(op.error)showResult(`Operation failed: ${esc(op.error)}`,'error');else if(op.result){showResult(resultSummaryWithCoreRestart(op.result),'success');}await refresh(false);}}catch(e){clearInterval(pollTimer);restoreActivitySection();showResult(`Unable to read operation status: ${esc(e.message)}`,'error');setControls(false);}},700);}
$('close-changelog').addEventListener('click',()=>toggleChangelog(false));
$('check').addEventListener('click',()=>refresh(false));$('backups').addEventListener('change',renderBackupMeta);
$('dry-run').addEventListener('click',async()=>{try{await json('api/dry-run',{method:'POST'});pollOperation();}catch(e){showResult(`Dry run failed: ${esc(e.message)}`,'error');}});
$('install').addEventListener('click',async()=>{try{await json('api/install',{method:'POST'});pollOperation();}catch(e){showResult(`Installation failed: ${esc(e.message)}`,'error');}});
$('create-backup').addEventListener('click',async()=>{try{await json('api/create-backup',{method:'POST'});pollOperation();}catch(e){showResult(`Backup failed: ${esc(e.message)}`,'error');}});
$('validate-backup').addEventListener('click',async()=>{const b=selectedBackup();if(!b)return;try{await json('api/validate-backup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:b.name})});pollOperation();}catch(e){showResult(`Validation failed: ${esc(e.message)}`,'error');}});
$('restore').addEventListener('click',async()=>{const b=selectedBackup();if(!b)return;if(!confirm(`Restore ${b.name}?\n\nThis will replace the components contained in that backup.`))return;try{await json('api/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:b.name})});pollOperation();}catch(e){showResult(`Restore failed: ${esc(e.message)}`,'error');}});
$('prune-backups').addEventListener('click',async()=>{try{const r=await json('api/prune-backups',{method:'POST'});await loadBackups();showResult(`<h3>Backup retention applied</h3><p><b>Retention:</b> newest ${esc(r.retention)} backups</p><p><b>Removed:</b> ${esc((r.removed||[]).length)}</p><p><b>Location:</b> <code>${esc(r.backup_path||'')}</code></p>`,'success');}catch(e){showResult(`Retention cleanup failed: ${esc(e.message)}`,'error');}});
$('delete-backup').addEventListener('click',async()=>{const b=selectedBackup();if(!b)return;if(!confirm(`Delete backup ${b.name}?\n\nThis cannot be undone.`))return;try{await json('api/delete-backup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:b.name})});await loadBackups();showResult('Backup deleted.','success');}catch(e){showResult(`Delete failed: ${esc(e.message)}`,'error');}});

$('install-discovery').addEventListener('click',async()=>{const button=$('install-discovery');button.disabled=true;try{await json('api/install-discovery',{method:'POST'});showResult('Discovery add-on installation requested. Refreshing status shortly…','success');setTimeout(()=>refresh(false),4000);}catch(e){button.disabled=false;showResult(`Discovery install failed: ${esc(e.message)}`,'error');}});
$('install-snmp2mqtt').addEventListener('click',async()=>{const button=$('install-snmp2mqtt');button.disabled=true;try{await json('api/install-snmp2mqtt',{method:'POST'});showResult('SNMP2MQTT add-on installation requested. Refreshing status shortly…','success');setTimeout(()=>refresh(false),4000);}catch(e){button.disabled=false;showResult(`SNMP2MQTT install failed: ${esc(e.message)}`,'error');}});
$('install-unifi2mqtt').addEventListener('click',async()=>{const button=$('install-unifi2mqtt');button.disabled=true;try{await json('api/install-unifi2mqtt',{method:'POST'});showResult('UniFi2MQTT add-on installed. Configure it from Switch Vision Hub before starting.','success');setTimeout(()=>refresh(false),2500);}catch(e){button.disabled=false;showResult(`UniFi2MQTT install failed: ${esc(e.message)}`,'error');}});
$('result').addEventListener('click',event=>{if(event.target.closest('#result-restart-core'))$('restart-core').click();});
$('restart-core').addEventListener('click',async()=>{if(!confirm('Restart Home Assistant Core now?'))return;const button=$('restart-core');button.disabled=true;try{await json('api/restart-core',{method:'POST'});showResult('Home Assistant Core restart requested. This page may temporarily disconnect.','success');}catch(e){button.disabled=false;showResult(`Core restart failed: ${esc(e.message)}`,'error');}});
$('restart-discovery').addEventListener('click',async()=>{const button=$('restart-discovery');button.disabled=true;try{await json('api/restart-discovery',{method:'POST'});showResult('Discovery add-on restart requested.','success');setTimeout(()=>{button.disabled=false;},5000);}catch(e){button.disabled=false;showResult(`Discovery restart failed: ${esc(e.message)}`,'error');}});
initialiseCollapsibleSections();
loadUiPreferences().finally(()=>refresh());

$('restart-snmp2mqtt').addEventListener('click',async()=>{const button=$('restart-snmp2mqtt');button.disabled=true;try{await json('api/restart-snmp2mqtt',{method:'POST'});showResult('SNMP2MQTT add-on restart requested.','success');setTimeout(()=>{button.disabled=false;},5000);}catch(e){button.disabled=false;showResult(`SNMP2MQTT restart failed: ${esc(e.message)}`,'error');}});
$('restart-unifi2mqtt').addEventListener('click',async()=>{const button=$('restart-unifi2mqtt');button.disabled=true;try{await json('api/restart-unifi2mqtt',{method:'POST'});showResult('UniFi2MQTT add-on restart requested.','success');setTimeout(()=>{button.disabled=false;refresh(false);},5000);}catch(e){button.disabled=false;showResult(`UniFi2MQTT restart failed: ${esc(e.message)}`,'error');}});
