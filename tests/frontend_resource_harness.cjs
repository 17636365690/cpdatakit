// Execute the shipped browser logic with a small DOM/fetch boundary; no UI library is replaced.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const environments = [];

class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.dataset = {}; this.listeners = {};
    this.value = ''; this.textContent = ''; this.hidden = false;
  }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  prepend(node) { node.parent = this; this.children.unshift(node); }
  after(node) {
    node.remove(); node.parent = this.parent;
    this.parent.children.splice(this.parent.children.indexOf(this) + 1, 0, node);
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); }
  contains(node) { return node === this || this.children.some(child => child.contains(node)); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  setAttribute(name, value) { (this.attributes ||= {})[name] = String(value); }
  getAttribute(name) { return this.attributes?.[name] ?? null; }
  removeAttribute(name) { if (this.attributes) delete this.attributes[name]; }
  get classList() {
    const classes = this.classes ||= new Set();
    return {add: (...names) => names.forEach(name => classes.add(name)), remove: (...names) => names.forEach(name => classes.delete(name)),
      contains: name => classes.has(name),
      toggle: (name, force = !classes.has(name)) => { if (force) classes.add(name); else classes.delete(name); return force; }};
  }
  async dispatchEvent(event) { await Promise.all((this.listeners[event.type] || []).map(fn => fn({preventDefault() {}, ...event, currentTarget: this, target: this}))); }
  async click() { await this.dispatchEvent({type: 'click'}); }
  focus() { this.focused = true; }
  cloneNode() { const copy = new Node(this.tagName); Object.assign(copy, this, {children: [...this.children]}); return copy; }
  querySelectorAll(selector) {
    const all = this.children.flatMap(node => [node, ...node.querySelectorAll('*')]);
    if (selector === '*') return all;
    if (selector === 'option') return all.filter(node => node.tagName === 'option');
    const match = selector.match(/^\[data-([a-z-]+)(?:="(.*)")?\]$/);
    if (match) {
      const key = match[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
      return all.filter(node => node.dataset[key] !== undefined && (!match[2] || node.dataset[key] === match[2]));
    }
    return all.filter(node => node.tagName === selector);
  }
  querySelector(selector) {
    if (selector === 'optgroup:last-child') return this.children.filter(node => node.tagName === 'optgroup').at(-1);
    if (selector === 'option:checked') return this.querySelectorAll('option').find(node => String(node.value) === String(this.value));
    return this.querySelectorAll(selector)[0] || null;
  }
  get options() { return this.querySelectorAll('option'); }
  get rows() { return this.querySelectorAll('tr'); }
  get selectedOptions() { return this.options.filter(node => String(node.value) === String(this.value)); }
}

const kinds = ['datasets', 'artifacts', 'schemas', 'jobs'];
function page(overrides = {}, offset = 0, counts = {}) {
  const value = {project: {id: 1}, datasets: [], artifacts: [], schemas: [], jobs: [], ...overrides};
  const totals = Object.fromEntries(kinds.map(kind => [kind, counts[kind] ?? value[kind].length]));
  value.pagination = {limit: 50, offset, counts: totals,
    has_more: Object.fromEntries(kinds.map(kind => [kind, offset + value[kind].length < totals[kind]]))};
  return value;
}

function environment(initial, responder, {authoring = false, csvIntake = false} = {}) {
  const nodes = new Map();
  for (const id of ['dataset', 'schema', 'artifacts', 'jobs', 'jobs-panel', 'check', 'operation-result', 'result-title', 'result-content',
                    'project-resources', 'slice-image', 'slice-caption', 'slice-download', 'slice-preview',
                    'workflow-status', 'output-feedback-convert',
                    'output-feedback-report', 'convert-output', 'report-output', 'mapping-json']) {
    nodes.set('#' + id, new Node(['dataset', 'schema'].includes(id) ? 'select' : 'div'));
  }
  const builtinGroup = new Node('optgroup'); const schemaGroup = new Node('optgroup');
  nodes.get('#schema').append(builtinGroup, schemaGroup);
  if (authoring) for (const id of ['draft-schema', 'schema-draft-json', 'authoring-status', 'schema-review',
                                  'draft-editor', 'save-draft', 'preview-mapping', 'mapping-preview', 'mapping-preview tbody']) {
    nodes.set('#' + id, new Node());
  }
  if (csvIntake) {
    for (const id of ['csv-preview-form', 'csv-file', 'csv-input-controls', 'csv-review-controls',
                     'csv-confirm-form', 'csv-status', 'csv-columns tbody', 'csv-confirmed',
                     'csv-delimiter', 'csv-header-row', 'csv-unit-row', 'csv-decimal',
                     'csv-encoding', 'csv-preview-button', 'csv-counts', 'csv-conventions',
                     'csv-settings-file', 'csv-settings-clear', 'csv-settings-status',
                     'csv-settings-review', 'csv-saved-controls', 'csv-import-button', 'csv-problems',
                     'csv-confirm-note', 'csv-options-toggle', 'csv-options', 'csv-options-summary',
                     'csv-raw-toggle', 'csv-raw', 'csv-source-toggle', 'csv-source-state',
                     'csv-source-editor', 'csv-keep-count']) {
      nodes.set('#' + id, new Node());
    }
    nodes.get('#csv-file').files = [{name: 'malformed.csv'}];
    for (const [id, value] of [['csv-delimiter', ';'], ['csv-header-row', '1'],
                             ['csv-unit-row', '0'], ['csv-decimal', '.'],
                             ['csv-encoding', 'utf-8-sig']]) nodes.get('#' + id).value = value;
  }
  for (const name of ['curve', 'point']) {
    const option = new Node('option'); option.value = name; option.textContent = name;
    builtinGroup.append(option);
  }
  for (const item of initial.schemas) {
    const option = new Node('option'); option.value = `schema:${item.id}`;
    option.textContent = item.label || `${item.name} · ${item.version} · #${item.id}`; schemaGroup.append(option);
  }
  nodes.get('#schema').value = 'curve';
  const forms = ['validate', 'convert', 'report'].map(operation => {
    const form = new Node('form'); form.dataset.operation = operation;
    form.action = `/api/projects/1/${operation}`;
    const button = new Node('button'); form.append(button);
    if (operation !== 'validate') {
      const output = nodes.get(`#${operation}-output`); output.name = 'output';
      output.value = operation === 'convert' ? 'results/converted.h5' : 'results/report.html';
      const force = new Node('input'); force.name = 'force'; force.type = 'checkbox'; force.value = 'true'; force.checked = false;
      form.append(output, force); form.force = force;
    }
    nodes.set(`form:${operation}`, form); return form;
  });
  nodes.get('#project-resources').textContent = JSON.stringify(initial);
  for (const item of initial.datasets) {
    const option = new Node('option'); option.value = String(item.id); option.textContent = item.relative_path;
    nodes.get('#dataset').append(option);
  }
  nodes.get('#dataset').value = String(initial.datasets[0]?.id || '');
  for (const job of initial.jobs) {
    const row = new Node('p'); row.dataset.jobId = job.id; row.dataset.jobStatus = job.status;
    nodes.get('#jobs').append(row);
  }
  const controls = kinds.map(kind => {
    const button = new Node('button'); button.dataset.loadMore = kind;
    nodes.set(`[data-load-more="${kind}"]`, button);
    nodes.set(`[data-resource-count="${kind}"]`, new Node('p'));
    return button;
  });
  const calls = [];
  const timers = new Set();
  const document = {
    body: {dataset: {projectId: '1'}},
    querySelector: selector => nodes.get(selector) || null,
    querySelectorAll: selector => {
      if (selector === '[data-load-more]') return controls;
      if (selector === '[data-job-id]') return nodes.get('#jobs').children;
      if (selector === 'form[data-operation]') return forms;
      return [];
    },
    createElement: tag => new Node(tag), createTextNode: text => { const item = new Node(); item.textContent = text; return item; }, addEventListener() {}, dispatchEvent() {},
  };
  class FormData {
    constructor(form) { this.values = new Map(); for (const node of form?.children || []) if (node.name && (node.type !== 'checkbox' || node.checked)) this.set(node.name, node.value); }
    set(name, value) { this.values.set(name, value); }
    get(name) { return this.values.get(name); }
    delete(name) { this.values.delete(name); }
    append(name, value) { this.set(name, value); }
  }
  const posted = [];
  const context = vm.createContext({document, Event: class {constructor(type) {this.type = type;}}, FormData, Blob, CSS: {escape: value => value},
    setTimeout(callback, delay, ...args) {
      const timer = setTimeout(() => { timers.delete(timer); callback(...args); }, delay);
      timers.add(timer); return timer;
    },
    clearTimeout(timer) { timers.delete(timer); clearTimeout(timer); }, console, URLSearchParams,
    setupAuthoring() {}, setupFields() {},
    fetch: async (url, options) => {
      calls.push(url); if (options?.body) posted.push(options.body);
      const reply = await responder(url, options);
      return {ok: !reply?.httpStatus || reply.httpStatus < 400, status: reply?.httpStatus || 200,
        json: async () => reply?.httpStatus ? reply.payload : reply};
    },
  });
  const directory = path.join(__dirname, '../src/cpdatakit/web/static');
  const fields = fs.readFileSync(path.join(directory, 'fields.js'), 'utf8').replace(/^export /gm, '');
  vm.runInContext(fields, context);
  const authoringCode = fs.readFileSync(path.join(directory, 'authoring.js'), 'utf8').replace(/^export /gm, '');
  vm.runInContext(authoringCode, context);
  const csvIntakeCode = fs.readFileSync(path.join(directory, 'csv-intake.js'), 'utf8').replace(/^export /gm, '');
  vm.runInContext(csvIntakeCode, context);
  const app = fs.readFileSync(path.join(directory, 'app.js'), 'utf8').replace(/^import .*;\r?\n/gm, '');
  vm.runInContext(app, context);
  const env = {nodes, calls, posted, context, timers, run: script => vm.runInContext(script, context)};
  environments.push(env);
  return env;
}

const visibleText = node => [node.textContent, ...node.children.filter(child => child.tagName !== 'details').map(visibleText)].join(' ');

// The three-row synthetic instrument export from examples/csv-intake, as returned by csv-preview.
const instrumentColumns = [
  {index: 0, source_name: '(sec)', dtype: 'integer', suggested_unit: 'sec', samples: ['0', '1', '2']},
  {index: 1, source_name: '(mm)', dtype: 'float', suggested_unit: 'mm', samples: ['0', '0.5', '1.25']},
  {index: 2, source_name: '(N)', dtype: 'integer', suggested_unit: 'N', samples: ['100', '250', '375']},
  {index: 3, source_name: '', dtype: 'integer', suggested_unit: null, samples: ['0', '0', '0']},
  {index: 4, source_name: '(MPa)', dtype: 'integer', suggested_unit: 'MPa', samples: ['20', '40', '60']},
  {index: 5, source_name: '(mm/mm)', dtype: 'float', suggested_unit: 'mm/mm', samples: ['0', '0.01', '0.02']},
];
const instrumentPreview = (overrides = {}) => ({
  source_sha256: 'a'.repeat(64), record_count: 3,
  options: {delimiter: ';', header_row: 1, unit_row: 0, decimal: '.', encoding: 'utf-8-sig'},
  columns: instrumentColumns.map(column => ({...column, samples: [...column.samples]})),
  sample_rows: [2, 3, 4].map((line, row) => ({line, cells: instrumentColumns.map(column => column.samples[row])})),
  warnings: ['Units from headers are suggestions and require explicit confirmation.'], ...overrides,
});
const importedCsv = {dataset_id: 7, schema_selector: 'schema:3', filename: 'instrument.csv · 已确认数据',
  schema_name: 'imported-csv', operation: 'csv_import'};
const validInstrument = {
  0: {target: 'time', dtype: 'float', input_unit: 's', output_unit: 's', role: 'time'},
  1: {target: 'extension', role: 'measured_quantity'},
  2: {target: 'force', dtype: 'float', output_unit: 'kN', role: 'measured_quantity'},
  4: {target: 'reported_stress', dtype: 'float', role: 'measured_quantity'},
  5: {target: 'reported_strain', output_unit: 'dimensionless', role: 'measured_quantity'},
};
const csvEnv = responder => environment(page(), (url, options) => url.includes('?limit=') ? page() : responder(url, options), {csvIntake: true});
const csvBody = env => env.nodes.get('#csv-columns tbody');
const csvRow = (env, index) => csvBody(env).children.find(row => row.dataset.index === String(index));
const csvEditor = env => csvBody(env).children.find(row => row.dataset.editorFor !== undefined);
async function previewCsv(env) { await env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'}); }
async function setControl(control, value) {
  control.value = value; await control.dispatchEvent({type: control.tagName === 'select' ? 'change' : 'input'});
}
async function setKept(env, index, checked) {
  const keep = csvRow(env, index).querySelector('[data-key="include"]');
  keep.checked = checked; await keep.dispatchEvent({type: 'change'});
}
async function openCsvEditor(env, index) { await csvRow(env, index).querySelector('[data-edit-column]').click(); return csvEditor(env); }
async function editCsvRow(env, index, values, action = 'apply') {
  const editor = await openCsvEditor(env, index);
  for (const [key, value] of Object.entries(values)) await setControl(editor.querySelector(`[data-edit="${key}"]`), value);
  if (action) await editor.querySelector(`[data-editor-${action}]`).click();
  return editor;
}
async function completeInstrument(env) {
  await setKept(env, 3, false);
  for (const [index, values] of Object.entries(validInstrument)) await editCsvRow(env, Number(index), values);
  const conventions = env.nodes.get('#csv-conventions');
  conventions.value = 'Synthetic example; units from the header row.';
  await conventions.dispatchEvent({type: 'input'});
}
async function confirmCsv(env) {
  const confirmed = env.nodes.get('#csv-confirmed');
  confirmed.checked = true; await confirmed.dispatchEvent({type: 'change'});
}
const cellText = (env, index, field) => visibleText(csvRow(env, index).querySelector(`[data-field="${field}"]`));

async function checkCsvReview(name) {
  if (name === 'csv-edit-summary') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : page());
    await previewCsv(env);
    const tbody = csvBody(env);
    assert.equal(env.nodes.get('#csv-confirm-form').hidden, false);
    assert.equal(tbody.rows.length, 6);
    assert.deepEqual(tbody.querySelectorAll('input').map(input => input.type), Array(6).fill('checkbox'),
      'Summary rows must not expose every declaration control at once');
    assert.equal(tbody.querySelectorAll('select').length, 0);
    assert.match(cellText(env, 2, 'source'), /03.*\(N\)/);
    assert.match(cellText(env, 3, 'source'), /04.*无列名/);
    assert.match(cellText(env, 2, 'target'), /column_3/);
    assert.match(cellText(env, 2, 'unit'), /N/);
    assert.match(cellText(env, 2, 'kind'), /整数.*未选用途/);
    assert.equal(csvRow(env, 2).dataset.problem, 'pending', 'Missing declarations are visible pending items');
    let editor = await openCsvEditor(env, 2);
    assert.equal(tbody.children.indexOf(editor), tbody.children.indexOf(csvRow(env, 2)) + 1,
      'Only the current field expands, directly below its summary');
    assert.equal(tbody.querySelectorAll('select').length, 2);
    assert.equal(editor.querySelector('[data-edit="target"]').value, 'column_3');
    assert.equal(editor.querySelector('[data-edit="input_unit"]').value, 'N');
    assert.equal(editor.querySelector('[data-edit="role"]').value, '');
    assert.equal(editor.querySelector('[data-edit="target"]').focused, true, 'The editor receives keyboard focus');
    assert.match(visibleText(editor), /100 \/ 250 \/ 375/, 'The editor shows this column\'s own raw samples');
    for (const index of [0, 1, 3, 4, 5]) {
      assert.equal(csvRow(env, index).querySelector('[data-edit-column]').disabled, true);
      assert.equal(csvRow(env, index).querySelector('[data-key="include"]').disabled, true);
    }
    assert.equal(env.nodes.get('#csv-confirmed').disabled, true);
    assert.equal(env.nodes.get('#csv-import-button').disabled, true, 'An open editor blocks import');
    await setControl(editor.querySelector('[data-edit="target"]'), 'discarded');
    await editor.querySelector('[data-editor-cancel]').click();
    assert.equal(csvEditor(env), undefined);
    assert.match(cellText(env, 2, 'target'), /column_3/, 'Cancel keeps the original value');
    assert.doesNotMatch(visibleText(csvRow(env, 2)), /discarded/);
    assert.equal(csvRow(env, 2).querySelector('[data-edit-column]').focused, true, 'Focus returns to the row action');
    editor = await openCsvEditor(env, 2);
    assert.equal(editor.querySelector('[data-edit="target"]').value, 'column_3');
    await setControl(editor.querySelector('[data-edit="target"]'), 'escaped');
    await editor.querySelector('[data-edit="target"]').dispatchEvent({type: 'keydown', key: 'Escape'});
    assert.equal(csvEditor(env), undefined, 'Escape cancels the editor');
    assert.match(cellText(env, 2, 'target'), /column_3/);
    await editCsvRow(env, 2, {target: 'force', dtype: 'float', output_unit: 'kN', role: 'measured_quantity'});
    assert.match(cellText(env, 2, 'target'), /force/, 'Applied values update the summary immediately');
    assert.match(cellText(env, 2, 'unit'), /N\s*→\s*kN/);
    assert.match(cellText(env, 2, 'kind'), /小数.*测量值/);
    assert.equal(csvRow(env, 2).dataset.problem, '');
    assert.equal(csvRow(env, 2).querySelector('[data-edit-column]').focused, true);
    editor = await editCsvRow(env, 5, {output_unit: 'dimensionless', role: 'measured_quantity'}, null);
    await editor.querySelector('[data-edit="role"]').dispatchEvent({type: 'keydown', key: 'Enter'});
    assert.equal(csvEditor(env), undefined, 'Enter applies the current field');
    assert.match(cellText(env, 5, 'unit'), /mm\/mm\s*→\s*无量纲/);
  } else if (name === 'csv-reconfirm') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : url.endsWith('/csv-import') ? importedCsv : page());
    await previewCsv(env);
    await completeInstrument(env);
    const confirmed = env.nodes.get('#csv-confirmed'), button = env.nodes.get('#csv-import-button');
    const conventions = env.nodes.get('#csv-conventions'), note = env.nodes.get('#csv-confirm-note');
    assert.equal(button.disabled, true, 'An unconfirmed review cannot be submitted');
    await confirmCsv(env);
    assert.equal(button.disabled, false);
    const editor = await openCsvEditor(env, 0);
    assert.equal(button.disabled, true);
    await editor.querySelector('[data-editor-cancel]').click();
    assert.equal(confirmed.checked, true, 'Cancelling without changes keeps the confirmation');
    assert.equal(button.disabled, false);
    await editCsvRow(env, 0, {target: 'time'});
    assert.equal(confirmed.checked, true, 'Applying identical values keeps the confirmation');
    await editCsvRow(env, 0, {target: 'elapsed'});
    assert.equal(confirmed.checked, false, 'A changed field invalidates the old confirmation');
    assert.equal(button.disabled, true);
    assert.equal(note.hidden, false);
    assert.match(visibleText(note), /重新核对/);
    await confirmCsv(env);
    assert.equal(note.hidden, true);
    await setKept(env, 3, true);
    assert.equal(confirmed.checked, false, 'Changing kept columns invalidates the confirmation');
    assert.equal(csvRow(env, 3).dataset.problem, 'pending', 'A newly kept column needs its own declaration');
    await confirmCsv(env);
    assert.equal(button.disabled, true, 'Pending declarations still block import');
    await setKept(env, 3, false);
    await confirmCsv(env);
    conventions.value += ' Revised.'; await conventions.dispatchEvent({type: 'input'});
    assert.equal(confirmed.checked, false, 'Editing the source description invalidates the confirmation');
    await confirmCsv(env);
    assert.equal(button.disabled, false);
    await env.nodes.get('#csv-confirm-form').dispatchEvent({type: 'submit'});
    const request = env.posted.at(-1);
    const sent = JSON.parse(request.get('columns_json'));
    assert.deepEqual(sent.map(item => item.include), [true, true, true, false, true, true]);
    assert.deepEqual(sent[0], {index: 0, include: true, target: 'elapsed', dtype: 'float', input_unit: 's', output_unit: 's', role: 'time'});
    assert.deepEqual(sent[2], {index: 2, include: true, target: 'force', dtype: 'float', input_unit: 'N', output_unit: 'kN', role: 'measured_quantity'});
    assert.equal(sent[5].output_unit, 'dimensionless');
    assert.equal(request.get('confirmed'), 'true');
    assert.match(request.get('conventions'), /Revised/);
    assert.equal(request.get('source_sha256'), 'a'.repeat(64));
    assert.equal(env.nodes.get('#csv-confirm-form').hidden, true, 'A completed import closes its review');
    assert.equal(conventions.value, '', 'Source facts are never carried to the next file');
    assert.ok(env.nodes.get('#csv-status').querySelectorAll('a').some(link => link.href.endsWith('/csv-imports/7/manifest')));
  } else if (name === 'csv-blocking') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : page());
    await previewCsv(env);
    const button = env.nodes.get('#csv-import-button'), problems = env.nodes.get('#csv-problems');
    const source = env.nodes.get('#csv-source-editor');
    await confirmCsv(env);
    assert.equal(button.disabled, true, 'Missing roles and source description block import');
    assert.match(visibleText(problems), /用途/);
    assert.match(visibleText(problems), /来源说明/);
    assert.equal(source.hidden, false, 'A missing source description is shown');
    await env.nodes.get('#csv-source-toggle').click();
    assert.equal(source.hidden, false, 'A missing source description cannot be collapsed');
    await env.nodes.get('#csv-confirm-form').dispatchEvent({type: 'submit'});
    assert.ok(!env.calls.some(url => url.endsWith('/csv-import')), 'A blocked review must not be submitted');
    for (const index of [0, 1, 2, 3, 4, 5]) await setKept(env, index, false);
    assert.match(visibleText(problems), /至少保留一列/);
    assert.match(visibleText(env.nodes.get('#csv-keep-count')), /保留 0 列/);
    assert.doesNotMatch(visibleText(problems), /用途/, 'Excluded columns need no declaration');
    for (const index of [0, 1, 2, 4, 5]) await setKept(env, index, true);
    for (const [index, values] of Object.entries(validInstrument)) await editCsvRow(env, Number(index), values);
    let editor = await editCsvRow(env, 1, {target: 'time'}, null);
    const apply = editor.querySelector('[data-editor-apply]');
    assert.equal(apply.disabled, true, 'A duplicate output field cannot be applied');
    assert.match(visibleText(editor.querySelector('[data-editor-error]')), /重复/);
    await apply.click();
    assert.ok(csvEditor(env), 'An invalid draft keeps the editor open');
    await setControl(editor.querySelector('[data-edit="target"]'), 'a/b');
    assert.equal(apply.disabled, true);
    assert.match(visibleText(editor.querySelector('[data-editor-error]')), /\//);
    await setControl(editor.querySelector('[data-edit="target"]'), '  ');
    assert.equal(apply.disabled, true, 'An empty output field cannot be applied');
    await editor.querySelector('[data-editor-cancel]').click();
    assert.match(cellText(env, 1, 'target'), /extension/);
    await editCsvRow(env, 3, {target: 'time'});
    assert.equal(csvRow(env, 3).dataset.problem, '', 'Excluded columns do not take part in duplicate checks');
    await setKept(env, 3, true);
    assert.equal(csvRow(env, 3).dataset.problem, 'invalid', 'Keeping a column can create a duplicate field');
    assert.equal(csvRow(env, 0).dataset.problem, 'invalid');
    assert.match(visibleText(problems), /重复/);
    await setKept(env, 3, false);
    await editCsvRow(env, 1, {input_unit: ''});
    assert.equal(csvRow(env, 1).dataset.problem, 'pending');
    assert.match(cellText(env, 1, 'unit'), /未填/);
    assert.match(visibleText(problems), /单位/);
    const conventions = env.nodes.get('#csv-conventions');
    conventions.value = 'Synthetic example.'; await conventions.dispatchEvent({type: 'input'});
    await confirmCsv(env);
    assert.equal(button.disabled, true, 'A numeric field without units cannot be imported');
    await editCsvRow(env, 1, {input_unit: 'mm'});
    await confirmCsv(env);
    assert.equal(button.disabled, false);
  } else if (name === 'csv-type-switch') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : page());
    await previewCsv(env);
    let editor = await openCsvEditor(env, 3);
    const control = key => editor.querySelector(`[data-edit="${key}"]`);
    await setControl(control('dtype'), 'string');
    assert.equal(control('input_unit').disabled, true, 'Text fields do not use units');
    assert.equal(control('input_unit').value, '');
    assert.equal(control('output_unit').disabled, true);
    await setControl(control('role'), 'identifier');
    await editor.querySelector('[data-editor-apply]').click();
    assert.match(cellText(env, 3, 'unit'), /不适用/);
    assert.match(cellText(env, 3, 'kind'), /文字.*标识/);
    assert.equal(csvRow(env, 3).dataset.problem, '');
    editor = await openCsvEditor(env, 3);
    await setControl(control('dtype'), 'float');
    assert.equal(control('input_unit').disabled, false);
    assert.equal(control('input_unit').value, '', 'Units are not invented when switching back to numbers');
    await editor.querySelector('[data-editor-apply]').click();
    assert.equal(csvRow(env, 3).dataset.problem, 'pending', 'A numeric field needs explicit units');
    assert.match(cellText(env, 3, 'unit'), /未填/);
    editor = await openCsvEditor(env, 2);
    await setControl(control('dtype'), 'boolean');
    assert.equal(control('input_unit').value, '');
    await editor.querySelector('[data-editor-apply]').click();
    assert.match(cellText(env, 2, 'unit'), /不适用/);
    assert.match(cellText(env, 2, 'kind'), /布尔/);
  } else if (name === 'csv-server-error') {
    let reject = true;
    const env = csvEnv(url => {
      if (url.endsWith('/csv-preview')) return instrumentPreview();
      if (url.endsWith('/csv-import')) return reject ? {httpStatus: 400, payload: {error: {code: 'csv_review_required',
        message: 'Column 3 has invalid/incompatible units', action: '请核对文件解析设置及表格中的字段、单位和用途。'}}} : importedCsv;
      return page();
    });
    await previewCsv(env);
    await completeInstrument(env);
    await editCsvRow(env, 2, {output_unit: 'MPa'});
    await confirmCsv(env);
    await env.nodes.get('#csv-confirm-form').dispatchEvent({type: 'submit'});
    const problems = env.nodes.get('#csv-problems'), button = env.nodes.get('#csv-import-button');
    assert.equal(env.nodes.get('#csv-confirm-form').hidden, false, 'A rejected import keeps the review open');
    assert.equal(csvRow(env, 2).dataset.problem, 'invalid', 'The column named by the server is marked');
    assert.match(visibleText(problems), /第 3 列/);
    assert.match(visibleText(problems), /Column 3 has invalid\/incompatible units/, 'The original diagnostic remains traceable');
    assert.match(visibleText(problems), /请核对文件解析设置/);
    assert.equal(button.disabled, true, 'An unresolved located error blocks resubmission');
    assert.equal(env.run('resourceState.datasets.length'), 0);
    reject = false;
    await editCsvRow(env, 2, {output_unit: 'kN'});
    assert.equal(csvRow(env, 2).dataset.problem, '');
    assert.doesNotMatch(visibleText(problems), /第 3 列/);
    assert.equal(env.nodes.get('#csv-confirmed').checked, false);
    await confirmCsv(env);
    await env.nodes.get('#csv-confirm-form').dispatchEvent({type: 'submit'});
    assert.equal(env.nodes.get('#csv-confirm-form').hidden, true);
  } else if (name === 'csv-preview-stale') {
    const releases = [];
    const env = csvEnv(url => url.endsWith('/csv-preview') ? new Promise(resolve => releases.push(resolve)) : page());
    const first = env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
    // Browsers deliver both input and change for one select change.
    await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'input'});
    await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'change'});
    releases[0](instrumentPreview()); await first;
    assert.equal(env.nodes.get('#csv-confirm-form').hidden, true, 'A response for old parse settings cannot open a review');
    assert.equal(csvBody(env).children.length, 0);
    assert.match(env.nodes.get('#csv-status').textContent, /重新预览/, 'Cancelling an in-flight preview is stated');
    const older = env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
    const latest = env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
    releases[2](instrumentPreview({record_count: 1, columns: [{index: 0, source_name: 'latest', dtype: 'float', suggested_unit: null, samples: ['1']}],
      sample_rows: [{line: 2, cells: ['1']}]}));
    await latest;
    releases[1](instrumentPreview()); await older;
    assert.equal(csvBody(env).rows.length, 1, 'An older preview response cannot replace the latest one');
    assert.match(cellText(env, 0, 'source'), /latest/);
  } else if (name === 'csv-raw-preview') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : page());
    await previewCsv(env);
    const raw = env.nodes.get('#csv-raw'), toggle = env.nodes.get('#csv-raw-toggle');
    assert.equal(raw.hidden, true, 'The raw preview opens on demand');
    assert.equal(toggle.hidden, false);
    await toggle.click();
    assert.equal(raw.hidden, false);
    assert.equal(toggle.getAttribute('aria-expanded'), 'true');
    const texts = raw.querySelectorAll('tr').map(row => row.children.map(cell => cell.textContent));
    assert.deepEqual(texts.at(-3), ['2', '0', '0', '100', '0', '20', '0']);
    assert.deepEqual(texts.at(-1), ['4', '2', '1.25', '375', '0', '60', '0.02']);
    assert.ok(texts.some(row => row[0] === '1' && row.includes('(sec)')), 'The header line keeps its physical line number');
    await toggle.click();
    assert.equal(raw.hidden, true);
    const legacy = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview({sample_rows: undefined}) : page());
    await previewCsv(legacy);
    assert.equal(legacy.nodes.get('#csv-raw-toggle').hidden, true, 'Column samples are never stitched into a raw table');
    assert.equal(legacy.nodes.get('#csv-raw').querySelectorAll('tr').length, 0);
  } else if (name === 'csv-source-collapse') {
    const env = csvEnv(url => url.endsWith('/csv-preview') ? instrumentPreview() : page());
    await previewCsv(env);
    const editor = env.nodes.get('#csv-source-editor'), toggle = env.nodes.get('#csv-source-toggle');
    const state = env.nodes.get('#csv-source-state'), text = env.nodes.get('#csv-conventions');
    assert.equal(editor.hidden, false);
    assert.match(visibleText(state), /必填/);
    text.value = 'Synthetic instrument export; units from the header row.'; await text.dispatchEvent({type: 'input'});
    await toggle.click();
    assert.equal(editor.hidden, true, 'A filled description may collapse');
    assert.equal(toggle.getAttribute('aria-expanded'), 'false');
    assert.match(visibleText(state), /Synthetic instrument export/, 'A collapsed description keeps a readable summary');
    await toggle.click();
    assert.equal(editor.hidden, false);
    await toggle.click();
    await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'input'});
    await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'change'});
    assert.match(env.nodes.get('#csv-status').textContent, /重新预览/, 'Both events of one change keep the invalidation notice');
    await previewCsv(env);
    assert.equal(text.value, '', 'A new file starts with its own empty description');
    assert.equal(editor.hidden, false, 'An empty description reopens automatically');
  } else {
    throw new Error(`Unknown frontend behavior: ${name}`);
  }
}

async function check(name) {
  if (name.startsWith('csv-') && !name.startsWith('csv-settings-') && name !== 'csv-error-hint') return checkCsvReview(name);
  if (name.startsWith('csv-settings-')) {
    const options = {delimiter: ',', header_row: 1, unit_row: 0, decimal: '.', encoding: 'utf-8-sig'};
    const declarations = [{index: 0, include: true, target: 'elapsed', dtype: 'float', input_unit: 's', output_unit: 's', role: 'time'},
      {index: 1, include: false}];
    const expectedRole = name === 'csv-settings-custom-role' ? 'coordinate' : 'time';
    declarations[0].role = expectedRole;
    const sourceColumns = [{index: 0, source_name: 't', dtype: 'float', suggested_unit: null},
      {index: 1, source_name: 'unused', dtype: 'string', suggested_unit: null}];
    const saved = {options, columns: declarations, source_columns: sourceColumns,
      confirmed_source_definition: 'OLD experiment and electrode', source_sha256: 'old-hash'};
    const result = {source_sha256: 'new-hash', record_count: 2, options,
      columns: sourceColumns.map(column => ({...column, samples: ['1.1', '2.2']})), warnings: [],
      settings_review: {matches: name !== 'csv-settings-drift',
        columns: name === 'csv-settings-drift' ? [] : declarations,
        changes: name === 'csv-settings-drift' ? [{field: '第 1 列名称', before: 't', after: 'potential'}] : [],
        warnings: ['请独立核对本文件的单位与来源。']}};
    const env = environment(page(), url => {
      if (url.endsWith('/csv-import')) {
        assert.equal(env.nodes.get('#csv-saved-controls').disabled, true, 'Settings changes must be disabled during import');
        return {dataset_id: 1, schema_selector: 'schema:1', filename: 'new.csv', schema_name: 'new-rules', operation: 'csv_import'};
      }
      return url.includes('?limit=') ? page() : result;
    }, {csvIntake: true});
    const upload = env.nodes.get('#csv-settings-file');
    upload.files = [{name: 'settings.json', size: 400, text: async () => JSON.stringify(saved)}];
    env.nodes.get('#csv-conventions').value = 'OLD experiment and electrode';
    env.nodes.get('#csv-confirmed').checked = true;
    await upload.dispatchEvent({type: 'change'});
    if (name === 'csv-settings-stale-load' || name === 'csv-settings-load-file-change') {
      let release;
      upload.files = [{name: 'slow.json', size: 400, text: () => new Promise(resolve => { release = resolve; })}];
      const loading = upload.dispatchEvent({type: 'change'});
      if (name === 'csv-settings-load-file-change') {
        await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'change'});
      } else await env.nodes.get('#csv-settings-clear').click();
      release(JSON.stringify(saved)); await loading;
      await env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
      assert.equal(env.posted.at(-1).get('settings_json'), undefined);
      if (name === 'csv-settings-load-file-change') {
        assert.match(visibleText(env.nodes.get('#csv-settings-status')), /取消.*重新选择/);
        assert.equal(upload.value, '');
      }
    } else if (name === 'csv-settings-invalid-load') {
      upload.files = [{name: 'broken.json', size: 1, text: async () => '{'}];
      await upload.dispatchEvent({type: 'change'});
      await env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
      assert.equal(env.posted.at(-1).get('settings_json'), undefined);
      assert.match(visibleText(env.nodes.get('#csv-settings-status')), /无法|无效/);
    } else {
      assert.equal(env.nodes.get('#csv-delimiter').value, ',');
      assert.equal(env.nodes.get('#csv-conventions').value, '', 'Old experiment facts must not be copied');
      assert.equal(env.nodes.get('#csv-confirmed').checked, false);
      await env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
      const transmitted = JSON.parse(env.posted.at(-1).get('settings_json'));
      assert.equal(transmitted.confirmed_source_definition, undefined);
      assert.equal(transmitted.source_sha256, undefined);
      const editor = await openCsvEditor(env, 0);
      const control = key => editor.querySelector(`[data-edit="${key}"]`);
      if (name === 'csv-settings-drift') {
        assert.equal(control('role').value, '');
        assert.equal(control('input_unit').value, '');
        assert.match(cellText(env, 0, 'kind'), /未选用途/, 'Drifted settings must not show old declarations');
        assert.match(visibleText(env.nodes.get('#csv-settings-review')), /potential/);
        assert.match(visibleText(env.nodes.get('#csv-settings-review')), /t/);
        await editor.querySelector('[data-editor-cancel]').click();
      } else {
        assert.equal(control('target').value, 'elapsed');
        assert.equal(control('input_unit').value, 's');
        assert.equal(control('output_unit').value, 's');
        assert.equal(control('role').value, expectedRole);
        assert.ok(control('role').options.some(option => option.value === expectedRole), 'Saved roles must be available in the real select');
        await editor.querySelector('[data-editor-cancel]').click();
        assert.match(cellText(env, 0, 'target'), /elapsed/);
        assert.match(cellText(env, 0, 'unit'), /s/);
        assert.equal(csvRow(env, 1).querySelector('[data-key="include"]').checked, false);
        env.nodes.get('#csv-conventions').value = 'new per-file facts';
        env.nodes.get('#csv-confirmed').checked = true;
        if (name === 'csv-settings-submit') {
          await env.nodes.get('#csv-confirm-form').dispatchEvent({type: 'submit'});
          const request = env.posted.at(-1);
          assert.equal(request.get('source_sha256'), 'new-hash');
          assert.equal(request.get('conventions'), 'new per-file facts');
          assert.equal(JSON.parse(request.get('settings_json')).columns[0].target, 'elapsed');
          assert.equal(JSON.parse(request.get('columns_json'))[0].role, 'time');
          const links = env.nodes.get('#csv-status').querySelectorAll('a');
          assert.ok(links.some(link => link.href === '/api/projects/1/csv-imports/1/settings'));
        }
        await env.nodes.get('#csv-input-controls').dispatchEvent({type: 'change'});
        assert.equal(env.nodes.get('#csv-conventions').value, '');
        assert.equal(env.nodes.get('#csv-confirmed').checked, false);
        assert.equal(env.nodes.get('#csv-confirm-form').hidden, true);
      }
    }
  } else if (name === 'csv-error-hint') {
    const env = environment(page(), () => ({httpStatus: 400, payload: {error: {
      code: 'csv_review_required', message: 'CSV row 3 has 5 columns; expected 6.',
      action: '请核对文件解析设置及表格中的字段、单位和用途。',
    }}}), {csvIntake: true});
    await env.nodes.get('#csv-preview-form').dispatchEvent({type: 'submit'});
    assert.match(env.nodes.get('#csv-status').textContent, /CSV row 3 has 5 columns/);
    assert.match(env.nodes.get('#csv-status').textContent, /请核对文件解析设置/,
      'CSV failures must show the corrective hint alongside the row diagnostic');
  } else if (name === 'upload-clears-authoring') {
    const initial = page({datasets: [{id: 1, relative_path: 'old.csv'}, {id: 2, relative_path: 'uploaded.csv'}]});
    const env = environment(initial, () => initial, {authoring: true});
    env.nodes.get('#mapping-json').value = '{"mappings":[{"source":"old","target":"stress"}]}';
    env.nodes.get('#schema-draft-json').value = '{"profile":"old"}';
    env.nodes.get('#mapping-preview').hidden = env.nodes.get('#draft-editor').hidden = false;
    env.nodes.get('#mapping-preview tbody').append(new Node('tr'));
    await env.run('refreshResources()');
    assert.notEqual(env.nodes.get('#mapping-json').value, '', 'Background refresh must preserve current work');
    // Ordinary upload uses this boundary to select the newly registered input.
    await env.run('refreshResources(2)');
    assert.equal(env.nodes.get('#dataset').value, '2');
    assert.equal(env.nodes.get('#mapping-json').value, '', 'Uploading another file must clear the prior mapping');
    assert.equal(env.nodes.get('#schema-draft-json').value, '');
    assert.equal(env.nodes.get('#mapping-preview').hidden, true);
    assert.equal(env.nodes.get('#draft-editor').hidden, true);
    assert.equal(env.nodes.get('#mapping-preview tbody').children.length, 0);
  } else if (name === 'authoring-reset') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}, {id: 2, relative_path: 'other.csv'}]}), () => page(), {authoring: true});
    for (const [id, value] of [['dataset', '2'], ['schema', 'point']]) {
      env.nodes.get('#mapping-json').value = '{"mappings":[{"source":"old","target":"stress"}]}';
      env.nodes.get('#schema-draft-json').value = '{"profile":"old"}';
      env.nodes.get('#mapping-preview').hidden = env.nodes.get('#draft-editor').hidden = false;
      const row = new Node('tr'); row.textContent = 'old mapped values'; env.nodes.get('#mapping-preview tbody').append(row);
      env.nodes.get('#' + id).value = value; await env.nodes.get('#' + id).dispatchEvent({type: 'change'});
      assert.equal(env.nodes.get('#mapping-json').value, '', `${id} change must clear old mappings`);
      assert.equal(env.nodes.get('#schema-draft-json').value, '', `${id} change must clear old drafts`);
      assert.equal(env.nodes.get('#mapping-preview').hidden, true);
      assert.equal(env.nodes.get('#draft-editor').hidden, true);
      assert.equal(env.nodes.get('#mapping-preview tbody').children.length, 0);
    }
  } else if (name === 'draft-stale') {
    let release; const pending = new Promise(resolve => { release = resolve; });
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}, {id: 2, relative_path: 'other.csv'}]}), () => pending, {authoring: true});
    const submitted = env.nodes.get('#draft-schema').click();
    env.nodes.get('#dataset').value = '2'; await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    env.nodes.get('#mapping-json').value = 'new mapping';
    release({value: {schema: {schema_version: '1.0', fields: [{name: 'old'}]}, review: []}}); await submitted;
    assert.equal(env.nodes.get('#schema-draft-json').value, '', 'Old file draft cannot populate the new selection');
    assert.equal(env.nodes.get('#mapping-json').value, 'new mapping');
    assert.equal(env.nodes.get('#draft-editor').hidden, true);
  } else if (name === 'authoring-save-stale') {
    let release; const pending = new Promise(resolve => { release = resolve; });
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}, {id: 2, relative_path: 'other.csv'}]}), () => pending, {authoring: true});
    env.nodes.get('#schema-draft-json').value = '{"profile":"old"}';
    const submitted = env.nodes.get('#save-draft').click();
    env.nodes.get('#dataset').value = '2'; await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    release({name: 'old', version: '1.0', id: 5, selector: 'schema:5'}); await submitted;
    assert.equal(env.nodes.get('#schema').value, 'curve', 'Saving an old draft must not rebind newly selected data');
  } else if (name === 'initial-bound-input') {
    const env = environment(page({datasets: [
      {id: 8, relative_path: 'csv-imports/a/data.h5', metadata: {csv_import: true, source_name: 'curve-A.csv', schema_selector: 'schema:77'}},
      {id: 9, relative_path: 'csv-imports/b/data.h5', metadata: {csv_import: true, source_name: 'curve-B.csv', schema_selector: 'schema:78'}},
      {id: 10, relative_path: 'results/snapshot.h5', metadata: {source_artifact_id: 45, schema: 'curve'}},
    ], schemas: [{id: 77, name: 'curve-A', version: '1.0'}]}), () => page());
    assert.match(env.nodes.get('#dataset').options[0].textContent, /curve-A.csv.*#8/);
    assert.match(env.nodes.get('#dataset').options[1].textContent, /curve-B.csv.*#9/);
    assert.match(env.nodes.get('#dataset').options[2].textContent, /转换结果.*#10/);
    assert.equal(env.nodes.get('#schema').value, 'schema:77');
    assert.match(env.nodes.get('#dataset').selectedOptions[0].textContent, /curve-A.csv.*#8/, 'The visible selector names the current input');
    env.nodes.get('#dataset').value = '9'; await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    assert.equal(env.nodes.get('#schema').value, 'schema:78', 'Bound rules outside the first catalog page must remain selectable');
  } else if (name === 'activation-refresh-race') {
    const releases = []; const initial = page({datasets: [{id: 1, relative_path: 'raw.csv'}]});
    const env = environment(initial, () => new Promise(resolve => releases.push(resolve)), {authoring: true});
    const activating = env.run('activateInput({dataset_id: 50, schema_selector: "schema:6", filename: "curve.csv · 已确认数据", schema_name: "curve-rules", operation: "csv_import"})');
    const refresh = env.run('refreshResources()');
    releases[1](initial); await refresh;
    releases[0](page({datasets: [{id: 50, relative_path: 'imports/data.h5'}]})); await activating;
    assert.equal(env.nodes.get('#dataset').value, '50', 'A newer background refresh cannot leave the old dataset with new rules');
    assert.equal(env.nodes.get('#schema').value, 'schema:6');
    assert.match(env.nodes.get('#dataset').selectedOptions[0].textContent, /curve.csv.*#50/);
    assert.equal(env.nodes.get('#mapping-json').value, '');
  } else if (name === 'activation-user-change') {
    let release; const pending = new Promise(resolve => { release = resolve; });
    const initial = page({datasets: [{id: 1, relative_path: 'raw.csv'}, {id: 2, relative_path: 'other.csv'}]});
    const env = environment(initial, () => pending, {authoring: true});
    const activating = env.run('activateInput({dataset_id: 50, schema_selector: "schema:6", filename: "converted.h5"})');
    env.nodes.get('#dataset').value = '2'; await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    env.nodes.get('#schema').value = 'point'; await env.nodes.get('#schema').dispatchEvent({type: 'change'});
    release(initial);
    assert.equal(await activating, false, 'A skipped selection is a completed import, not an activation');
    assert.equal(env.nodes.get('#dataset').value, '2', 'Pending activation cannot override a later user choice');
    assert.equal(env.nodes.get('#schema').value, 'point');
  } else if (name === 'activation-stale-context') {
    const initial = page({datasets: [{id: 1, relative_path: 'raw.csv'}, {id: 2, relative_path: 'other.csv'}]});
    const refreshed = page({datasets: [...initial.datasets, {id: 50, relative_path: 'converted.h5', metadata: {schema_selector: 'schema:6'}}]});
    const env = environment(initial, () => refreshed, {authoring: true});
    env.run('globalThis.submittedContext = selectedContext()');
    for (const id of ['2', '1']) {
      env.nodes.get('#dataset').value = id; await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    }
    const selected = await env.run('activateInput({dataset_id: 50, schema_selector: "schema:6", filename: "converted.h5"}, submittedContext)');
    assert.equal(selected, false, 'Switching away and back still supersedes the pending request');
    assert.equal(env.nodes.get('#dataset').value, '1');
    assert.equal(env.nodes.get('#schema').value, 'curve');
    assert.ok(env.nodes.get('#dataset').options.some(option => option.value === '50'), 'The completed result remains available without stealing the selection');
  } else if (name === 'activation-overlap') {
    const releases = []; const initial = page({datasets: [{id: 1, relative_path: 'raw.csv'}]});
    const env = environment(initial, () => new Promise(resolve => releases.push(resolve)), {authoring: true});
    const older = env.run('activateInput({dataset_id: 50, schema_selector: "schema:6", filename: "old.h5", artifact_id: 60})');
    const latest = env.run('activateInput({dataset_id: 51, schema_selector: "schema:7", filename: "latest.h5", artifact_id: 61})');
    releases[1](initial); assert.equal(await latest, true);
    releases[0](initial); assert.equal(await older, false);
    assert.equal(env.nodes.get('#dataset').value, '51');
    assert.equal(env.nodes.get('#schema').value, 'schema:7');
    assert.match(env.nodes.get('#dataset').selectedOptions[0].textContent, /latest.h5.*转换结果.*#51/);
  } else if (name === 'authoring-preview-current') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}]}), () => ({operation: 'preview_mapping', status: 'succeeded',
      value: {fields: [{source: 'temp_C', target: 'temperature', source_unit: 'degC', target_unit: 'K', source_dims: ['record'], target_dims: ['record'], before: [25], after: [298.15]}], validation: {valid: true, errors: [], warnings: []}}}), {authoring: true});
    await env.nodes.get('#preview-mapping').click();
    assert.match(visibleText(env.nodes.get('#mapping-preview tbody')), /temp_C.*temperature.*degC.*K.*298.15/, 'Current scientific field names and mapped values remain unchanged');
    assert.equal(env.nodes.get('#mapping-preview').hidden, false);
  } else if (name === 'mapping-scope') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}]}), () => page());
    env.context.result = {operation: 'preview_mapping', status: 'succeeded', provenance: {input_filename: 'raw.csv'}, value: {validation: {valid: true, errors: [], warnings: []}, fields: []}};
    env.run('showResult("映射预览", result, selectedContext())');
    assert.match(visibleText(env.nodes.get('#workflow-status')), /映射后/, 'Preview validates the mapped values, not the unchanged source');
    assert.match(visibleText(env.nodes.get('#result-content')), /尚未.*保存|尚未.*写出/, 'Preview cannot imply a converted file was written');
  } else if (name === 'authoring-save') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}]}), url => url.endsWith('/schemas')
      ? {name: 'custom', version: '1.0', id: 5, selector: 'schema:5'}
      : {operation: 'validate_and_summarize', status: 'succeeded', provenance: {input_filename: 'raw.csv'}, value: {validation: {valid: true, errors: [], warnings: []}}}, {authoring: true});
    await env.nodes.get('form:validate').dispatchEvent({type: 'submit'});
    env.nodes.get('#schema-draft-json').value = '{"profile":"custom","schema_version":"1.0","fields":[]}';
    env.nodes.get('#mapping-json').value = '{"mappings":[{"source":"raw","target":"value"}]}';
    await env.nodes.get('#save-draft').click();
    assert.equal(env.nodes.get('#schema').value, 'schema:5');
    assert.match(visibleText(env.nodes.get('#workflow-status')), /历史|已切换/, 'Saving and selecting a new rule invalidates the current-selection status');
    assert.match(env.nodes.get('#schema').selectedOptions[0].textContent, /custom/);
    assert.equal(env.nodes.get('#mapping-json').value, '{"mappings":[{"source":"raw","target":"value"}]}', 'Saving this draft must preserve its matching mapping');
  } else if (name === 'authoring-context') {
    let resolve;
    const pending = new Promise(done => { resolve = done; });
    const env = environment(page({datasets: [{id: 1, relative_path: 'raw.csv'}]}), () => pending, {authoring: true});
    const submitted = env.nodes.get('#preview-mapping').click();
    env.nodes.get('#schema').value = 'point';
    await env.nodes.get('#schema').dispatchEvent({type: 'change'});
    resolve({operation: 'preview_mapping', status: 'succeeded', provenance: {input_filename: 'raw.csv'},
      value: {fields: [{source: 'temp_C', target: 'temperature', source_unit: 'degC', target_unit: 'K', source_dims: ['record'], target_dims: ['record'], before: [25], after: [298.15]}], validation: {valid: true, errors: [], warnings: []}}});
    await submitted;
    assert.equal(env.nodes.get('#mapping-preview').hidden, true, 'A response from a previous selection cannot become the current mapping preview');
    assert.equal(env.nodes.get('#mapping-preview tbody').children.length, 0);
    assert.doesNotMatch(visibleText(env.nodes.get('#result-content')), /校验通过/, 'Discarding stale authoring work must not present it as a fresh result');
  } else if (name === 'validation-context') {
    let resolve;
    const pending = new Promise(done => { resolve = done; });
    const env = environment(page({datasets: [{id: 1, relative_path: 'original.csv'}, {id: 2, relative_path: 'other.csv'}]}), () => pending);
    const submitted = env.nodes.get('form:validate').dispatchEvent({type: 'submit'});
    env.nodes.get('#dataset').value = '2';
    await env.nodes.get('#dataset').dispatchEvent({type: 'change'});
    env.nodes.get('#schema').value = 'point';
    await env.nodes.get('#schema').dispatchEvent({type: 'change'});
    resolve({operation: 'validate_and_summarize', status: 'succeeded', provenance: {input_filename: 'original.csv'},
      value: {validation: {valid: false, errors: [{field: 'stress', message: 'Missing stress', code: 'missing_field', affected_records: 3}], warnings: [{field: 'strain', message: 'Extra values', code: 'extra', affected_records: 1}]},
        summary: {record_count: 3, field_count: 2, error_count: 1, warning_count: 1}}});
    await submitted;
    const result = visibleText(env.nodes.get('#result-content'));
    assert.match(result, /original.csv/, 'Result must identify the file submitted before the selection changed');
    assert.match(result, /curve/, 'Result must identify the schema actually submitted');
    assert.doesNotMatch(result, /other.csv|point/, 'A completed response cannot claim the newly selected inputs');
    assert.match(result, /错误\s*1|1\s*项错误/);
    assert.match(result, /警告\s*1|1\s*项警告/);
    assert.match(result, /记录\s*3|3\s*条记录/);
    assert.match(visibleText(env.nodes.get('#workflow-status')), /历史|已切换/, 'Outdated validation must remain explicitly historical');
    assert.match(env.nodes.get('#dataset').selectedOptions[0].textContent, /other.csv/);
    assert.equal(env.posted[0].get('dataset_id'), '1');
    assert.equal(env.posted[0].get('schema'), 'curve');
  } else if (name === 'validation-history') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'sample.csv'}]}), () => ({operation: 'validate_and_summarize', status: 'succeeded', provenance: {input_filename: 'sample.csv'}, value: {validation: {valid: true, errors: [], warnings: []}, summary: {record_count: 2, field_count: 2}}}));
    await env.nodes.get('form:validate').dispatchEvent({type: 'submit'});
    env.nodes.get('#schema').value = 'point';
    await env.nodes.get('#schema').dispatchEvent({type: 'change'});
    assert.match(visibleText(env.nodes.get('#workflow-status')), /历史|已切换/);
    assert.match(visibleText(env.nodes.get('#result-content')), /curve/);
    assert.match(env.nodes.get('#schema').selectedOptions[0].textContent, /point/);
  } else if (name === 'output-conflict') {
    let retry = false;
    const env = environment(page({datasets: [{id: 1, relative_path: 'sample.csv'}]}), url => retry
      ? (url.includes('/api/jobs/') ? {id: 'renamed', operation: 'convert', status: 'succeeded'} : url.endsWith('/convert') ? {job_id: 'renamed'} : page())
      : ({httpStatus: 409,
      payload: {error: {code: 'overwrite_confirmation', message: 'The requested output already exists.', action: 'Confirm overwrite explicitly before retrying.'}}}));
    await env.nodes.get('form:convert').dispatchEvent({type: 'submit'});
    const feedback = visibleText(env.nodes.get('#output-feedback-convert'));
    assert.match(feedback, /results\/converted.h5/, 'Conflict must name the requested project path');
    assert.match(feedback, /更名|修改.*路径|更换.*名称/);
    assert.match(feedback, /覆盖/);
    assert.equal(env.nodes.get('#convert-output').focused, true, 'Conflict should direct the user to the output path');
    assert.equal(env.nodes.get('form:convert').force.checked, false, 'Conflict cannot authorize overwrite');
    assert.equal(env.calls.length, 1, 'Conflict must not retry automatically');
    assert.equal(env.posted[0].get('force'), undefined);
    retry = true;
    env.nodes.get('#convert-output').value = 'results/renamed.h5';
    await env.nodes.get('form:convert').dispatchEvent({type: 'submit'});
    assert.notEqual(env.nodes.get('#output-feedback-convert').className, 'error', 'An accepted renamed output clears the old conflict styling');
    assert.match(visibleText(env.nodes.get('#output-feedback-convert')), /results\/renamed.h5/);
    assert.equal(env.posted[1].get('force'), undefined, 'A rename retry still must not request overwrite');
  } else if (name === 'artifact-actions') {
    const env = environment(page({artifacts: [{id: 999, relative_path: 'results/report.html', kind: 'report'}]}), () => page());
    env.context.result = {operation: 'build_report', status: 'succeeded', artifact: 'results/report.html', provenance: {artifact_id: 17, input_filename: 'source.nc'}, value: {report: {schema: {profile: 'measured', schema_version: '2.0'}, statistics: {dimensions: {time: 3, y: 2, x: 4}, fields: {temperature: {unit: 'K', dims: ['time', 'y', 'x'], shape: [3, 2, 4]}}}, validation: {valid: true, errors: [], warnings: []}}}};
    env.run('showResult("报告完成", result)');
    assert.match(visibleText(env.nodes.get('#result-content')), /time = 3.*y = 2.*x = 4/, 'Nested report statistics must retain their dimension context');
    const links = env.nodes.get('#result-content').querySelectorAll('a');
    assert.ok(links.some(link => link.href === '/api/projects/1/artifacts/17'), 'View must use the exact registered artifact identity');
    assert.ok(links.some(link => link.href === '/api/projects/1/artifacts/17?download=true'));
    assert.ok(!links.some(link => link.href.includes('/999')));
    env.run('delete result.provenance.artifact_id; showResult("旧报告", result)');
    assert.equal(env.nodes.get('#result-content').querySelectorAll('a').length, 0, 'A same-named catalog entry is not proof of result identity');
  } else if (name === 'pending-persistence') {
    const job = {id: 'unsaved', operation: 'report', status: 'succeeded', active: false,
      persistence: {state: 'pending', evidence_saved: true}};
    const env = environment(page({jobs: [job]}), () => page({jobs: [{...job, persistence: {state: 'saved'}}]}));
    const row = () => env.nodes.get('#jobs').querySelector('[data-job-id="unsaved"]');
    assert.ok(row().children.some(node => node.dataset.persistence === 'pending' && node.textContent.trim()), 'Unpersisted results must be visibly distinguished from durable results');
    assert.deepEqual(env.calls, [], 'Persistence recovery is independent of browser detail polling');
    await env.run('refreshResources()');
    assert.ok(!row().children.some(node => node.dataset.persistence === 'pending'), 'A saved result clears the pending notice');
  } else if (name === 'active-history') {
    const active = {id: 'long', operation: 'report', status: 'running', active: true};
    const history = Array.from({length: 50}, (_, i) => ({id: `old-${i}`, status: 'succeeded'}));
    let finish, completed = false;
    const pending = new Promise(resolve => { finish = resolve; });
    const env = environment(page({jobs: history, active_jobs: [active]}, 0, {jobs: 62}), url => {
      if (url === '/api/jobs/long') return pending;
      if (url === '/api/jobs/long/cancel') return {status: 'running'};
      if (url.includes('offset=50')) return page({jobs: [active], active_jobs: [active]}, 50, {jobs: 62});
      return page({jobs: history, active_jobs: completed ? [] : [active]}, 0, {jobs: 62});
    });
    const rows = () => env.nodes.get('#jobs').querySelectorAll('[data-job-id="long"]');
    assert.equal(rows().length, 1, 'A fresh page must display an active job outside the history page');
    await rows()[0].querySelector('button').click();
    assert.ok(env.calls.includes('/api/jobs/long/cancel'));
    await env.run('refreshResources()');
    await env.nodes.get('[data-load-more="jobs"]').click();
    assert.equal(rows().length, 1, 'History and active rows must be deduplicated');
    assert.equal(env.calls.filter(url => url === '/api/jobs/long').length, 1);
    completed = true;
    finish({...active, status: 'cancelled', active: false});
    await new Promise(resolve => setTimeout(resolve, 150));
    assert.equal(rows().length, 1);
    assert.equal(rows()[0].dataset.jobStatus, 'cancelled');
    assert.equal(env.run('watching.size'), 0, 'Completion must stop polling even outside the current history page');
  } else if (name === 'terminal-refresh-race') {
    const active = {id: 'long', operation: 'report', status: 'running', active: true};
    let releaseDetail, releasePage, pageEntered;
    const detail = new Promise(resolve => { releaseDetail = resolve; });
    const pageReady = new Promise(resolve => { pageEntered = resolve; });
    const pendingPage = new Promise(resolve => { releasePage = resolve; });
    const env = environment(page(), url => {
      if (url === '/api/jobs/long') return detail;
      pageEntered(); return pendingPage;
    });
    const following = env.run('followJob("long")');
    const refreshing = env.run('queueResourceRefresh()');
    await pageReady;
    releaseDetail({...active, status: 'succeeded', active: false});
    await new Promise(resolve => setImmediate(resolve));
    const row = () => env.nodes.get('#jobs').querySelector('[data-job-id="long"]');
    assert.equal(row().dataset.jobStatus, 'succeeded', 'The detail response establishes the terminal status');
    releasePage(page({jobs: [active], active_jobs: [active]}));
    await Promise.all([following, refreshing]);
    assert.equal(row().dataset.jobStatus, 'succeeded', 'An older active snapshot cannot regress a terminal row');
    assert.equal(row().querySelector('button').textContent, '查看详情');
    assert.equal(env.run('watching.size'), 0);
    env.run('renderJobs()');
    assert.equal(row().dataset.jobStatus, 'succeeded', 'Re-rendering must retain the observed terminal status');
    assert.equal(env.calls.filter(url => url === '/api/jobs/long').length, 1, 'A terminal job must not restart polling');
  } else if (name === 'stale-running') {
    const stale = {id: 'old-session', operation: 'report', status: 'running', active: false};
    const env = environment(page({jobs: [stale], active_jobs: []}), () => ({...stale, status: 'failed'}));
    assert.deepEqual(env.calls, [], 'Persisted running rows must not start live polling');
    const button = env.nodes.get('#jobs').children[0].querySelector('button');
    assert.equal(button.textContent, '查看详情');
    await button.click();
    assert.deepEqual(env.calls, ['/api/jobs/old-session']);
  } else if (name === 'historical') {
    const jobs = Array.from({length: 50}, (_, i) => ({id: `old-${i}`, operation: 'convert', status: 'succeeded'}));
    const env = environment(page({jobs}), url => ({...jobs[0], result: {message: 'Loaded details'}}));
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.deepEqual(env.calls, [], 'Opening project must not poll historical completed jobs');
    const button = env.nodes.get('#jobs').children[0].querySelector('button');
    assert.ok(button, 'Terminal job should offer on-demand details');
    await button.click();
    assert.deepEqual(env.calls, ['/api/jobs/old-0']);
  } else if (name === 'jobs-attention') {
    const quiet = environment(page({jobs: [{id: 'done', operation: 'report', status: 'succeeded', active: false}]}), () => page());
    assert.ok(!quiet.nodes.get('#jobs-panel').open, 'Completed history stays behind a secondary entry');
    const pending = environment(page({jobs: [{id: 'unsaved', operation: 'report', status: 'succeeded', active: false,
      persistence: {state: 'pending'}}]}), () => page());
    assert.equal(pending.nodes.get('#jobs-panel').open, true, 'A result waiting to be saved cannot be folded away');
    let finish;
    const active = {id: 'live', operation: 'convert', status: 'running', active: true};
    const running = environment(page({jobs: [], active_jobs: [active]}), url => url === '/api/jobs/live'
      ? new Promise(resolve => { finish = resolve; }) : page());
    assert.equal(running.nodes.get('#jobs-panel').open, true, 'Running jobs show their progress and cancel action');
    finish({...active, status: 'failed', active: false, error: 'stopped'});
    await new Promise(resolve => setTimeout(resolve, 150));
    assert.equal(running.nodes.get('#jobs').querySelector('[data-job-id="live"]').dataset.jobStatus, 'failed');
  } else if (name === 'paging-quiet') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'one.csv'}]}), () => page());
    assert.equal(env.nodes.get('[data-resource-count="datasets"]').hidden, true, 'Complete lists need no paging text');
    assert.equal(env.nodes.get('[data-load-more="datasets"]').hidden, true);
    const more = environment(page({datasets: [{id: 2, relative_path: 'two.csv'}]}, 0, {datasets: 60}), () => page());
    assert.equal(more.nodes.get('[data-resource-count="datasets"]').hidden, false);
    assert.match(more.nodes.get('[data-resource-count="datasets"]').textContent, /共 60/);
  } else if (name === 'check-visibility') {
    const env = environment(page(), () => page({datasets: [{id: 3, relative_path: 'uploaded.csv'}]}));
    assert.equal(env.nodes.get('#check').hidden, true, 'Checks are not offered before any data exists');
    await env.run('refreshResources(3)');
    assert.equal(env.nodes.get('#check').hidden, false);
    assert.equal(env.nodes.get('#dataset').value, '3');
  } else if (name === 'selection') {
    const initial = page({datasets: [{id: 1, relative_path: 'old.csv'}]});
    const recent = page({datasets: [{id: 100, relative_path: 'new.csv'}]}, 0, {datasets: 100});
    const env = environment(initial, () => recent);
    await env.run('refreshResources()');
    assert.equal(env.nodes.get('#dataset').value, '1');
    assert.ok(env.nodes.get('#dataset').options.some(option => String(option.value) === '1'));
    assert.match(env.calls[0], /limit=50/);
    assert.match(env.calls[0], /newest_first=true/);
  } else if (name === 'load-more') {
    const first = Array.from({length: 50}, (_, i) => ({id: 100-i, relative_path: `data-${100-i}.csv`}));
    const next = page({datasets: [{id: 50, relative_path: 'data-50.csv'}]}, 50, {datasets: 51});
    const env = environment(page({datasets: first}, 0, {datasets: 51}), () => next);
    const button = env.nodes.get('[data-load-more="datasets"]');
    await button.click();
    assert.match(env.calls[0] || '', /offset=50/);
    assert.equal(env.nodes.get('#dataset').options.length, 51);
    assert.equal(button.hidden, true);
  } else if (name === 'slice') {
    const env = environment(page(), () => page());
    const result = {operation: 'plot_scientific_slice', status: 'succeeded', provenance: {artifact_id: 99},
      artifact: 'results/old.png', value: {variable: 'temperature', unit: 'K', slice: {}, shape: [2, 2], cmap: 'viridis'}};
    env.context.result = result;
    env.run('showSliceResult(result, {project: {id: 1}, artifacts: []})');
    assert.equal(env.nodes.get('#slice-image').src, '/api/projects/1/artifacts/99');
    assert.equal(env.nodes.get('#slice-preview').hidden, false);
  } else if (name === 'coalesce') {
    const env = environment(page(), url => url.startsWith('/api/jobs/')
      ? {id: url.split('/').at(-1), operation: 'convert', status: 'succeeded', result: {message: 'finished'}}
      : page());
    await env.run('Promise.all([followJob("new-a"), followJob("new-b")])');
    assert.equal(env.calls.filter(url => url.startsWith('/api/projects/')).length, 1,
      'Simultaneous completions should share one bounded resource refresh');
  } else if (name === 'stale-page') {
    const first = Array.from({length: 50}, (_, i) => ({id: 100-i, relative_path: `data-${100-i}.csv`}));
    const latest = Array.from({length: 50}, (_, i) => ({id: 200-i, relative_path: `data-${200-i}.csv`}));
    let release;
    const env = environment(page({datasets: first}, 0, {datasets: 100}), url => url.includes('offset=50')
      ? new Promise(resolve => { release = resolve; })
      : page({datasets: latest}, 0, {datasets: 150}));
    const pending = env.nodes.get('[data-load-more="datasets"]').click();
    await Promise.resolve();
    await env.run('refreshResources()');
    release(page({datasets: [{id: 50, relative_path: 'old-page.csv'}]}, 50, {datasets: 100}));
    await pending;
    assert.ok(!env.nodes.get('#dataset').options.some(option => String(option.value) === '50'));
    assert.match(env.nodes.get('[data-resource-count="datasets"]').textContent, /共 150/);
  } else if (name === 'schema-selection') {
    const env = environment(page(), () => page());
    const selected = new Node('option'); selected.value = 'schema:99'; selected.textContent = 'Thermal · 2.0 · #99';
    env.nodes.get('#schema').querySelector('optgroup:last-child').append(selected);
    env.nodes.get('#schema').value = 'schema:99';
    await env.run('refreshResources()');
    assert.equal(env.nodes.get('#schema').value, 'schema:99');
    assert.equal(env.nodes.get('#schema').selectedOptions[0].textContent, 'Thermal · 2.0 · #99');
  } else if (name === 'slice-legacy') {
    const env = environment(page(), () => page());
    env.context.result = {operation: 'plot_scientific_slice', status: 'succeeded', artifact: 'results/old.png',
      value: {variable: 'temperature', unit: 'K', slice: {}, shape: [2, 2], cmap: 'viridis'}};
    env.run('showSliceResult(result, {project: {id: 1}, artifacts: [{id: 11, relative_path: "results/old.png"}]})');
    assert.equal(env.nodes.get('#slice-image').src, '/api/projects/1/artifacts/11');
  } else {
    throw new Error(`Unknown frontend behavior: ${name}`);
  }
}

async function main() {
  const behaviors = process.argv.slice(2);
  if (!behaviors.length) throw new Error('At least one frontend behavior is required');
  const emit = value => console.log(JSON.stringify(value));
  emit({phase: 'ready', node: process.version, platform: process.platform});
  for (const behavior of behaviors) {
    environments.length = 0;
    const started = performance.now();
    emit({phase: 'started', behavior});
    await check(behavior);
    emit({phase: 'asserted', behavior, ms: performance.now() - started});
    // Let the real browser callbacks and polling finish. Never force process
    // exit, unref timers, or discard a late failure to obtain a passing result.
    while (environments.some(env => env.timers.size || env.run('watching.size'))) {
      await new Promise(resolve => setTimeout(resolve, 1));
    }
    emit({phase: 'passed', behavior, ms: performance.now() - started,
      pending_timers: environments.reduce((total, env) => total + env.timers.size, 0),
      watching: environments.reduce((total, env) => total + env.run('watching.size'), 0)});
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
