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
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter(node => node !== this); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  setAttribute(name, value) { (this.attributes ||= {})[name] = value; }
  get classList() { return {toggle() {}}; }
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
  for (const id of ['dataset', 'schema', 'artifacts', 'jobs', 'operation-result', 'result-title', 'result-content',
                    'project-resources', 'slice-image', 'slice-caption', 'slice-download', 'slice-preview',
                    'current-dataset', 'current-schema', 'workflow-status', 'output-feedback-convert',
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
                     'csv-encoding', 'csv-preview-button', 'csv-counts', 'csv-conventions']) {
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
    createElement: tag => new Node(tag), addEventListener() {}, dispatchEvent() {},
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

async function check(name) {
  if (name === 'csv-error-hint') {
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
    assert.match(visibleText(env.nodes.get('#current-dataset')), /curve-A.csv.*#8/);
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
    assert.match(visibleText(env.nodes.get('#current-schema')), /custom/);
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
    assert.match(visibleText(env.nodes.get('#current-dataset')), /other.csv/);
    assert.equal(env.posted[0].get('dataset_id'), '1');
    assert.equal(env.posted[0].get('schema'), 'curve');
  } else if (name === 'validation-history') {
    const env = environment(page({datasets: [{id: 1, relative_path: 'sample.csv'}]}), () => ({operation: 'validate_and_summarize', status: 'succeeded', provenance: {input_filename: 'sample.csv'}, value: {validation: {valid: true, errors: [], warnings: []}, summary: {record_count: 2, field_count: 2}}}));
    await env.nodes.get('form:validate').dispatchEvent({type: 'submit'});
    env.nodes.get('#schema').value = 'point';
    await env.nodes.get('#schema').dispatchEvent({type: 'change'});
    assert.match(visibleText(env.nodes.get('#workflow-status')), /历史|已切换/);
    assert.match(visibleText(env.nodes.get('#result-content')), /curve/);
    assert.match(visibleText(env.nodes.get('#current-schema')), /point/);
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
