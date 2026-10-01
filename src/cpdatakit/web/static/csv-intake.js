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
  let preview;
  let generation = 0;

  function options() {
    const delimiter = document.querySelector('#csv-delimiter').value;
    return {delimiter: delimiter === 'tab' ? '\t' : delimiter,
      header_row: Number(document.querySelector('#csv-header-row').value),
      unit_row: Number(document.querySelector('#csv-unit-row').value),
      decimal: document.querySelector('#csv-decimal').value,
      encoding: document.querySelector('#csv-encoding').value};
  }
  function invalidate() {
    generation++; preview = null; review.hidden = true; confirmed.checked = false;
    status.textContent = '文件或解析设置已更改，请重新预览。';
  }
  settings.addEventListener('input', invalidate);
  settings.addEventListener('change', invalidate);
  review.addEventListener('input', event => {
    if (event.target !== confirmed) confirmed.checked = false;
  });

  function inputCell(row, key, value, label) {
    const cell = node('td'); const input = node('input'); input.value = value || '';
    input.dataset.key = key; input.setAttribute('aria-label', label); cell.append(input); row.append(cell);
    return input;
  }
  function selectCell(row, key, values, value, label) {
    const cell = node('td'); const select = node('select'); select.dataset.key = key;
    select.setAttribute('aria-label', label);
    for (const [id, text] of values) { const option = node('option', text); option.value = id; select.append(option); }
    select.value = value || ''; cell.append(select); row.append(cell); return select;
  }
  function renderColumns(columns) {
    tbody.replaceChildren();
    for (const column of columns) {
      const row = node('tr'); row.dataset.index = column.index;
      const includeCell = node('td'); const include = node('input'); include.type = 'checkbox';
      include.dataset.key = 'include'; include.checked = true;
      include.setAttribute('aria-label', `保留第 ${column.index + 1} 列`); includeCell.append(include); row.append(includeCell);
      const source = node('td'); source.append(node('strong', `${column.index + 1} · ${column.source_name || '无列名'}`), node('p', column.samples.map(value => String(value)).join(' / ')));
      row.append(source);
      const proposed = column.source_name && !column.suggested_unit ? column.source_name : `column_${column.index + 1}`;
      inputCell(row, 'target', proposed, `第 ${column.index + 1} 列输出字段名`);
      const dtype = selectCell(row, 'dtype', [['float','小数'],['integer','整数'],['string','文字'],['boolean','布尔']], column.dtype, `第 ${column.index + 1} 列类型`);
      const sourceUnit = inputCell(row, 'input_unit', column.suggested_unit, `第 ${column.index + 1} 列来源单位`);
      const outputUnit = inputCell(row, 'output_unit', column.suggested_unit, `第 ${column.index + 1} 列输出单位`);
      const role = selectCell(row, 'role', [['','请选择用途'],['time','时间'],['measured_quantity','测量值'],['simulated_quantity','模拟值'],['identifier','标识'],['category','类别'],['custom','其他（在说明中声明）']], '', `第 ${column.index + 1} 列用途`);
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
    const current = ++generation; preview = null; review.hidden = true; confirmed.checked = false;
    const button = document.querySelector('#csv-preview-button'); button.disabled = true;
    const declared = options(); const data = new FormData(); data.set('file', chosen); data.set('options_json', JSON.stringify(declared));
    status.textContent = '正在读取表格预览…';
    try {
      const result = await request(`/api/projects/${project}/csv-preview`, data);
      if (current !== generation) return;
      preview = {result, file: chosen, options: declared}; renderColumns(result.columns);
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
    data.set('columns_json', JSON.stringify(columns)); data.set('confirmed', 'true');
    data.set('conventions', document.querySelector('#csv-conventions').value);
    settings.disabled = reviewControls.disabled = true; status.textContent = '正在保存原文件、已确认数据与规则…';
    try {
      const result = await request(`/api/projects/${project}/csv-import`, data);
      const activated = await activateInput(result, context);
      const importedContext = {datasetId: String(result.dataset_id), schemaSelector: result.schema_selector,
        filename: result.filename, schemaLabel: result.schema_name};
      showResult('已确认并导入，可生成报告', result, activated ? selectedContext() : importedContext);
      status.replaceChildren(node('span', activated ? '导入完成，当前数据与规则已选中。 ' : '导入完成；当前选择已改变，可从数据列表选择新结果。 '));
      for (const [part, label] of [['source','下载原文件'],['schema','下载正式规则'],['manifest','下载导入清单']]) {
        const link = node('a', label); link.href = `/api/projects/${project}/csv-imports/${result.dataset_id}/${part}`;
        status.append(link, document.createTextNode('　'));
      }
      confirmed.checked = false;
    } catch (error) { status.textContent = errorMessage(error); }
    finally { settings.disabled = reviewControls.disabled = false; }
  });
}
