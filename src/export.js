// ============================================================
// Data Export Module — CSV + Parquet export and Data tab UI
// ============================================================

// --- State for the Data tab ---
let _pbixDataModel = null; // Result from parsePbixDataModel()
let _currentTableData = null; // Current extracted table { columns, rows, rowCount }
let _currentTableName = null;

// ============================================================
// CSV Export
// ============================================================

function escapeCSVField(val) {
  if (val == null) return '';
  const s = String(val);
  if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function tableToCSV(tableData) {
  const { columns, rows } = tableData;
  const lines = [];
  lines.push(columns.map(escapeCSVField).join(','));
  for (const row of rows) {
    lines.push(row.map(v => {
      if (v instanceof Date) return v.toISOString();
      return escapeCSVField(v);
    }).join(','));
  }
  return lines.join('\n');
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportCSV(tableName, tableData) {
  const csv = tableToCSV(tableData);
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  downloadBlob(blob, tableName + '.csv');
}

// ============================================================
// Parquet Export (via hyparquet-writer)
// ============================================================

function exportParquet(tableName, tableData) {
  if (typeof HyparquetWriter === 'undefined' || !HyparquetWriter.parquetWriteBuffer) {
    toast('Parquet writer not available');
    return;
  }

  const { columns, rows } = tableData;
  const columnData = columns.map((name, colIdx) => {
    const data = rows.map(row => row[colIdx]);
    return { name, data };
  });

  const buffer = HyparquetWriter.parquetWriteBuffer({ columnData });
  const blob = new Blob([buffer], { type: 'application/octet-stream' });
  downloadBlob(blob, tableName + '.parquet');
}

// ============================================================
// Data Tab UI
// ============================================================

function initDataTab(pbixDataModel) {
  _pbixDataModel = pbixDataModel;

  // Show the Data tab button
  const dataTabBtn = document.getElementById('dataTabBtn');
  if (dataTabBtn) dataTabBtn.style.display = '';

  // Render table list in sidebar
  renderDataTableList();

  // Wire up export buttons
  document.getElementById('exportCsvBtn').addEventListener('click', () => {
    if (_currentTableData && _currentTableName) {
      exportCSV(_currentTableName, _currentTableData);
      toast('Exported ' + _currentTableName + '.csv');
    }
  });

  document.getElementById('exportParquetBtn').addEventListener('click', () => {
    if (_currentTableData && _currentTableName) {
      exportParquet(_currentTableName, _currentTableData);
      toast('Exported ' + _currentTableName + '.parquet');
    }
  });
}

function renderDataTableList() {
  const listEl = document.getElementById('dataTableList');
  if (!listEl || !_pbixDataModel) return;

  listEl.innerHTML = '';
  for (const name of _pbixDataModel.tableNames) {
    const item = document.createElement('div');
    item.className = 'data-table-item';
    item.textContent = name;
    item.addEventListener('click', () => selectDataTable(name));
    listEl.appendChild(item);
  }
}

async function selectDataTable(tableName) {
  const statusEl = document.getElementById('dataStatus');
  const previewEl = document.getElementById('dataPreview');
  const nameEl = document.getElementById('dataTableName');
  const countEl = document.getElementById('dataRowCount');
  const csvBtn = document.getElementById('exportCsvBtn');
  const parquetBtn = document.getElementById('exportParquetBtn');

  // Highlight selected
  document.querySelectorAll('.data-table-item').forEach(el => {
    el.classList.toggle('active', el.textContent === tableName);
  });

  nameEl.textContent = tableName;
  countEl.textContent = '';
  csvBtn.disabled = true;
  parquetBtn.disabled = true;
  previewEl.innerHTML = '<div class="detail-empty">Loading table data...</div>';
  statusEl.textContent = 'Extracting ' + tableName + '...';

  // Use setTimeout to allow UI to update before heavy computation
  await new Promise(r => setTimeout(r, 10));

  try {
    const data = _pbixDataModel.getTable(tableName);
    _currentTableData = data;
    _currentTableName = tableName;

    countEl.textContent = formatNum(data.rowCount) + ' rows';
    csvBtn.disabled = false;
    parquetBtn.disabled = false;
    statusEl.textContent = '';

    renderDataPreview(data);
  } catch (e) {
    previewEl.innerHTML = '<div class="detail-empty" style="color:var(--err);">Error: ' + escHtml(e.message) + '</div>';
    statusEl.textContent = 'Failed to extract table data';
    _currentTableData = null;
    _currentTableName = null;
  }
}

function renderDataPreview(tableData, maxRows) {
  maxRows = maxRows || 100;
  const previewEl = document.getElementById('dataPreview');
  if (!previewEl) return;

  const { columns, rows, rowCount } = tableData;
  const displayRows = rows.slice(0, maxRows);

  let html = '<table class="data-table"><thead><tr>';
  for (const col of columns) {
    html += '<th>' + escHtml(col) + '</th>';
  }
  html += '</tr></thead><tbody>';

  for (const row of displayRows) {
    html += '<tr>';
    for (const val of row) {
      let display;
      if (val == null) {
        display = '<span class="null-val">null</span>';
      } else if (val instanceof Date) {
        display = escHtml(val.toISOString().replace('T', ' ').replace('Z', ''));
      } else {
        display = escHtml(String(val));
      }
      html += '<td>' + display + '</td>';
    }
    html += '</tr>';
  }

  html += '</tbody></table>';

  if (rowCount > maxRows) {
    html += '<div class="data-truncated">Showing ' + maxRows + ' of ' + formatNum(rowCount) + ' rows. Export to see all data.</div>';
  }

  previewEl.innerHTML = html;
}
