"""Execute the actual component update JS handlers without a dry-run detour."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
manager=root / "switch_vision_installer/www/component-manager.js"
node=r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const js=fs.readFileSync(process.argv[1],'utf8');
const start=js.indexOf('async function requestComponentUpdate(component){');
const end=js.indexOf('async function requestComponentReinstall(',start);
assert(start>=0&&end>start);
const updateAll=js.indexOf("$('update-all-components')?.addEventListener('click',async()=>{");
assert(updateAll>0);
let requests=[],polls=0,errors=[],click;
const ctx={
  $:()=>({addEventListener:(type,cb)=>{assert.equal(type,'click');click=cb}}),
  json:async (url,opts)=>{
    requests.push([url,opts]);
    if(url==='api/dry-run')throw Error('Special preview preflight must never be requested');
    return {ok:true};
  },
  pollOperation:()=>{polls++},
  showResult:(msg)=>{errors.push(msg)},
  esc:s=>s
};
vm.createContext(ctx);
vm.runInContext(js.slice(start,end),ctx);
vm.runInContext(js.slice(updateAll),ctx);
(async()=>{
  await ctx.requestComponentUpdate('core');
  await ctx.requestComponentUpdate('discovery');
  assert.deepEqual(requests.slice(0,2).map(r=>r[0]),
    ['api/update-component','api/update-component']);
  assert.equal(JSON.parse(requests[0][1].body).component,'core');
  assert.equal(JSON.parse(requests[1][1].body).component,'discovery');
  assert.equal(polls,2);
  await click();
  assert.equal(requests[2][0],'api/update-all');
  assert.equal(polls,3);
  assert.equal(requests.some(r=>r[0]==='api/dry-run'),false);
  console.log('Installer 2.1.63 direct Core/Discovery/Update-All dispatch: PASS');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
res=subprocess.run(["node","-e",node,str(manager)],capture_output=True,text=True)
assert res.returncode == 0,res.stdout+res.stderr
print(res.stdout.strip())
