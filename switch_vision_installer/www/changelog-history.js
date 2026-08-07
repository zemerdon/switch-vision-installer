(()=>{
  let releases=[];
  let releaseIndex=0;
  let historyPromise=null;

  const style=document.createElement('style');
  style.textContent=`
    .sv-changelog-nav{display:flex;align-items:center;gap:8px;margin-top:7px}
    .sv-changelog-nav button{width:36px;height:30px;padding:0;display:grid;place-items:center;font-size:1rem;line-height:1}
    .sv-changelog-version{min-width:76px;text-align:center;color:#eaf2ff;font-weight:800}
  `;
  document.head.appendChild(style);

  const nav=document.createElement('div');
  nav.className='sv-changelog-nav';
  nav.innerHTML='<button id="changelog-older" class="secondary" type="button" aria-label="Show older changelog" title="Older release">←</button><span id="changelog-version" class="sv-changelog-version" aria-live="polite">—</span><button id="changelog-newer" class="secondary" type="button" aria-label="Show newer changelog" title="Newer release">→</button>';
  const subtitle=$('changelog-subtitle');
  subtitle.parentNode.insertBefore(nav,subtitle);

  const older=$('changelog-older');
  const newer=$('changelog-newer');
  const versionLabel=$('changelog-version');

  function versionOf(release){return String(release?.version||'').trim().replace(/^v/i,'');}

  function renderRelease(release){
    const version=versionOf(release);
    $('changelog-title').textContent=version?`Switch Vision v${version} changelog`:'Release changelog';
    $('changelog-subtitle').textContent=release?.name||'GitHub release notes.';
    $('changelog-content').innerHTML=renderReleaseMarkdown(release?.changelog);
    versionLabel.textContent=version?`v${version}`:'—';
    older.disabled=!releases.length||releaseIndex>=releases.length-1;
    newer.disabled=!releases.length||releaseIndex<=0;
  }

  async function loadReleaseHistory(){
    if(historyPromise)return historyPromise;
    historyPromise=(async()=>{
      const payload=await json('api/releases');
      const list=Array.isArray(payload?.releases)?payload.releases:[];
      const seen=new Set();
      releases=list.filter(release=>{
        const version=versionOf(release);
        if(!version||seen.has(version))return false;
        seen.add(version);
        return true;
      });
      const currentVersion=versionOf(currentRelease);
      let found=releases.findIndex(release=>versionOf(release)===currentVersion);
      if(found<0&&currentVersion){releases.unshift(currentRelease);found=0;}
      releaseIndex=Math.max(0,found);
      return releases;
    })();
    return historyPromise;
  }

  async function prepareHistory(){
    renderRelease(currentRelease);
    try{
      await loadReleaseHistory();
      renderRelease(releases[releaseIndex]||currentRelease);
    }catch(error){
      console.warn('Switch Vision Installer changelog history unavailable:',error);
      releases=[];
      releaseIndex=0;
      renderRelease(currentRelease);
    }
  }

  const originalToggleChangelog=toggleChangelog;
  toggleChangelog=function(show){
    if(!show){originalToggleChangelog(false);return;}
    originalToggleChangelog(true);
    void prepareHistory();
  };

  older.addEventListener('click',()=>{
    if(releaseIndex>=releases.length-1)return;
    releaseIndex+=1;
    renderRelease(releases[releaseIndex]);
  });
  newer.addEventListener('click',()=>{
    if(releaseIndex<=0)return;
    releaseIndex-=1;
    renderRelease(releases[releaseIndex]);
  });
})();
