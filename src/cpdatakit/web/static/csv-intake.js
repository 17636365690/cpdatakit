// CSV intake: preview, summary-first field review with one-row editing, explicit confirmation.
const TYPES = {float: '小数', integer: '整数', string: '文字', boolean: '布尔'};
const ROLES = [['time', '时间'], ['measured_quantity', '测量值'], ['simulated_quantity', '模拟值'],
  ['identifier', '标识'], ['category', '类别'], ['custom', '其他']];
const ROLE_LABELS = Object.fromEntries(ROLES);
const ROLE_OPTIONS = [['', '请选择'], ...ROLES.map(([id, label]) => [id, id === 'custom' ? '其他（在来源说明中写明）' : label])];
const PREVIEW_WARNINGS = {
  'Only one column was read; check the delimiter before confirming fields.': '只读到一列，请检查分隔符。',
  // Shown once in the counts line; the confirmation covers every unit.
  'Units from headers are suggestions and require explicit confirmation.': '',
};
const SERVER_HINTS = [
  [/has invalid\/incompatible units/, 'unit', '单位无法识别或不能换算'],
  [/requires explicit input\/output unit/, 'unit', '需填写来源和输出单位'],
  [/units apply only to numeric fields/, 'unit', '文字或布尔列不使用单位'],
  [/requires explicit role/, 'kind', '需选择用途'],
  [/requires explicit (?:target|dtype)/, 'target', '需填写字段名和类型'],
  [/must be a flat field name/, 'target', '字段名不能包含 /，也不能是 . 或 ..'],
  [/Duplicate target field/, 'target', '输出字段名重复'],
];
const DECLARATION_KEYS = ['target', 'dtype', 'input_unit', 'output_unit', 'role'];

function node(tag, text, className) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  if (className) value.className = className;
  return value;
}

const numeric = dtype => dtype === 'float' || dtype === 'integer';
const unitText = unit => unit === 'dimensionless' ? '无量纲' : unit;

function errorMessage(error) {
  const action = error.payload?.error?.action;
  return action ? `${error.message} ${action}` : error.message;
}

// Server diagnostics name one-based columns ("Column 3 ...", "CSV row 4, column 3 ...").
function describeServerError(error) {
  const message = error.message || '';
  const located = /\b(?:CSV row (\d+), )?column (\d+)\b/i.exec(message);
  let hint = '';
  let field = 'target';
  if (located?.[1]) {
    hint = `原文件第 ${located[1]} 行的值不能按所选类型或单位读取`;
    field = 'kind';
  } else {
    const known = SERVER_HINTS.find(([pattern]) => pattern.test(message));
    if (known) [, field, hint] = known;
  }
  return {index: located ? Number(located[2]) - 1 : null, field, hint, message,
    action: error.payload?.error?.action || ''};
}

export function setupCsvIntake({request, activateInput, showResult, selectedContext}) {
  const $ = id => document.querySelector(`#${id}`);
  const form = $('csv-preview-form');
  if (!form) return;
  const project = document.body.dataset.projectId;
  const file = $('csv-file');
  const settings = $('csv-input-controls');
  const reviewControls = $('csv-review-controls');
  const review = $('csv-confirm-form');
  const status = $('csv-status');
  const tbody = document.querySelector('#csv-columns tbody');
  const confirmed = $('csv-confirmed');
  const conventions = $('csv-conventions');
  const importButton = $('csv-import-button');
  const problemList = $('csv-problems');
  const confirmNote = $('csv-confirm-note');
  const settingsFile = $('csv-settings-file');
  const settingsStatus = $('csv-settings-status');
  const settingsReview = $('csv-settings-review');
  const savedControls = $('csv-saved-controls');
  const optionsToggle = $('csv-options-toggle');
  const optionsPanel = $('csv-options');
  const optionsSummary = $('csv-options-summary');
  const rawToggle = $('csv-raw-toggle');
  const raw = $('csv-raw');
  const sourceToggle = $('csv-source-toggle');
  const sourceState = $('csv-source-state');
  const sourceEditor = $('csv-source-editor');
  const keepCount = $('csv-keep-count');
  let preview;
  let savedSettings = null;
  let settingsLoading = false;
  let generation = 0;
  let pendingPreview = null;
  let declarations = [];
  let editing = null;
  let editor = null;
  let importIssue = null;
  let importing = false;
  let sourceOpen = true;

  function setStatus(text = '', kind = '') {
    status.replaceChildren();
    status.textContent = text;
    status.dataset.kind = kind;
  }
  function options() {
    const delimiter = $('csv-delimiter').value;
    return {delimiter: delimiter === 'tab' ? '\t' : delimiter,
      header_row: Number($('csv-header-row').value),
      unit_row: Number($('csv-unit-row').value),
      decimal: $('csv-decimal').value,
      encoding: $('csv-encoding').value};
  }
  function describeOptions() {
    const value = options();
    return [`${{',': '逗号', ';': '分号', '\t': '制表符'}[value.delimiter] || value.delimiter}分隔`,
      value.encoding === 'gb18030' ? 'GB18030' : 'UTF-8',
      value.header_row ? `表头第 ${value.header_row} 行` : '无表头',
      value.unit_row ? `单位第 ${value.unit_row} 行` : '无单位行',
      value.decimal === ',' ? '小数逗号' : '小数点'].join(' · ');
  }
  function refreshOptionsSummary() { if (optionsSummary) optionsSummary.textContent = describeOptions(); }
  function showOptions(open) {
    if (!optionsToggle) return;
    optionsPanel.hidden = !open;
    if (savedControls) savedControls.hidden = !open;
    optionsToggle.setAttribute('aria-expanded', String(open));
  }
  optionsToggle?.addEventListener('click', () => showOptions(optionsPanel.hidden));

  function cancelSettingsLoad() {
    if (!settingsLoading) return;
    settingsLoading = false; settingsFile.value = '';
    settingsStatus.textContent = '设置载入已取消，请重新选择设置文件。';
  }
  function resetReview() {
    preview = null; declarations = []; editing = null; editor = null; importIssue = null;
    review.hidden = true; confirmed.checked = false; conventions.value = ''; sourceOpen = true;
    if (confirmNote) confirmNote.hidden = true;
    settingsReview?.replaceChildren(); tbody.replaceChildren(); raw?.replaceChildren();
  }
  // Any change of file or parsing options makes the previous preview and its review obsolete.
  // A select fires both input and change, so the notice must survive the repeated call.
  function invalidate() {
    const hadPreview = Boolean(preview) || !review.hidden || pendingPreview !== null;
    cancelSettingsLoad();
    generation++;
    resetReview();
    if (hadPreview) setStatus('文件或解析设置已更改，请重新预览。', 'stale');
    else if (status.dataset.kind !== 'stale') setStatus('');
    refreshOptionsSummary();
  }
  settings.addEventListener('input', invalidate);
  settings.addEventListener('change', invalidate);
  settingsFile?.addEventListener('change', async () => {
    const chosen = settingsFile.files[0];
    invalidate(); savedSettings = null;
    const current = generation;
    if (!chosen) { settingsStatus.textContent = ''; return; }
    settingsLoading = true;
    settingsStatus.textContent = '正在载入设置…';
    try {
      if (chosen.size > 1024 * 1024) throw new Error('设置文件超过 1 MiB。');
      const value = JSON.parse(await chosen.text());
      if (current !== generation) return;
      if (!value || typeof value !== 'object' || Array.isArray(value) ||
          !value.options || typeof value.options !== 'object' || Array.isArray(value.options) ||
          !Array.isArray(value.columns)) throw new Error('需要包含 options 和 columns 的设置文件。');
      const opts = {delimiter: ',', header_row: 1, unit_row: 0, decimal: '.', encoding: 'utf-8-sig', ...value.options};
      const selectors = {delimiter: ['csv-delimiter', [',', ';', '\t']],
        decimal: ['csv-decimal', ['.', ',']], encoding: ['csv-encoding', ['utf-8-sig', 'gb18030']]};
      for (const [key, [, allowed]] of Object.entries(selectors)) {
        if (!allowed.includes(opts[key])) throw new Error('解析选项无效。');
      }
      for (const key of ['header_row', 'unit_row']) {
        if (!Number.isSafeInteger(opts[key]) || opts[key] < 0) throw new Error('行号无效。');
      }
      savedSettings = {options: value.options, columns: value.columns};
      if (value.source_columns !== undefined) savedSettings.source_columns = value.source_columns;
      for (const [key, [id]] of Object.entries(selectors)) $(id).value = opts[key] === '\t' ? 'tab' : opts[key];
      $('csv-header-row').value = String(opts.header_row);
      $('csv-unit-row').value = String(opts.unit_row);
      refreshOptionsSummary();
      settingsStatus.textContent = `已载入 ${chosen.name}。请预览当前文件核对差异；来源说明需为本文件重新填写。`;
    } catch (error) {
      if (current === generation) settingsStatus.textContent = `无法载入设置：${error.message}`;
    }
    finally { if (current === generation) settingsLoading = false; }
  });
  $('csv-settings-clear')?.addEventListener('click', () => {
    invalidate(); savedSettings = null; settingsFile.value = '';
    settingsStatus.textContent = '已取消设置复用。当前解析设置保留，请重新预览。';
  });

  function renderSettingsReview(result) {
    if (!settingsReview) return;
    settingsReview.replaceChildren();
    if (!result) return;
    const [scope, ...specific] = result.warnings || [];
    settingsReview.append(node('p', result.matches
      ? '结构与已载入设置一致，已填入此前确认的声明。请核对本文件的实际含义。'
      : '结构与已载入设置不同，未套用旧声明。请按当前文件重新确认。', result.matches ? 'note' : 'attention'));
    if (result.changes.length) {
      const table = node('table', undefined, 'diff-table');
      const head = node('thead'); const headRow = node('tr');
      for (const label of ['变化项', '保存的设置', '当前文件']) headRow.append(node('th', label));
      head.append(headRow);
      const body = node('tbody');
      const display = value => value === null || value === undefined ? '未声明' : typeof value === 'object' ? JSON.stringify(value) : String(value);
      const labels = {'options.delimiter': '分隔符', 'options.header_row': '表头行', 'options.unit_row': '独立单位行',
        'options.decimal': '小数符号', 'options.encoding': '文件编码', 'source_columns.length': '列数', 'source_columns': '原始列记录'};
      for (const change of result.changes) {
        const row = node('tr');
        const column = /^source_columns\[(\d+)\]\.(\w+)$/.exec(change.field);
        const label = column ? `第 ${Number(column[1]) + 1} 列 · ${{index: '位置', source_name: '名称', dtype: '检测类型', suggested_unit: '单位提示'}[column[2]] || column[2]}` : labels[change.field] || change.field;
        for (const value of [label, display(change.before), display(change.after)]) row.append(node('td', value));
        body.append(row);
      }
      table.append(head, body);
      const wrap = node('div', undefined, 'table-wrap'); wrap.append(table);
      settingsReview.append(wrap);
    }
    for (const warning of specific) settingsReview.append(node('p', warning, 'attention'));
    if (scope) {
      const details = node('details', undefined, 'inline-details');
      details.append(node('summary', '核对范围'), node('p', scope, 'note'));
      settingsReview.append(details);
    }
  }

  function renderRaw(result) {
    if (!raw || !rawToggle) return;
    raw.replaceChildren(); raw.hidden = true;
    rawToggle.setAttribute('aria-expanded', 'false');
    // Only records the parser returns as aligned rows are shown; column samples are never stitched together.
    const records = Array.isArray(result.sample_rows) ? result.sample_rows : [];
    rawToggle.hidden = !records.length;
    if (!records.length) return;
    const table = node('table', undefined, 'raw-table');
    const head = node('thead'); const headRow = node('tr');
    headRow.append(node('th', '行'));
    for (const column of result.columns) {
      const cell = node('th', String(column.index + 1)); cell.setAttribute('scope', 'col'); headRow.append(cell);
    }
    head.append(headRow);
    const body = node('tbody');
    const line = (number, cells, className) => {
      const row = node('tr', undefined, className);
      const label = node('th', String(number)); label.setAttribute('scope', 'row');
      row.append(label);
      for (const cell of cells) row.append(node('td', cell));
      body.append(row);
    };
    if (result.options?.header_row) line(result.options.header_row, result.columns.map(column => column.source_name), 'raw-header');
    for (const record of records) line(record.line, record.cells);
    table.append(head, body);
    const wrap = node('div', undefined, 'table-wrap'); wrap.append(table);
    raw.append(wrap, node('p', `原文件前 ${records.length} 条记录。左列为原文件行号，单元格文本未做类型转换。`, 'note'));
  }
  rawToggle?.addEventListener('click', () => {
    raw.hidden = !raw.hidden;
    rawToggle.setAttribute('aria-expanded', String(!raw.hidden));
  });

  function initialDeclarations(columns, saved = []) {
    return columns.map(column => {
      const prior = saved.find(item => item.index === column.index);
      const proposed = column.source_name && !column.suggested_unit ? column.source_name : `column_${column.index + 1}`;
      const item = {index: column.index, include: prior ? prior.include : true,
        target: prior?.target ?? proposed, dtype: prior?.dtype ?? column.dtype,
        input_unit: prior?.input_unit ?? column.suggested_unit ?? '',
        output_unit: prior?.output_unit ?? column.suggested_unit ?? '', role: prior?.role ?? ''};
      if (!numeric(item.dtype)) item.input_unit = item.output_unit = '';
      return item;
    });
  }
  const columnFor = index => preview.result.columns.find(column => column.index === index);
  const rowFor = index => tbody.querySelector(`[data-index="${index}"]`);

  // Generic declaration checks only; unit validity and conversion are decided by the server.
  function problemsFor(item, all = declarations, includeServer = true) {
    if (!item.include) return [];
    const issues = [];
    const target = item.target.trim();
    if (!target) issues.push({field: 'target', level: 'invalid', text: '请填写字段名'});
    else if (/[/\0]/.test(target) || target === '.' || target === '..') {
      issues.push({field: 'target', level: 'invalid', text: '字段名不能包含 /，也不能是 . 或 ..'});
    } else if (all.some(other => other.index !== item.index && other.include && other.target.trim() === target)) {
      issues.push({field: 'target', level: 'invalid', text: '字段名重复'});
    }
    if (numeric(item.dtype) && (!item.input_unit.trim() || !item.output_unit.trim())) {
      issues.push({field: 'unit', level: 'pending', text: '需填写来源和输出单位'});
    }
    if (!item.role) issues.push({field: 'kind', level: 'pending', text: '需选择用途'});
    if (includeServer && importIssue?.index === item.index) {
      issues.push({field: importIssue.field, level: 'invalid', text: importIssue.hint || '导入时被拒绝'});
    }
    return issues;
  }
  function blockers() {
    const list = [];
    if (editing !== null) list.push({text: '请先应用或取消当前字段编辑。'});
    if (!declarations.some(item => item.include)) list.push({text: '至少保留一列。'});
    const grouped = new Map();
    for (const item of declarations) {
      for (const issue of problemsFor(item)) {
        if (!grouped.has(issue.text)) grouped.set(issue.text, {...issue, columns: []});
        grouped.get(issue.text).columns.push(item.index + 1);
      }
    }
    list.push(...grouped.values());
    if (!conventions.value.trim()) list.push({text: '请填写本次来源说明。'});
    return list;
  }
  function renderProblems(list) {
    problemList.replaceChildren();
    for (const item of list) {
      problemList.append(node('li', item.columns ? `第 ${item.columns.join('、')} 列：${item.text}` : item.text,
        item.level === 'invalid' ? 'invalid' : ''));
    }
    if (importIssue) {
      const line = node('li', undefined, 'invalid');
      line.append(node('strong', '导入未完成'));
      if (importIssue.index === null && importIssue.hint) line.append(node('span', `：${importIssue.hint}`));
      line.append(node('span', [importIssue.message, importIssue.action].filter(Boolean).join(' '), 'detail'));
      problemList.append(line);
    }
    problemList.hidden = !problemList.children.length;
  }
  function updateGate() {
    const list = blockers();
    renderProblems(list);
    confirmed.disabled = editing !== null || importing;
    importButton.disabled = importing || list.length > 0 || !confirmed.checked;
  }
  function changed(index) {
    if (confirmed.checked && confirmNote) { confirmNote.textContent = '已修改，请重新核对。'; confirmNote.hidden = false; }
    confirmed.checked = false;
    if (importIssue && (importIssue.index === null || importIssue.index === index)) importIssue = null;
  }

  function renderRows() {
    tbody.replaceChildren();
    const locked = editing !== null || importing;
    for (const item of declarations) {
      const column = columnFor(item.index);
      const issues = problemsFor(item);
      const invalidIssue = field => issues.find(issue => issue.field === field && issue.level === 'invalid');
      const row = node('tr');
      row.dataset.index = String(item.index);
      row.dataset.problem = issues.some(issue => issue.level === 'invalid') ? 'invalid' : issues.length ? 'pending' : '';
      if (!item.include) row.dataset.excluded = 'true';
      if (editing === item.index) row.dataset.editing = 'true';
      const keep = node('input');
      keep.type = 'checkbox'; keep.dataset.key = 'include'; keep.checked = item.include; keep.disabled = locked;
      keep.setAttribute('aria-label', `保留第 ${item.index + 1} 列`);
      keep.addEventListener('change', () => {
        item.include = keep.checked; changed(item.index); render();
        rowFor(item.index)?.querySelector('[data-key="include"]')?.focus();
      });
      const keepCell = node('td', undefined, 'cell-keep'); keepCell.append(keep);
      const source = node('td', undefined, 'cell-source'); source.dataset.field = 'source';
      source.append(node('span', String(item.index + 1).padStart(2, '0'), 'column-number'),
        node('span', column.source_name || '无列名', column.source_name ? 'source-name' : 'source-name muted'));
      const target = node('td', undefined, 'cell-target'); target.dataset.field = 'target';
      target.append(node('span', item.target.trim() || '未填写', 'field-name'));
      const unit = node('td', undefined, 'cell-unit'); unit.dataset.field = 'unit';
      const input = item.input_unit.trim(); const output = item.output_unit.trim();
      if (!numeric(item.dtype)) unit.append(node('span', '不适用', 'muted'));
      else if (input && output) unit.append(node('span', input === output ? unitText(input) : `${unitText(input)} → ${unitText(output)}`));
      else unit.append(node('span', '未填写单位', item.include ? 'issue-text' : 'muted'));
      const kind = node('td', undefined, 'cell-kind'); kind.dataset.field = 'kind';
      if (!item.include) kind.append(node('span', '已排除', 'muted'));
      else {
        kind.append(document.createTextNode(`${TYPES[item.dtype] || item.dtype} · `));
        kind.append(item.role ? node('span', ROLE_LABELS[item.role] || item.role) : node('span', '未选用途', 'issue-text'));
      }
      for (const [cell, field] of [[target, 'target'], [unit, 'unit'], [kind, 'kind']]) {
        const issue = invalidIssue(field);
        if (issue) cell.append(node('span', issue.text, 'cell-issue'));
      }
      const edit = node('button', '编辑', 'link-button');
      edit.type = 'button'; edit.dataset.editColumn = String(item.index); edit.disabled = locked;
      edit.setAttribute('aria-label', `编辑第 ${item.index + 1} 列 ${item.target.trim()}`.trim());
      edit.addEventListener('click', () => openEditor(item.index));
      const action = node('td', undefined, 'cell-action'); action.append(edit);
      row.append(keepCell, source, target, unit, kind, action);
      tbody.append(row);
    }
  }
  function renderSource() {
    const text = conventions.value.trim();
    const open = sourceOpen || !text;
    sourceEditor.hidden = !open;
    sourceToggle.setAttribute('aria-expanded', String(open));
    sourceState.textContent = !text ? '必填' : open ? '' : text;
    sourceState.dataset.state = text ? '' : 'required';
  }
  function render() {
    if (!preview) return;
    renderRows();
    const kept = declarations.filter(item => item.include).length;
    keepCount.textContent = `保留 ${kept} 列${declarations.length > kept ? ` · 排除 ${declarations.length - kept} 列` : ''}`;
    renderSource();
    updateGate();
  }

  function editorField(container, key, label, control) {
    const wrapper = node('label', undefined, 'editor-field');
    control.dataset.edit = key;
    wrapper.append(node('span', label), control);
    container.append(wrapper);
    return control;
  }
  function choice(values, value) {
    const select = node('select');
    for (const [id, label] of values) { const option = node('option', label); option.value = id; select.append(option); }
    if (value && !values.some(([id]) => id === value)) {
      const option = node('option', `已保存用途：${value}`); option.value = value; select.append(option);
    }
    select.value = value;
    return select;
  }
  function textInput(value) {
    const input = node('input'); input.value = value; input.spellcheck = false; input.autocomplete = 'off';
    return input;
  }
  function onEditorKey(event) {
    if (event.isComposing || event.keyCode === 229) return;
    if (event.key === 'Escape') { event.preventDefault(); closeEditor(false); }
    else if (event.key === 'Enter' && event.currentTarget.tagName.toLowerCase() !== 'button') { event.preventDefault(); applyEdit(); }
  }
  // Only one field expands at a time; other row actions stay disabled until it is applied or cancelled.
  function openEditor(index) {
    if (editing !== null || importing) return;
    editing = index;
    render();
    const item = declarations.find(entry => entry.index === index);
    const panel = node('div', undefined, 'field-editor');
    panel.setAttribute('role', 'group');
    panel.setAttribute('aria-label', `编辑第 ${index + 1} 列`);
    const grid = node('div', undefined, 'field-editor-grid');
    const controls = {
      target: editorField(grid, 'target', '字段名', textInput(item.target)),
      dtype: editorField(grid, 'dtype', '类型', choice(Object.entries(TYPES), item.dtype)),
      input_unit: editorField(grid, 'input_unit', '来源单位', textInput(item.input_unit)),
      output_unit: editorField(grid, 'output_unit', '输出单位', textInput(item.output_unit)),
      role: editorField(grid, 'role', '用途', choice(ROLE_OPTIONS, item.role)),
    };
    const samples = columnFor(index).samples;
    const error = node('p', '', 'editor-error'); error.dataset.editorError = ''; error.hidden = true;
    error.setAttribute('aria-live', 'polite');
    const hint = node('p', '', 'editor-hint'); hint.hidden = true;
    const cancel = node('button', '取消', 'link-button'); cancel.type = 'button'; cancel.dataset.editorCancel = '';
    const apply = node('button', '应用', 'primary'); apply.type = 'button'; apply.dataset.editorApply = '';
    const actions = node('div', undefined, 'field-editor-actions'); actions.append(cancel, apply);
    panel.append(grid, node('p', `原始样本：${samples.length ? samples.join(' / ') : '无'}`, 'editor-sample'), error, hint, actions);
    const cell = node('td'); cell.colSpan = 6; cell.append(panel);
    const row = node('tr', undefined, 'editor-row'); row.dataset.editorFor = String(index); row.append(cell);
    rowFor(index).after(row);
    editor = {index, controls, error, hint, apply};
    for (const control of Object.values(controls)) {
      control.addEventListener('input', checkDraft);
      control.addEventListener('change', checkDraft);
      control.addEventListener('keydown', onEditorKey);
    }
    for (const button of [cancel, apply]) button.addEventListener('keydown', onEditorKey);
    cancel.addEventListener('click', () => closeEditor(false));
    apply.addEventListener('click', applyEdit);
    checkDraft();
    controls.target.focus();
  }
  function readDraft() {
    const {controls} = editor;
    const draft = {...declarations.find(entry => entry.index === editor.index)};
    for (const key of DECLARATION_KEYS) draft[key] = controls[key].value;
    const isNumeric = numeric(draft.dtype);
    controls.input_unit.disabled = controls.output_unit.disabled = !isNumeric;
    if (!isNumeric) controls.input_unit.value = controls.output_unit.value = draft.input_unit = draft.output_unit = '';
    for (const key of ['target', 'input_unit', 'output_unit']) draft[key] = draft[key].trim();
    return draft;
  }
  function checkDraft() {
    if (!editor) return;
    const draft = readDraft();
    const issues = problemsFor(draft, declarations.map(entry => entry.index === draft.index ? draft : entry), false);
    const invalid = issues.filter(issue => issue.level === 'invalid');
    const pending = issues.filter(issue => issue.level === 'pending');
    editor.error.textContent = invalid.map(issue => issue.text).join('；');
    editor.error.hidden = !invalid.length;
    editor.hint.textContent = pending.length ? `还需${pending.map(issue => issue.text.replace(/^需/, '')).join('、')}` : '';
    editor.hint.hidden = !pending.length;
    editor.apply.disabled = invalid.length > 0;
    editor.controls.target.setAttribute('aria-invalid', String(invalid.some(issue => issue.field === 'target')));
  }
  function applyEdit() {
    if (!editor) return;
    checkDraft();
    if (editor.apply.disabled) return;
    const draft = readDraft();
    const prior = declarations.find(entry => entry.index === draft.index);
    const modified = DECLARATION_KEYS.some(key => prior[key] !== draft[key]);
    declarations = declarations.map(entry => entry.index === draft.index ? draft : entry);
    closeEditor(modified);
  }
  function closeEditor(modified) {
    if (editing === null) return;
    const index = editing;
    editing = null; editor = null;
    if (modified) changed(index);
    render();
    rowFor(index)?.querySelector('[data-edit-column]')?.focus();
  }

  sourceToggle?.addEventListener('click', () => {
    sourceOpen = !conventions.value.trim() || sourceEditor.hidden;
    renderSource();
    if (sourceOpen) conventions.focus();
  });
  conventions.addEventListener('input', () => { changed('source'); renderSource(); updateGate(); });
  confirmed.addEventListener('change', () => { if (confirmNote) confirmNote.hidden = true; updateGate(); });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const chosen = file.files[0]; if (!chosen) return;
    cancelSettingsLoad();
    const current = ++generation;
    pendingPreview = current;
    preview = null; review.hidden = true; confirmed.checked = false; editing = null; editor = null; importIssue = null;
    const button = $('csv-preview-button'); button.disabled = true;
    const declared = options(); const data = new FormData(); data.set('file', chosen); data.set('options_json', JSON.stringify(declared));
    if (savedSettings) data.set('settings_json', JSON.stringify(savedSettings));
    setStatus('正在读取表格…');
    try {
      const result = await request(`/api/projects/${project}/csv-preview`, data);
      if (current !== generation) return;
      preview = {result, file: chosen, options: declared, settings: savedSettings};
      declarations = initialDeclarations(result.columns, result.settings_review?.matches ? result.settings_review.columns : []);
      renderSettingsReview(result.settings_review);
      renderRaw(result);
      const suggested = result.columns.some(column => column.suggested_unit);
      $('csv-counts').textContent = `${chosen.name} · ${result.record_count} 条记录 · ${result.columns.length} 列${suggested ? ' · 单位取自表头，仅作建议' : ''}`;
      const notes = (result.warnings || []).map(warning => PREVIEW_WARNINGS[warning] ?? warning).filter(Boolean);
      setStatus(notes.join(' '), notes.length ? 'warning' : '');
      if (notes.length) showOptions(true);
      if (confirmNote) confirmNote.hidden = true;
      review.hidden = false;
      render();
    } catch (error) {
      if (current === generation) { setStatus(errorMessage(error), 'error'); showOptions(true); }
    }
    finally {
      button.disabled = false;
      if (pendingPreview === current) pendingPreview = null;
    }
  });
  review.addEventListener('submit', async event => {
    event.preventDefault();
    if (!preview || importing || !confirmed.checked || blockers().length) { updateGate(); return; }
    const columns = declarations.map(({index, include, target, dtype, input_unit, output_unit, role}) =>
      ({index, include, target, dtype, input_unit, output_unit, role}));
    const data = new FormData(); data.set('file', preview.file);
    const context = selectedContext();
    data.set('source_sha256', preview.result.source_sha256); data.set('options_json', JSON.stringify(preview.options));
    if (preview.settings) data.set('settings_json', JSON.stringify(preview.settings));
    data.set('columns_json', JSON.stringify(columns)); data.set('confirmed', 'true');
    data.set('conventions', conventions.value);
    importing = true; importIssue = null;
    settings.disabled = reviewControls.disabled = true;
    if (savedControls) savedControls.disabled = true;
    render();
    setStatus('正在保存原文件、已确认数据与规则…');
    try {
      const result = await request(`/api/projects/${project}/csv-import`, data);
      const activated = await activateInput(result, context);
      const importedContext = {datasetId: String(result.dataset_id), schemaSelector: result.schema_selector,
        filename: result.filename, schemaLabel: result.schema_name};
      showResult('已确认并导入，可生成报告', result, activated ? selectedContext() : importedContext);
      resetReview();
      setStatus('', 'success');
      status.append(node('span', activated ? '导入完成，已选中这份数据与规则。' : '导入完成；当前选择已改变，可从数据列表选择新结果。'));
      const links = node('span', undefined, 'status-links');
      for (const [part, label] of [['source', '下载原文件'], ['schema', '下载正式规则'], ['manifest', '下载导入清单'], ['settings', '保存已确认导入设置']]) {
        const link = node('a', label); link.href = `/api/projects/${project}/csv-imports/${result.dataset_id}/${part}`;
        links.append(link);
      }
      status.append(links);
    } catch (error) {
      importIssue = describeServerError(error);
      setStatus('');
    } finally {
      importing = false;
      settings.disabled = reviewControls.disabled = false;
      if (savedControls) savedControls.disabled = false;
      render();
    }
  });
  refreshOptionsSummary();
}
