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
let _bulkExportInProgress = false;

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

function sanitizeFileName(name) {
  if (name == null) return '';
  return String(name).replace(/[<>:"/\\|?*\x00-\x1f]/g, '_');
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
 * Stream CSV construction in 50k-row chunks.
 */
async function buildCSVParts(tableData, onChunk) {
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
    if (onChunk) onChunk(end, rowCount);
    if (end < rowCount) await new Promise(r => setTimeout(r, 0));
  }

  return parts;
}

/**
 * Stream CSV export for large tables — writes in 50k-row chunks.
 */
async function exportCSVStreaming(tableName, tableData) {
  const parts = await buildCSVParts(tableData);

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

function isParquetAvailable() {
  return typeof HyparquetWriter !== 'undefined' && !!HyparquetWriter.parquetWriteBuffer;
}

function tableToParquetBuffer(tableData) {
  const { columns, columnData } = tableData;
  const parquetCols = columns.map((name, i) => ({ name, data: columnData[i] }));
  return HyparquetWriter.parquetWriteBuffer({ columnData: parquetCols });
}

function exportParquet(tableName, tableData) {
  if (!isParquetAvailable()) {
    toast('Parquet writer not available');
    return;
  }

  const buffer = tableToParquetBuffer(tableData);
  const blob = new Blob([buffer], { type: 'application/octet-stream' });
  downloadBlob(blob, tableName + '.parquet');
}

// ============================================================
// Bulk Export (all tables)
// ============================================================

function getModelExportName() {
  const fallback = 'semantic-model';
  if (typeof appState === 'undefined' || !appState.model || !appState.model.name) return fallback;
  const safe = sanitizeFileName(appState.model.name).trim();
  return safe || fallback;
}

function updateExportButtons() {
  const csvBtn = document.getElementById('exportCsvBtn');
  const parquetBtn = document.getElementById('exportParquetBtn');
  const allCsvBtn = document.getElementById('exportAllCsvBtn');
  const allParquetBtn = document.getElementById('exportAllParquetBtn');

  const hasCurrentTable = !!(_currentTableData && _currentTableName);
  const hasModel = !!_pbixDataModel;
  const parquetReady = isParquetAvailable();

  if (csvBtn) csvBtn.disabled = _bulkExportInProgress || !hasCurrentTable;
  if (parquetBtn) parquetBtn.disabled = _bulkExportInProgress || !hasCurrentTable || !parquetReady;
  if (allCsvBtn) allCsvBtn.disabled = _bulkExportInProgress || !hasModel;
  if (allParquetBtn) allParquetBtn.disabled = _bulkExportInProgress || !hasModel || !parquetReady;
}

async function exportAllTables(format) {
  if (!_pbixDataModel || _bulkExportInProgress) return;
  if (typeof JSZip === 'undefined') {
    toast('ZIP library not available');
    return;
  }
  if (format !== 'csv' && format !== 'parquet') {
    toast('Unknown export format: ' + format);
    return;
  }
  if (format === 'parquet' && !isParquetAvailable()) {
    toast('Parquet writer not available');
    return;
  }

  const tableNames = _pbixDataModel.tableNames || [];
  if (tableNames.length === 0) {
    toast('No tables to export');
    return;
  }

  const statusEl = document.getElementById('dataStatus');
  _bulkExportInProgress = true;
  _extractionEpoch++; // cancel any in-flight table preview extraction
  updateExportButtons();

  try {
    const zip = new JSZip();

    for (let i = 0; i < tableNames.length; i++) {
      const tableName = tableNames[i];
      const fileBase = sanitizeFileName(tableName) || ('table_' + (i + 1));
      const prefix = 'Exporting ' + (i + 1) + '/' + tableNames.length + ': ' + tableName;

      if (statusEl) statusEl.textContent = prefix + '...';

      const data = await _pbixDataModel.getTableStreaming(tableName, (colIdx, total, colName) => {
        const pct = total > 0 ? Math.round(((colIdx + 1) / total) * 100) : 100;
        if (statusEl) statusEl.textContent = prefix + ' column ' + (colIdx + 1) + '/' + total + ' (' + pct + '%)';
      });

      if (format === 'csv') {
        if (statusEl) statusEl.textContent = 'Building CSV ' + (i + 1) + '/' + tableNames.length + ': ' + tableName + '...';
        const csvParts = await buildCSVParts(data);
        zip.file(fileBase + '.csv', csvParts.join(''));
      } else {
        if (statusEl) statusEl.textContent = 'Building Parquet ' + (i + 1) + '/' + tableNames.length + ': ' + tableName + '...';
        const buffer = tableToParquetBuffer(data);
        zip.file(fileBase + '.parquet', buffer);
        await new Promise(r => setTimeout(r, 0));
      }
    }

    if (statusEl) statusEl.textContent = 'Compressing archive...';
    const zipBlob = await zip.generateAsync({
      type: 'blob',
      compression: 'DEFLATE',
      compressionOptions: { level: 6 },
    });
    const filename = getModelExportName() + '-tables-' + format + '.zip';
    downloadBlob(zipBlob, filename);
    if (statusEl) statusEl.textContent = '';
    toast('Exported ' + tableNames.length + ' tables as ' + format.toUpperCase() + ' ZIP');
  } catch (e) {
    if (statusEl) statusEl.textContent = 'Failed to export all tables';
    toast('Bulk export failed: ' + (e && e.message ? e.message : 'Unknown error'));
  } finally {
    _bulkExportInProgress = false;
    updateExportButtons();
  }
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
  _bulkExportInProgress = false;
  _extractionEpoch++;

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
  updateExportButtons();
}

function initDataTab(pbixDataModel) {
  _pbixDataModel = pbixDataModel;
  _currentTableData = null;
  _currentTableName = null;
  _bulkExportInProgress = false;

  const dataTabBtn = document.getElementById('dataTabBtn');
  if (dataTabBtn) dataTabBtn.style.display = '';

  renderDataTableList();
  updateExportButtons();

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

    document.getElementById('exportAllCsvBtn').addEventListener('click', () => {
      exportAllTables('csv');
    });

    document.getElementById('exportAllParquetBtn').addEventListener('click', () => {
      exportAllTables('parquet');
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
  if (_bulkExportInProgress) {
    toast('Bulk export in progress. Please wait.');
    return;
  }

  const statusEl = document.getElementById('dataStatus');
  const previewEl = document.getElementById('dataPreview');
  const nameEl = document.getElementById('dataTableName');
  const countEl = document.getElementById('dataRowCount');

  // Cancel any in-progress extraction via epoch counter (no timing dependency)
  const epoch = ++_extractionEpoch;
  _extractionAborted = false;

  // Highlight selected
  document.querySelectorAll('.data-table-item').forEach(el => {
    el.classList.toggle('active', el.textContent === tableName);
  });

  nameEl.textContent = tableName;
  countEl.textContent = '';
  _currentTableData = null;
  _currentTableName = null;
  updateExportButtons();
  previewEl.innerHTML = '<div class="detail-empty">Loading table data...</div>';
  if (statusEl) statusEl.textContent = 'Extracting ' + tableName + '...';

  try {
    const data = await _pbixDataModel.getTableStreaming(tableName, (colIdx, total, colName) => {
      if (epoch !== _extractionEpoch) throw new Error('__aborted__');
      const pct = total > 0 ? Math.round(((colIdx + 1) / total) * 100) : 100;
      if (statusEl) statusEl.textContent = 'Extracting ' + tableName + '... column ' + (colIdx + 1) + '/' + total + ' (' + pct + '%)';
    });

    if (epoch !== _extractionEpoch) return;

    _currentTableData = data;
    _currentTableName = tableName;

    countEl.textContent = formatNum(data.rowCount) + ' rows';
    updateExportButtons();
    if (statusEl) statusEl.textContent = '';

    renderDataPreview(data);
  } catch (e) {
    if (e.message === '__aborted__') return;
    previewEl.innerHTML = '<div class="detail-empty" style="color:var(--err);">Error: ' + escHtml(e.message) + '</div>';
    if (statusEl) statusEl.textContent = 'Failed to extract table data';
    _currentTableData = null;
    _currentTableName = null;
    updateExportButtons();
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
