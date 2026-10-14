// Functional DOM-free smoke tests for component row rendering and restart routing.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../switch_vision_installer/www/component-manager.js'), 'utf8');
const calls = [];
const confirmations = [];
const results = [];
const elements = {
  components: {innerHTML: '', addEventListener(kind, handler) {this.click = handler;}},
  'update-all-components': {disabled: true, addEventListener() {}},
};
const note = {textContent: '', innerHTML: ''};
const buttons = {};
let approve = true;
const context = vm.createContext({
  $: id => elements[id] || null,
  document: {querySelector: selector => {
    if (selector === '.component-manager-note') return note;
    if (selector.startsWith('button.component-restart')) return buttons[selector] || null;
    return null;
  }},
  window: {confirm: message => {confirmations.push(message); return approve;}},
  json: async (url, opts) => {calls.push([url, opts?.method || 'GET']); return {ok: true};},
  refresh: async () => {},
  esc: value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;'),
  showResult: (...args) => results.push(args),
  pollOperation() {},
  setTimeout() {},
  console,
});
vm.runInContext(script, context);

const row = (id, state='started', installed=true) => ({
  id, label: 'Switch Vision ' + id,
  kind: id === 'core' ? 'core' : 'addon', installed,
  slug: id === 'core' ? null : 'repo_' + id,
  state, installed_version: '1.0.0', latest_version: '1.0.1',
  update_available: true, dependency_ok: true,
});
const rows = [row('core'), row('discovery'), row('snmp2mqtt', 'stopped'), row('unifi2mqtt', 'not_installed', false), row('installer')];
function render() {
  vm.runInContext('managedComponentSnapshot = ' + JSON.stringify({components: rows}) + '; renderManagedComponents();', context);
  return elements.components.innerHTML;
}
function markupFor(id) {
  const html = render();
  const start = html.indexOf('data-component="' + id + '"');
  const next = html.indexOf('<div class="managed-component" data-component="', start + 10);
  assert(start >= 0, id + ' row absent');
  return html.slice(start, next < 0 ? undefined : next);
}
async function send(id) {
  await vm.runInContext("requestComponentRestart('" + id + "','Switch Vision " + id + "')", context);
}
async function main() {
  const core = markupFor('core');
  for (const cls of ['component-changelog','component-reinstall','component-restart','component-update']) {
    assert(core.includes(cls), cls + ' missing');
  }
  assert(core.indexOf('component-changelog') < core.indexOf('component-reinstall'));
  assert(core.indexOf('component-reinstall') < core.indexOf('component-restart'));
  assert(core.indexOf('component-restart') < core.indexOf('component-update'));
  assert(!markupFor('installer').includes('component-restart'), 'Installer must not advertise a fake self-restart');
  assert(markupFor('installer').includes('component-external-reinstall'));
  assert(markupFor('snmp2mqtt').includes('disabled title="Restart requires a running Supervisor app."'));
  assert(!markupFor('unifi2mqtt').includes('component-restart'), 'Uninstalled app must not advertise restart');
  assert(markupFor('discovery').includes('component-restart'));
  // Removing the standalone Core card must retain first-install capability.
  rows[0].installed = false;
  const coreNotInstalled = markupFor('core');
  assert(coreNotInstalled.includes('>Install</button>'));
  assert(!coreNotInstalled.includes('component-reinstall'));
  await vm.runInContext("requestComponentUpdate('core')", context);
  assert.deepEqual(calls.at(-1), ['api/update-component', 'POST']);
  calls.length = 0;
  rows[0].installed = true;
  render();
  await send('snmp2mqtt');
  await send('unifi2mqtt');
  await send('installer');
  assert.equal(calls.length, 0, 'unsafe state must not request restart');
  rows[2].state = 'started';
  rows[3].installed = true;
  rows[3].state = 'running';
  render();
  const routes = {core:'api/restart-core',discovery:'api/restart-discovery',snmp2mqtt:'api/restart-snmp2mqtt',unifi2mqtt:'api/restart-unifi2mqtt'};
  for (const [id, url] of Object.entries(routes)) {
    buttons['button.component-restart[data-component="' + id + '"]'] = {disabled:false};
    const count = calls.length;
    await send(id);
    assert.equal(calls.length, count + 1, id + ' did not issue exactly one request');
    assert.deepEqual(calls.at(-1), [url, 'POST']);
    assert.equal(buttons['button.component-restart[data-component="' + id + '"]'].disabled, true);
  }
  assert.equal(confirmations.length, 0, 'Restart must not show a confirmation popup');
  approve = false;
  const count = calls.length;
  await send('discovery');
  assert.equal(calls.length, count, 'Disabled restart must not issue a duplicate request');
  buttons['button.component-restart[data-component="discovery"]'].disabled = false;
  await send('discovery');
  assert.equal(calls.length, count + 1, 'Restart must work without user confirmation');
  assert.equal(confirmations.length, 0, 'Restart must not use window.confirm');
  approve = true;
  const click = elements.components.click;
  buttons['button.component-restart[data-component="discovery"]'].disabled = false;
  click({target:{closest: selector => selector === '.component-restart'
    ? {dataset:{component:'discovery',label:'Switch Vision Discovery'}} : null}});
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls.at(-1), ['api/restart-discovery','POST']);
  assert(!script.includes('api/restart-installer'));
  assert(results.length > 0);
  console.log('Installer v2.1.48 restart UI rendering/routing: PASS');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
