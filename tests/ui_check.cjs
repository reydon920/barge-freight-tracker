// Execute the shipped report's scripts offline against a small DOM stand-in.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const cases = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
class Element {
  constructor() { this.value = ''; this.textContent = ''; this.children = []; this.events = {}; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  addEventListener(name, action) { this.events[name] = action; }
  click() { this.events.click?.(); }
}
const elements = {};
const get = id => elements[id] ??= new Element();
get('data').textContent = html.match(/<script id="data" type="application\/json">([\s\S]*?)<\/script>/)[1];
let downloaded = '';
const context = vm.createContext({
  document: {getElementById: get, createElement: () => new Element()},
  Blob: class {constructor(parts) { downloaded = parts.join(''); }},
  URL: {createObjectURL: () => 'blob:offline-test', revokeObjectURL: () => {}},
  setTimeout: action => action(), console,
});
vm.runInContext(html.match(/<script>\s*([\s\S]*?)<\/script>/)[1], context);
for (const item of cases) {
  get('origin').value = item.origin;
  get('tons').value = item.short_tons;
  get('budget').value = item.budget_date;
  get('comparison').value = item.comparison_date;
  context.update();
  assert.equal(get('download').disabled, false);
  get('download').click();
  const lines = downloaded.trim().split('\r\n');
  const values = lines[1].split(',').map(s => s.slice(1, -1));
  const keys = lines[0].split(',').map(s => s.slice(1, -1));
  const row = Object.fromEntries(keys.map((key, i) => [key, values[i]]));
  assert.deepEqual(row, item, `Browser/Python mismatch: ${JSON.stringify(item)}`);
}
get('origin').value = 'Twin Cities';
const data = JSON.parse(get('data').textContent);
const missing = data.dates.find(day => data.series['Twin Cities'][day] === null);
get('budget').value = missing;
context.update();
assert.equal(get('download').disabled, true);
assert.match(get('status').textContent, /Unavailable/);
get('tons').value = '-1';
context.update();
assert.equal(get('download').disabled, true);
get('origin').value = 'Lower Illinois';
context.refreshDates();
assert.match(get('chartTitle').textContent, /Lower Illinois/);
assert.ok(get('chart').innerHTML.includes('polyline'));
console.log(`Verified ${cases.length} browser/Python comparisons, missing quotes, CSV export and origin controls.`);
