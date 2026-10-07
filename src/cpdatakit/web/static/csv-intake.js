function node(tag, text) {
  const value = document.createElement(tag);
  if (text !== undefined) value.textContent = text;
  return value;
}

function errorMessage(error) {
  const action = error.payload?.error?.action;
  return action ? `${error.message} ${action}` : error.message;
}

export function setupCsvIntake({request, activateInput, showResult, selectedContext}) {
  const form = document.querySelector('#csv-preview-form');
  if (!form) return;
  const project = document.body.dataset.projectId;
  const file = document.querySelector('#csv-file');
  const settings = document.querySelector('#csv-input-controls');
  const reviewControls = document.querySelector('#csv-review-controls');
  const review = document.querySelector('#csv-confirm-form');
  const status = document.querySelector('#csv-status');
  const tbody = document.querySelector('#csv-columns tbody');
  const confirmed = document.querySelector('#csv-confirmed');
  const settingsFile = document.querySelector('#csv-settings-file');
  const settingsStatus = document.querySelector('#csv-settings-status');
  const settingsReview = document.querySelector('#csv-settings-review');
  const savedControls = document.querySelector('#csv-saved-controls');
  let preview;
  let savedSettings = null;
  let settingsLoading = false;
  let generation = 0;

  function options() {
    const delimiter = document.querySelector('#csv-delimiter').value;
    return {delimiter: delimiter === 'tab' ? '\t' : delimiter,
      header_row: Number(document.querySelector('#csv-header-row').value),
      unit_row: Number(document.querySelector('#csv-unit-row').value),
      decimal: document.querySelector('#csv-decimal').value,
      encoding: document.querySelector('#csv-encoding').value};
  }
  function cancelSettingsLoad() {
    if (!settingsLoading) return;
    settingsLoading = false; settingsFile.value = '';
    settingsStatus.textContent = '设置载入已取消，请重新选择设置文件。';
  }
  function invalidate() {
    cancelSettingsLoad();
    generation++; preview = null; review.hidden = true; confirmed.checked = false;
    document.querySelector('#csv-conventions').value = '';
    settingsReview?.replaceChildren();
    status.textContent = '文件或解析设置已更改，请重新预览。';
  }
  settings.addEventListener('input', invalidate);
  settings.addEventListener('change', invalidate);
  review.addEventListener('input', event => {
    if (event.target !== confirmed) confirmed.checked = false;
  });
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
      for (const [key, [id]] of Object.entries(selectors)) document.querySelector('#' + id).value = opts[key] === '\t' ? 'tab' : opts[key];
      document.querySelector('#csv-header-row').value = String(opts.header_row);
      document.querySelector('#csv-unit-row').value = String(opts.unit_row);
      settingsStatus.textContent = `已载入 ${chosen.name}。请预览当前文件，核对差异；本文件的来源说明需重新填写。`;
    } catch (error) {
      if (current === generation) settingsStatus.textContent = `无法载入设置：${error.message}`;
    }
    finally { if (current === generation) settingsLoading = false; }
  });
  document.querySelector('#csv-settings-clear')?.addEventListener('click', () => {
    invalidate(); savedSettings = null; settingsFile.value = '';
    settingsStatus.textContent = '已取消设置复用。当前解析选项保留，请重新预览。';
  });

  function renderSettingsReview(result) {
    if (!settingsReview) return;
    settingsReview.replaceChildren();
    if (!result) return;
    settingsReview.append(node('p', result.matches
      ? '文件结构与保存的设置一致，已填入此前确认的字段、单位和用途。请核对当前文件的实际含义。'
      : '当前文件与保存的设置存在差异，未套用旧字段声明。请按当前预览重新确认。'));
    if (result.changes.length) {
      const table = node('table'); const head = node('tr');
      for (const label of ['变化项', '保存的设置', '当前文件']) head.append(node('th', label));
      table.append(head);
      const display = value => value === null || value === undefined ? '未声明' : typeof value === 'object' ? JSON.stringify(value) : String(value);
      const labels = {'options.delimiter': '分隔符', 'options.header_row': '表头行', 'options.unit_row': '独立单位行',
        'options.decimal': '小数符号', 'options.encoding': '文件编码', 'source_columns.length': '列数', 'source_columns': '原始列记录'};
      for (const change of result.changes) {
        const row = node('tr');
        const column = /^source_columns\[(\d+)\]\.(\w+)$/.exec(change.field);
        const label = column ? `第 ${Number(column[1]) + 1} 列 · ${{index: '位置', source_name: '名称', dtype: '检测类型', suggested_unit: '单位提示'}[column[2]] || column[2]}` : labels[change.field] || change.field;
        for (const value of [label, display(change.before), display(change.after)]) row.append(node('td', value));
        table.append(row);
      }
      settingsReview.append(table);
    }
    for (const warning of result.warnings || []) settingsReview.append(node('p', warning));
  }

  function inputCell(row, key, value, label) {
    const cell = node('td'); const input = node('input'); input.value = value || '';
    input.dataset.key = key; input.setAttribute('aria-label', label); cell.append(input); row.append(cell);
    return input;
  }
  function selectCell(row, key, values, value, label) {
    const cell = node('td'); const select = node('select'); select.dataset.key = key;
    select.setAttribute('aria-label', label);
    for (const [id, text] of values) { const option = node('option', text); option.value = id; select.append(option); }
    if (value && !values.some(([id]) => id === value)) {
      const option = node('option', `已保存用途：${value}`); option.value = value; select.append(option);
    }
    select.value = value || ''; cell.append(select); row.append(cell); return select;
  }
  function renderColumns(columns, declarations = []) {
    tbody.replaceChildren();
    for (const column of columns) {
      const saved = declarations.find(item => item.index === column.index);
      const row = node('tr'); row.dataset.index = column.index;
      const includeCell = node('td'); const include = node('input'); include.type = 'checkbox';
      include.dataset.key = 'include'; include.checked = saved ? saved.include : true;
      include.setAttribute('aria-label', `保留第 ${column.index + 1} 列`); includeCell.append(include); row.append(includeCell);
      const source = node('td'); source.append(node('strong', `${column.index + 1} · ${column.source_name || '无列名'}`), node('p', column.samples.map(value => String(value)).join(' / ')));
      row.append(source);
      const proposed = column.source_name && !column.suggested_unit ? column.source_name : `column_${column.index + 1}`;
      inputCell(row, 'target', saved?.target ?? proposed, `第 ${column.index + 1} 列输出字段名`);
      const dtype = selectCell(row, 'dtype', [['float','小数'],['integer','整数'],['string','文字'],['boolean','布尔']], saved?.dtype ?? column.dtype, `第 ${column.index + 1} 列类型`);
      const sourceUnit = inputCell(row, 'input_unit', saved?.input_unit ?? column.suggested_unit, `第 ${column.index + 1} 列来源单位`);
      const outputUnit = inputCell(row, 'output_unit', saved?.output_unit ?? column.suggested_unit, `第 ${column.index + 1} 列输出单位`);
      const role = selectCell(row, 'role', [['','请选择用途'],['time','时间'],['measured_quantity','测量值'],['simulated_quantity','模拟值'],['identifier','标识'],['category','类别'],['custom','其他（在说明中声明）']], saved?.role ?? '', `第 ${column.index + 1} 列用途`);
      function updateRequired() {
        const numeric = ['float','integer'].includes(dtype.value);
        for (const control of row.querySelectorAll('[data-key]')) if (control !== include) control.disabled = !include.checked;
        row.querySelector('[data-key="target"]').required = include.checked;
        role.required = include.checked; dtype.required = include.checked;
        sourceUnit.required = outputUnit.required = include.checked && numeric;
        sourceUnit.disabled = outputUnit.disabled = !include.checked || !numeric;
        if (!numeric) { sourceUnit.value = ''; outputUnit.value = ''; }
        row.classList.toggle('csv-excluded', !include.checked);
      }
      include.addEventListener('change', updateRequired); dtype.addEventListener('change', updateRequired);
      updateRequired(); tbody.append(row);
    }
  }
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const chosen = file.files[0]; if (!chosen) return;
    cancelSettingsLoad();
    const current = ++generation; preview = null; review.hidden = true; confirmed.checked = false;
    const button = document.querySelector('#csv-preview-button'); button.disabled = true;
    const declared = options(); const data = new FormData(); data.set('file', chosen); data.set('options_json', JSON.stringify(declared));
    if (savedSettings) data.set('settings_json', JSON.stringify(savedSettings));
    status.textContent = '正在读取表格预览…';
    try {
      const result = await request(`/api/projects/${project}/csv-preview`, data);
      if (current !== generation) return;
      preview = {result, file: chosen, options: declared, settings: savedSettings};
      renderColumns(result.columns, result.settings_review?.matches ? result.settings_review.columns : []);
      renderSettingsReview(result.settings_review);
      document.querySelector('#csv-counts').textContent = `${result.record_count} 条记录，${result.columns.length} 列。请逐列确认；取消保留的列仍在原始文件中。`;
      const warnings = {
        'Only one column was read; check the delimiter before confirming fields.': '只读到一列，请检查分隔符是否正确。',
        'Units from headers are suggestions and require explicit confirmation.': '表头中的单位只作为建议，请对照来源逐列确认。',
      };
      status.textContent = result.warnings?.length ? result.warnings.map(item => warnings[item] || item).join(' ') : '预览完成。字段和单位建议尚未确认。';
      review.hidden = false;
    } catch (error) { if (current === generation) status.textContent = errorMessage(error); }
    finally { button.disabled = false; }
  });
  review.addEventListener('submit', async event => {
    event.preventDefault(); if (!preview || !confirmed.checked) return;
    const columns = [...tbody.rows].map(row => {
      const result = {index: Number(row.dataset.index)};
      for (const input of row.querySelectorAll('[data-key]')) result[input.dataset.key] = input.type === 'checkbox' ? input.checked : input.value;
      return result;
    });
    const data = new FormData(); data.set('file', preview.file);
    const context = selectedContext();
    data.set('source_sha256', preview.result.source_sha256); data.set('options_json', JSON.stringify(preview.options));
    if (preview.settings) data.set('settings_json', JSON.stringify(preview.settings));
    data.set('columns_json', JSON.stringify(columns)); data.set('confirmed', 'true');
    data.set('conventions', document.querySelector('#csv-conventions').value);
    settings.disabled = reviewControls.disabled = true;
    if (savedControls) savedControls.disabled = true;
    status.textContent = '正在保存原文件、已确认数据与规则…';
    try {
      const result = await request(`/api/projects/${project}/csv-import`, data);
      const activated = await activateInput(result, context);
      const importedContext = {datasetId: String(result.dataset_id), schemaSelector: result.schema_selector,
        filename: result.filename, schemaLabel: result.schema_name};
      showResult('已确认并导入，可生成报告', result, activated ? selectedContext() : importedContext);
      status.replaceChildren(node('span', activated ? '导入完成，当前数据与规则已选中。 ' : '导入完成；当前选择已改变，可从数据列表选择新结果。 '));
      for (const [part, label] of [['source','下载原文件'],['schema','下载正式规则'],['manifest','下载导入清单'],['settings','保存已确认导入设置']]) {
        const link = node('a', label); link.href = `/api/projects/${project}/csv-imports/${result.dataset_id}/${part}`;
        status.append(link, document.createTextNode('　'));
      }
      confirmed.checked = false;
    } catch (error) { status.textContent = errorMessage(error); }
    finally {
      settings.disabled = reviewControls.disabled = false;
      if (savedControls) savedControls.disabled = false;
    }
  });
}
