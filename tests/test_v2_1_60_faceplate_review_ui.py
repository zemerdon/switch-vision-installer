"""Faceplate review UI placement, responsive behavior and safe navigation."""
from pathlib import Path
from html.parser import HTMLParser
import re
import subprocess

root = Path(__file__).resolve().parents[1] / "switch_vision_installer" / "www"
html = (root / "index.html").read_text()
css = (root / "component-manager.css").read_text()
activity = (root / "installer.css").read_text()
js = (root / "installer.js").read_text()

class IDs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        ident = dict(attrs).get("id")
        if ident:
            self.ids.append(ident)

p = IDs()
p.feed(html)
assert len(set(p.ids)) == len(p.ids)
assert p.ids.index("faceplate-review-section") < p.ids.index("activity-section")
assert 'id="faceplate-review-section" class="card faceplate-review-section hidden"' in html
assert 'id="faceplate-review-content"' in html
assert ".faceplate-preview img{display:block;width:100%;height:auto;" in css
assert ".faceplate-preview-label{" in css
assert ".faceplate-preview-label-current{" in css
assert ".faceplate-preview-label-new{" in css
assert "margin:0 auto 16px" in css
assert ".faceplate-review-actions.is-hub{justify-content:center;" in css
assert ".faceplate-hub-link{" in css
assert "@keyframes faceplate-hub-border-glow{" in css
assert "@media(prefers-reduced-motion:reduce){.faceplate-hub-link{animation:none}}" in css
assert ".faceplate-review-actions button:focus-visible{" in css
assert "@media(max-width:560px){.faceplate-review-actions{flex-direction:column}" in css
assert ".result .preserve-columns{columns:2;" in activity
assert "@media(max-width:720px){.result .preserve-columns{columns:1}}" in activity
assert 'class="preserve-columns"' in js
assert "currentStatus?.discovery_hub_path" in js
backend = (root.parent / "app" / "installer.py").read_text()
assert '"discovery_hub_path": f"/app/{discovery.get(\'slug\')}"' in backend
assert "currentStatus?.discovery_ingress_entry" not in js
assert "window.open(entry,'_blank','noopener')" in js
assert "r.dry_run&&!window.svCoreUpgradePreflight" in js

def contrast(colour):
    x = [int(colour[i:i+2],16)/255 for i in (1,3,5)]
    lum = sum(w * (v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)
              for v,w in zip(x, (.2126,.7152,.0722)))
    return 1.05/(lum+.05)

for name in (".faceplate-upgrade-keep", ".faceplate-upgrade-keep:hover",
             ".faceplate-upgrade-review", ".faceplate-upgrade-review:hover"):
    m = re.search(r"(?m)^" + re.escape(name) +
                  r"\{background:linear-gradient\(180deg,var\((--[a-z-]+)\),var\((--[a-z-]+)\)\)", css)
    assert m, name
    for role in m.groups():
        token = re.search(re.escape(role) + r":(#[0-9a-f]{6});", activity)
        assert token, role
        assert contrast(token.group(1)) >= 4.5, role

# Permanent dynamic test uses Node's built-in VM; no browser/network required.
smoke = r"""
const a=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('function faceplateReviewCard(r){');
const end=source.indexOf('function resultSummaryWithCoreRestart(r){',start);
a(start>=0&&end>start);
const el={innerHTML:'',classList:{hidden:true,toggle(_,v){this.hidden=v},add(){this.hidden=true}},
  scrollIntoView(){this.scrolled=true},addEventListener(_,fn){this.click=fn}};
const status={discovery_installed:true,discovery_hub_path:'/app/local_switch_vision_discovery'};
let opened='',notice='';
const ctx={window:{svCoreUpgradePreflight:'core',svReviewFaceplatesAfterInstall:false,
  open:(v,where,rel)=>{opened=v;a.equal(where,'_blank');a.equal(rel,'noopener')}},
  currentStatus:status,resultSummary:()=>'<p>activity</p>', $:()=>el,
  showResult:v=>{notice=v},requestComponentRestart:()=>a.fail('no restart'),
  esc:v=>String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;'),
  document:{querySelectorAll:()=>[]}};
vm.createContext(ctx);
vm.runInContext(source.slice(start,end),ctx);
const name='cisco-3850-12xs.png';
const item={filename:name,incoming_sha256:'a'.repeat(64),
 previous_sha256:'b'.repeat(64), previous_preview:'faceplate-history/revisions/sha/'+'b'.repeat(64)+'/'+name};
const dry={dry_run:true,faceplate_changes:{changed:[item],new:[]}};
a.equal(ctx.resultSummary(dry),'<p>activity</p>');
a.equal(el.classList.hidden,false);
a.equal((el.innerHTML.match(/<img /g)||[]).length,2);
a.equal((el.innerHTML.match(/class="faceplate-preview-label /g)||[]).length,2);
a(el.innerHTML.includes('Current artwork')&&el.innerHTML.includes('New artwork'));
a(el.innerHTML.includes('faceplate-preview-label-current'));
a(el.innerHTML.includes('faceplate-preview-label-new'));
a(el.innerHTML.includes('id="faceplate-upgrade-keep"'));
a(el.innerHTML.includes('id="faceplate-upgrade-review"'));
a(el.innerHTML.includes('faceplates/'+name+'?sha='+'b'.repeat(64)));
a(el.innerHTML.includes('api/faceplate-preview?name='+name+'&sha='+'a'.repeat(64)));
a(!el.innerHTML.includes('id="faceplate-review-open"'));
ctx.window.svCoreUpgradePreflight='';
ctx.window.svReviewFaceplatesAfterInstall=true;
ctx.resultSummary({...dry,dry_run:false});
a(el.innerHTML.includes('id="faceplate-review-open"'));
a(el.innerHTML.includes('Open Switch Vision Hub'));
a(el.innerHTML.includes('faceplate-review-actions is-hub'));
a(el.innerHTML.includes('faceplate-hub-link'));
a(el.innerHTML.includes('faceplate-history/revisions/sha/'+'b'.repeat(64)+'/'+name+'?sha='+'b'.repeat(64)));
a(el.innerHTML.includes('faceplates/'+name+'?sha='+'a'.repeat(64)));
a(!el.innerHTML.includes('faceplates/'+name+'\"'));
a(!el.innerHTML.includes('faceplate-upgrade-keep'));
a(el.scrolled);
a.equal(ctx.window.svReviewFaceplatesAfterInstall,false);
const s=source.indexOf("$('result').addEventListener('click',event=>{");
const e=source.indexOf('initialiseCollapsibleSections();',s);
a(s>0&&e>s);
vm.runInContext(source.slice(s,e),ctx);
function click(id){el.click({target:{closest:sel=>sel===id?{}:null}})}
click('#faceplate-review-open');
a.equal(opened,'/app/local_switch_vision_discovery');
opened='';
status.discovery_hub_path='/api/hassio_ingress/stale';
click('#faceplate-review-open');
a.equal(opened,'');
a.match(notice,/Home Assistant sidebar/);
let request=null;
ctx.json=(url,options)=>{request={url,options};return {then:fn=>{fn();return {catch:()=>{}}}}};
ctx.pollOperation=()=>{};
ctx.window.svCoreUpgradePreflight='core';
click('#faceplate-upgrade-review');
a.equal(request.url,'api/update-component');
a.equal(JSON.parse(request.options.body).component,'core');
a.equal(ctx.window.svReviewFaceplatesAfterInstall,true);
ctx.window.svCoreUpgradePreflight='core';
click('#faceplate-upgrade-keep');
a.equal(request.url,'api/update-component');
a.equal(ctx.window.svReviewFaceplatesAfterInstall,false);
console.log('Faceplate review JavaScript controls: PASS');
"""
test = subprocess.run(["node", "-e", smoke, str(root / "installer.js")],
                      capture_output=True, text=True)
assert test.returncode == 0, test.stdout + test.stderr
print(test.stdout.strip())
print("Faceplate review responsive layout and safe navigation: PASS")
