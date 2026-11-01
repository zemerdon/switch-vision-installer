"""Shared Installer changelog grouping and accessible More/Less contract."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "switch_vision_installer" / "www" / "installer.js"


class ChangelogRollupTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is unavailable")
    def test_consolidated_groups_five_bullets_and_safe_expansion(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        fragment = source[
            source.index("function renderReleaseMarkdownPlain(raw){"):
            source.index("function toggleChangelog(show){")
        ]
        js = r"""
const vm=require('vm'), assert=require('assert'), fs=require('fs');
const source=fs.readFileSync(0,'utf8');
const context={esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.createContext(context);vm.runInContext(source,context);
const fixture=[
  '# Changelog',
  '## v4.0.1','- new platform',
  '## v3.0.0','- new major',
  '## v2.1.1','- a','- b','- c','- d','- e','- f','- g',
  '## v2.1.0','- previous feature',
  '## v2.0.9','- old minor',
  '## v1.9.9','- one major','## v1.0.0','- first gold',
  '## v0.9.2','- before gold','## v0.9.0','- initial beta',
  '## v2.1.1','- a',
].join('\n');
const groups=context.parseChangelogRollups(fixture);
assert.strictEqual(JSON.stringify(groups.map(g=>g.key)),JSON.stringify([
 '4.0.x','3.0.x','2.1.x','2.0.x','1.x','0.x'
]));
const minor=groups.find(g=>g.key==='2.1.x');
assert.strictEqual(minor.bullets.length,8);
assert.strictEqual(minor.versions.size,2);
const html=context.renderReleaseMarkdown(fixture);
assert(html.includes('More (3)'));
assert(html.includes('changelog-show-less">Less'));
assert(html.includes('v2.1.1'));
const block=html.split('v2.1.x')[1].split('v2.0.x')[0];
assert.strictEqual((block.split('<li>').length-1),8);
assert.strictEqual((block.split('<details')[0].split('<li>').length-1),5);
assert.strictEqual((block.split('<details')[1].split('<li>').length-1),3);
assert(!html.includes('<script>'));
const escaping=context.renderReleaseMarkdown('## v2.0.1\n\n- <script>alert(1)</script>');
assert(escaping.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
assert.strictEqual(context.renderReleaseMarkdown('# Notes\n\nPlain words.'),
 context.renderReleaseMarkdownPlain('# Notes\n\nPlain words.'));
const real=fs.readFileSync(process.argv[1],'utf8');
const realGroups=context.parseChangelogRollups(real);
assert(realGroups.some(g=>g.key==='1.x'));
assert(realGroups.some(g=>g.key==='2.1.x'));
console.log('PASS: shared major/minor roll-ups, five preview items, More/Less and escaping');
"""
        result = subprocess.run(
            [shutil.which("node") or "node", "-e", js,
             str(ROOT / "switch_vision_installer" / "CHANGELOG.md")],
            input=fragment,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
