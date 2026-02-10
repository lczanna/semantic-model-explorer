// ============================================================
// Data Export Module — CSV + Parquet export and Data tab UI
//
// Data is stored in columnar format { columns, columnData, rowCount }
// to avoid expensive row transposition and reduce memory usage.
// Extraction uses streaming (column-at-a-time with event loop yields)
// to keep the UI responsive for large tables.
// ============================================================

// --- State for the Data tab ---
let _pbixDataModel = null; // Result from parsePbixDataModel()
let _currentTableData = null; // { columns, columnData, rowCount }
let _currentTableName = null;
let _extractionAborted = false; // Signals abort when user clicks another table
let _extractionEpoch = 0; // Monotonic counter — incremented to cancel previous extractions

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

/**
 * Build CSV string from columnar data (small tables).
 */
function tableToCSV(tableData) {
  const { columns, columnData, rowCount } = tableData;
  const lines = [];
  lines.push(columns.map(escapeCSVField).join(','));
  for (let r = 0; r < rowCount; r++) {
    const fields = [];
    for (let c = 0; c < columnData.length; c++) {
      const v = r < columnData[c].length ? columnData[c][r] : null;
      if (v instanceof Date) fields.push(v.toISOString());
      else fields.push(escapeCSVField(v));
    }
    lines.push(fields.join(','));
  }
  return lines.join('\n');
}

/**
 * Stream CSV export for large tables — writes in 50k-row chunks.
 */
async function exportCSVStreaming(tableName, tableData) {
  const { columns, columnData, rowCount } = tableData;
  const CHUNK = 50000;
  const parts = [];

  parts.push(columns.map(escapeCSVField).join(',') + '\n');

  for (let start = 0; start < rowCount; start += CHUNK) {
    const end = Math.min(start + CHUNK, rowCount);
    const lines = [];
    for (let r = start; r < end; r++) {
      const fields = [];
      for (let c = 0; c < columnData.length; c++) {
        const v = r < columnData[c].length ? columnData[c][r] : null;
        if (v instanceof Date) fields.push(v.toISOString());
        else fields.push(escapeCSVField(v));
      }
      lines.push(fields.join(','));
    }
    parts.push(lines.join('\n') + '\n');
    if (end < rowCount) await new Promise(r => setTimeout(r, 0));
  }

  const blob = new Blob(parts, { type: 'text/csv;charset=utf-8' });
  downloadBlob(blob, tableName + '.csv');
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
  if (tableData.rowCount > 10000) {
    exportCSVStreaming(tableName, tableData);
    return;
  }
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

  const { columns, columnData } = tableData;
  const parquetCols = columns.map((name, i) => ({ name, data: columnData[i] }));

  const buffer = HyparquetWriter.parquetWriteBuffer({ columnData: parquetCols });
  const blob = new Blob([buffer], { type: 'application/octet-stream' });
  downloadBlob(blob, tableName + '.parquet');
}

// ============================================================
// Data Tab UI
// ============================================================

let _dataTabInitialized = false;

function resetDataTab() {
  _pbixDataModel = null;
  _currentTableData = null;
  _currentTableName = null;
  _extractionAborted = true;

  var listEl = document.getElementById('dataTableList');
  if (listEl) listEl.innerHTML = '';
  var previewEl = document.getElementById('dataPreview');
  if (previewEl) previewEl.innerHTML = '<div class="detail-empty">Select a table to preview data</div>';
  var nameEl = document.getElementById('dataTableName');
  if (nameEl) nameEl.textContent = '';
  var countEl = document.getElementById('dataRowCount');
  if (countEl) countEl.textContent = '';
  var statusEl = document.getElementById('dataStatus');
  if (statusEl) statusEl.textContent = '';
  var csvBtn = document.getElementById('exportCsvBtn');
  if (csvBtn) csvBtn.disabled = true;
  var parquetBtn = document.getElementById('exportParquetBtn');
  if (parquetBtn) parquetBtn.disabled = true;
}

function initDataTab(pbixDataModel) {
  _pbixDataModel = pbixDataModel;
  _currentTableData = null;
  _currentTableName = null;

  const dataTabBtn = document.getElementById('dataTabBtn');
  if (dataTabBtn) dataTabBtn.style.display = '';

  renderDataTableList();

  // Only attach listeners once to avoid duplicate handlers on re-init
  if (!_dataTabInitialized) {
    _dataTabInitialized = true;

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

  // Cancel any in-progress extraction via epoch counter (no timing dependency)
  const epoch = ++_extractionEpoch;
  _extractionAborted = false;

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

  try {
    const data = await _pbixDataModel.getTableStreaming(tableName, (colIdx, total, colName) => {
      if (epoch !== _extractionEpoch) throw new Error('__aborted__');
      const pct = Math.round((colIdx / total) * 100);
      statusEl.textContent = 'Extracting ' + tableName + '... column ' + (colIdx + 1) + '/' + total + ' (' + pct + '%)';
    });

    if (epoch !== _extractionEpoch) return;

    _currentTableData = data;
    _currentTableName = tableName;

    countEl.textContent = formatNum(data.rowCount) + ' rows';
    csvBtn.disabled = false;
    parquetBtn.disabled = false;
    statusEl.textContent = '';

    renderDataPreview(data);
  } catch (e) {
    if (e.message === '__aborted__') return;
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

  const { columns, columnData, rowCount } = tableData;
  const displayCount = Math.min(maxRows, rowCount);

  let html = '<table class="data-table"><thead><tr>';
  for (const col of columns) {
    html += '<th>' + escHtml(col) + '</th>';
  }
  html += '</tr></thead><tbody>';

  for (let r = 0; r < displayCount; r++) {
    html += '<tr>';
    for (let c = 0; c < columnData.length; c++) {
      const val = r < columnData[c].length ? columnData[c][r] : null;
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
