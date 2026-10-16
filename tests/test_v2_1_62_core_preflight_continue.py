"""Core Update must not stop after a no-artwork-change dry run.

Runs the real Installer poll/dispatch functions in isolated Node VM with
simulated finished Supervisor operation results. Never mutates HAOS.
"""
from pathlib import Path
import subprocess

source = Path(__file__).resolve().parents[1] / "switch_vision_installer/www/installer.js"
script = r"""
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const js=fs.readFileSync(process.argv[1],'utf8');
const start=js.indexOf('async function startPendingCoreUpdate(');
const end=js.indexOf("$('close-changelog').addEventListener",start);
assert(start>0&&end>start,'Expected production Core update functions');
let timers=[],network=[],statuses=[],op=null;
let refreshes=0;
const el={
  classList:{remove(){},add(){}},style:{},textContent:'',disabled:false
};
const ctx={
  window:{svCoreUpgradePreflight:'core',svReviewFaceplatesAfterInstall:false},
  pollTimer:null,
  $:()=>el,document:{querySelectorAll:()=>[]},
  showResult:(html,style)=>{statuses.push([String(html),style])},
  openActivitySection(){},restoreActivitySection(){},
  setControls(){},clearInterval(){},
  setInterval:(cb)=>{timers.push(cb);return timers.length},
  refresh:async()=>{refreshes++},
  resultSummaryWithCoreRestart:r=>'<pre>summary '+(r?.version||'')+'</pre>',
  esc:s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;'),
  json:async(url,options)=>{
    network.push([url,options]);
    if(url==='api/operation')return op;
    if(url==='api/update-component'||url==='api/update-all')return {ok:true,started:true};
    throw Error('unexpected url '+url);
  },
};
vm.createContext(ctx);
vm.runInContext(js.slice(start,end),ctx);
const valid={dry_run:true,version:'2.7.99',
  would_change:['custom component'],
  faceplate_changes:{new:[],changed:[]},
  preflight:[{name:'Supervisor API',ok:true,detail:'Pass'}]};
function count(url){return network.filter(([entry])=>entry===url).length}
async function execute(result,mode='core',error=null){
  ctx.window.svCoreUpgradePreflight=mode;
  op={active:false,result,error,kind:'dry run',percent:100,message:'Completed'};
  timers=[];
  network=[];
  statuses=[];
  ctx.pollOperation();
  assert.equal(timers.length,1,'must begin by polling dry-run completion');
  await timers[0]();
  return statuses.at(-1);
}
(async()=>{
  await execute(valid);
  assert.equal(count('api/update-component'),1,'a no-artwork-change Core update must start automatically');
  const coreCall=network.find(([url])=>url==='api/update-component')[1];
  assert.equal(JSON.parse(coreCall.body).component,'core');
  assert.equal(ctx.window.svCoreUpgradePreflight,'');
  assert.equal(ctx.window.svReviewFaceplatesAfterInstall,false);
  assert.equal(timers.length,2,'the same user request must continue polling the real update');
  op={active:false,result:{version:'2.7.99',required_actions:['Restart Home Assistant Core']},kind:'update',percent:100};
  await timers[1]();
  assert.equal(count('api/update-component'),1,'installation must be dispatched exactly once');

  await execute({...valid,faceplate_changes:{new:[],changed:[{filename:'cisco-3850-12xs.png'}]}});
  assert.equal(count('api/update-component'),0,'changed artwork must still wait for explicit user choice');
  assert.equal(ctx.window.svCoreUpgradePreflight,'core');

  await execute({...valid,faceplate_changes:undefined});
  assert.equal(count('api/update-component'),0,'missing comparison must fail closed');
  assert.equal(ctx.window.svCoreUpgradePreflight,'');
  assert.match(statuses.at(-1)[0],/complete artwork comparison/);

  await execute({...valid,faceplate_changes:{new:[],changed:undefined}});
  assert.equal(count('api/update-component'),0,'incomplete comparison must fail closed');

  await execute({...valid,preflight:[{name:'Disk space',ok:false,detail:'Insufficient'}]});
  assert.equal(count('api/update-component'),0,'failed preflight must not silently install');
  assert.match(statuses.at(-1)[0],/preflight checks need attention/);

  await execute({...valid,would_change:[]});
  assert.equal(count('api/update-component'),0,'already-current Core must not reinstall');
  assert.match(statuses.at(-1)[0],/No managed Core files/);

  await execute(valid,'all');
  assert.equal(count('api/update-all'),1,'update-all no-delta preflight must proceed');
  assert.equal(count('api/update-component'),0);

  await execute(valid,'core','Dry-run failed');
  assert.equal(count('api/update-component'),0,'failed operation must not install');
  assert.equal(ctx.window.svCoreUpgradePreflight,'');
  console.log('Installer 2.1.62 complete no-artwork-change preflight / safe update dispatch: PASS');
})().catch(err=>{console.error(err);process.exitCode=1});
"""
run = subprocess.run(["node", "-e", script, str(source)], capture_output=True, text=True)
assert run.returncode == 0, run.stdout + run.stderr
print(run.stdout.strip())
