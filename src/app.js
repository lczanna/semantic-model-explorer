
// ============================================================
// App State
// ============================================================
const appState = {
  model: null,
  selectedItem: null,
  checkedItems: new Set(),
  errors: [],
  cy: null, // Cytoscape instance
  pbixDataModel: null, // VertiPaq data model for Data tab (set after async init)
  statsCache: null, // Map<tableName, columnStats[]> — cached after first computation
};

const PROMPTS = {
  analyze: "You are a Power BI expert. Review this semantic model for best practices, potential issues, and improvement opportunities. Focus on DAX efficiency, relationship design, and naming conventions.\n\n",
  document: "Generate comprehensive documentation for this Power BI semantic model. Include a summary, table descriptions, measure explanations, and relationship overview.\n\n",
  optimize: "Analyze this Power BI semantic model and suggest performance optimizations. Look at calculated columns that should be measures, high-complexity DAX, relationship design, and model structure.\n\n",
  explain: "Explain what this Power BI model does in plain, non-technical language. Describe the business domain, key metrics, and how the tables relate to each other.\n\n",
};

// ============================================================
// Utility Functions
// ============================================================
function $(id) { return document.getElementById(id); }
function show(el) { if (typeof el === 'string') el = $(el); el.style.display = 'flex'; }
function hide(el) { if (typeof el === 'string') el = $(el); el.style.display = 'none'; }

function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback: textarea
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    return true;
  }
}

function escHtml(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function estimateTokens(text) {
  // Rough estimate: ~4 chars per token for English/code
  return Math.round(text.length / 4);
}

function formatNum(n) {
  if (n == null) return '';
  return n.toLocaleString();
}

// ============================================================
// PARSERS
// ============================================================

// --- Internal Data Model ---
function emptyModel() {
  return {
    name: '', compatibilityLevel: 0, culture: '',
    tables: [], relationships: [], roles: [],
    sourceFormat: '', statistics: null,
  };
}

function emptyTable() {
  return {
    name: '', type: 'import', isHidden: false, description: '',
    columns: [], measures: [], hierarchies: [], partitions: [],
    calculationItems: [],
  };
}

// --- BIM / TMSL Parser ---
function parseBimJson(json) {
  const model = emptyModel();
  const src = typeof json === 'string' ? JSON.parse(json) : json;
  const m = src.model || src;

  model.name = src.name || m.name || 'Untitled Model';
  model.compatibilityLevel = src.compatibilityLevel || 0;
  model.culture = m.culture || '';

  // Tables
  for (const t of (m.tables || [])) {
    const table = emptyTable();
    table.name = t.name || '';
    table.isHidden = !!t.isHidden;
    table.description = t.description || '';

    // Detect table type from partitions
    if (t.calculationGroup) {
      table.type = 'calculated';
      for (const ci of (t.calculationGroup.calculationItems || [])) {
        table.calculationItems.push({
          name: ci.name || '',
          expression: ci.expression || '',
          ordinal: ci.ordinal || 0,
        });
      }
    }

    // Columns
    for (const c of (t.columns || [])) {
      if (c.type === 'rowNumber') continue; // skip internal row number columns
      table.columns.push({
        name: c.name || '',
        dataType: c.dataType || 'string',
        type: c.type === 'calculated' ? 'calculated' : 'data',
        isHidden: !!c.isHidden,
        expression: c.expression || null,
        formatString: c.formatString || '',
        sortByColumn: c.sortByColumn || null,
        displayFolder: c.displayFolder || '',
        description: c.description || '',
      });
    }

    // Measures
    for (const m2 of (t.measures || [])) {
      table.measures.push({
        name: m2.name || '',
        expression: m2.expression || '',
        formatString: m2.formatString || '',
        displayFolder: m2.displayFolder || '',
        description: m2.description || '',
        isHidden: !!m2.isHidden,
      });
    }

    // Hierarchies
    for (const h of (t.hierarchies || [])) {
      table.hierarchies.push({
        name: h.name || '',
        levels: (h.levels || []).map(l => l.name || l.column || ''),
      });
    }

    // Partitions
    for (const p of (t.partitions || [])) {
      const part = { type: 'unknown', expression: '', mode: '' };
      if (p.source) {
        if (p.source.type === 'm' || p.source.type === 'powerQuery') {
          part.type = 'm';
          part.expression = p.source.expression || '';
        } else if (p.source.type === 'calculated') {
          part.type = 'calculated';
          part.expression = p.source.expression || '';
          table.type = 'calculated';
        } else if (p.source.type === 'query') {
          part.type = 'query';
          part.expression = p.source.query || '';
        } else if (p.source.type === 'entity') {
          part.type = 'entity';
          part.expression = p.source.entityName || '';
        }
      }
      part.mode = p.mode || '';
      if (p.mode === 'directQuery') table.type = 'directQuery';
      if (p.mode === 'dual') table.type = 'dual';
      if (p.mode === 'import' && table.type === 'import') table.type = 'import';
      table.partitions.push(part);
    }

    model.tables.push(table);
  }

  // Relationships
  for (const r of (m.relationships || [])) {
    model.relationships.push({
      fromTable: r.fromTable || '',
      fromColumn: r.fromColumn || '',
      toTable: r.toTable || '',
      toColumn: r.toColumn || '',
      cardinality: mapCardinality(r.fromCardinality, r.toCardinality, r.crossFilteringBehavior),
      crossFilterDirection: (r.crossFilteringBehavior === 'bothDirections' || r.crossFilteringBehavior === 'bothWays') ? 'both' : 'single',
      isActive: r.isActive !== false,
    });
  }

  // Roles
  for (const role of (m.roles || [])) {
    const rr = { name: role.name || '', tablePermissions: [] };
    for (const tp of (role.tablePermissions || [])) {
      rr.tablePermissions.push({
        table: tp.name || tp.table || '',
        filterExpression: tp.filterExpression || '',
      });
    }
    model.roles.push(rr);
  }

  return model;
}

function mapCardinality(from, to, behavior) {
  if (from === 'many' && to === 'one') return 'manyToOne';
  if (from === 'one' && to === 'many') return 'oneToMany';
  if (from === 'many' && to === 'many') return 'manyToMany';
  if (from === 'one' && to === 'one') return 'oneToOne';
  // Default for older formats without explicit cardinality
  return 'manyToOne';
}

// --- PBIT Parser ---
async function parsePbit(arrayBuffer) {
  const zip = await JSZip.loadAsync(arrayBuffer);
  const schemaFile = zip.file('DataModelSchema');
  if (!schemaFile) throw new Error('No DataModelSchema found in .pbit file');
  const raw = await schemaFile.async('uint8array');

  // UTF-16LE decode with BOM strip
  const decoder = new TextDecoder('utf-16le');
  let text = decoder.decode(raw);
  if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);

  const json = JSON.parse(text);
  const model = parseBimJson(json);
  model.sourceFormat = 'pbit';
  return model;
}

// --- TMDL Parser ---
function parseTmdl(files) {
  // files: Map<string, string> where key is relative path, value is file content
  const model = emptyModel();
  model.sourceFormat = 'tmdl';

  // Parse model.tmdl
  const modelFile = findFile(files, 'model.tmdl');
  if (modelFile) {
    const lines = modelFile.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('culture:')) model.culture = trimmed.split(':').slice(1).join(':').trim();
    }
  }

  // Parse database.tmdl
  const dbFile = findFile(files, 'database.tmdl');
  if (dbFile) {
    const lines = dbFile.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('compatibilityLevel:')) model.compatibilityLevel = parseInt(trimmed.split(':')[1].trim()) || 0;
      if (trimmed.startsWith('model Model')) { /* just the header */ }
    }
    // Also check for compatibilityLevel
    const clMatch = dbFile.match(/compatibilityLevel:\s*(\d+)/);
    if (clMatch) model.compatibilityLevel = parseInt(clMatch[1]);
  }

  // Parse table files
  for (const [path, content] of files) {
    const lower = path.toLowerCase();
    if (lower.includes('tables/') && lower.endsWith('.tmdl')) {
      const table = parseTmdlTable(content);
      if (table) model.tables.push(table);
    } else if (lower.endsWith('.tmd')) {
      // Alternative .tmd extension
      if (lower.includes('tables/')) {
        const table = parseTmdlTable(content);
        if (table) model.tables.push(table);
      }
    }
  }

  // Parse relationships
  const relFile = findFile(files, 'relationships.tmdl') || findFile(files, 'relationships.tmd');
  if (relFile) {
    model.relationships = parseTmdlRelationships(relFile);
  }

  // Parse roles
  for (const [path, content] of files) {
    const lower = path.toLowerCase();
    if ((lower.includes('roles/') && (lower.endsWith('.tmdl') || lower.endsWith('.tmd')))) {
      const role = parseTmdlRole(content);
      if (role) model.roles.push(role);
    }
  }

  // Set model name from first table or 'Untitled'
  const modelLine = modelFile ? modelFile.match(/^model\s+(.+)/m) : null;
  model.name = modelLine ? modelLine[1].replace(/'/g, '').trim() : 'TMDL Model';

  return model;
}

function findFile(files, name) {
  for (const [path, content] of files) {
    if (path.toLowerCase().endsWith(name.toLowerCase()) ||
        path.toLowerCase().endsWith(name.replace('.tmdl', '.tmd').toLowerCase())) {
      return content;
    }
  }
  return null;
}

function parseTmdlTable(text) {
  const table = emptyTable();
  const lines = text.split('\n');
  let i = 0;

  // Find table declaration
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.startsWith('table ')) {
      table.name = unquoteTmdl(line.substring(6).split('\n')[0].trim());
      i++;
      break;
    }
    if (line.startsWith('/// ')) { i++; continue; } // doc comment before table
    i++;
  }
  if (!table.name) return null;

  // Parse table-level properties and child objects
  let tableDescription = '';
  while (i < lines.length) {
    const rawLine = lines[i];
    const indent = getIndent(rawLine);
    const line = rawLine.trim();

    if (indent === 0 && line && !line.startsWith('///') && !line.startsWith('annotation') &&
        !line.startsWith('changedProperty')) break; // New top-level object

    if (line.startsWith('lineageTag:') || line.startsWith('isHidden') || line.startsWith('description:')) {
      if (line === 'isHidden') table.isHidden = true;
      if (line.startsWith('description:')) tableDescription = line.substring(12).trim();
    }

    // Column
    if (line.startsWith('column ')) {
      const col = parseTmdlColumn(lines, i);
      table.columns.push(col.column);
      i = col.nextIndex;
      continue;
    }

    // Measure
    if (line.startsWith('measure ')) {
      const meas = parseTmdlMeasure(lines, i);
      table.measures.push(meas.measure);
      i = meas.nextIndex;
      continue;
    }

    // Partition
    if (line.startsWith('partition ')) {
      const part = parseTmdlPartition(lines, i);
      table.partitions.push(part.partition);
      if (part.partition.mode === 'directQuery') table.type = 'directQuery';
      if (part.partition.mode === 'dual') table.type = 'dual';
      i = part.nextIndex;
      continue;
    }

    // Calculation items (for calculation group tables)
    if (line.startsWith('calculationItem ')) {
      const ci = parseTmdlCalcItem(lines, i);
      table.calculationItems.push(ci.item);
      table.type = 'calculated';
      i = ci.nextIndex;
      continue;
    }

    // Hierarchy
    if (line.startsWith('hierarchy ')) {
      const h = parseTmdlHierarchy(lines, i);
      table.hierarchies.push(h.hierarchy);
      i = h.nextIndex;
      continue;
    }

    i++;
  }

  table.description = tableDescription;
  return table;
}

function parseTmdlColumn(lines, startIdx) {
  const firstLine = lines[startIdx].trim();
  const nameMatch = firstLine.match(/^column\s+(.+?)$/);
  const col = {
    name: nameMatch ? unquoteTmdl(nameMatch[1].trim()) : '',
    dataType: 'string', type: 'data', isHidden: false,
    expression: null, formatString: '', sortByColumn: null,
    displayFolder: '', description: '',
  };

  const baseIndent = getIndent(lines[startIdx]);
  let i = startIdx + 1;
  let descLines = [];

  // Collect doc comments before the column
  let j = startIdx - 1;
  while (j >= 0 && lines[j].trim().startsWith('///')) {
    descLines.unshift(lines[j].trim().substring(3).trim());
    j--;
  }
  if (descLines.length) col.description = descLines.join(' ');

  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (indent <= baseIndent && line && !line.startsWith('///')) break;
    if (line.startsWith('dataType:')) col.dataType = line.split(':')[1].trim();
    if (line === 'isHidden') col.isHidden = true;
    if (line.startsWith('formatString:')) col.formatString = line.substring(13).trim();
    if (line.startsWith('sortByColumn:')) col.sortByColumn = line.substring(13).trim();
    if (line.startsWith('displayFolder:')) col.displayFolder = line.substring(14).trim();
    if (line.startsWith('expression')) {
      col.type = 'calculated';
      const exprResult = readTmdlExpression(lines, i);
      col.expression = exprResult.text;
      i = exprResult.nextIndex;
      continue;
    }
    i++;
  }
  return { column: col, nextIndex: i };
}

function parseTmdlMeasure(lines, startIdx) {
  const firstLine = lines[startIdx].trim();
  // measure 'Name' = expression OR measure 'Name' = \n (multiline)
  const eqIdx = firstLine.indexOf('=');
  let name = '', expression = '';

  if (eqIdx > 0) {
    name = unquoteTmdl(firstLine.substring(8, eqIdx).trim());
    const afterEq = firstLine.substring(eqIdx + 1).trim();
    if (afterEq === '```' || afterEq === '') {
      // Multi-line expression follows
    } else if (afterEq.startsWith('```')) {
      // Inline triple-backtick
      expression = afterEq;
    } else {
      expression = afterEq;
    }
  } else {
    name = unquoteTmdl(firstLine.substring(8).trim());
  }

  const meas = {
    name, expression, formatString: '', displayFolder: '',
    description: '', isHidden: false,
  };

  const baseIndent = getIndent(lines[startIdx]);
  let i = startIdx + 1;

  // Collect doc comments before
  let descLines = [];
  let j = startIdx - 1;
  while (j >= 0 && lines[j].trim().startsWith('///')) {
    descLines.unshift(lines[j].trim().substring(3).trim());
    j--;
  }
  if (descLines.length) meas.description = descLines.join(' ');

  // Check if expression continues on next lines
  if (!expression || expression === '```') {
    // Read multi-line expression
    if (expression === '```' || (i < lines.length && lines[i].trim().startsWith('```'))) {
      if (expression === '```') {
        // Already consumed opening backticks
      } else if (lines[i].trim() === '```') {
        i++; // skip opening backticks
      }
      let exprLines = [];
      while (i < lines.length) {
        const trimmed = lines[i].trim();
        if (trimmed === '```') { i++; break; }
        exprLines.push(lines[i].replace(/^\t\t\t/, '').replace(/^\t\t/, '')); // remove indent
        i++;
      }
      meas.expression = exprLines.join('\n').trim();
    } else if (!expression) {
      // Multi-line without backticks: indented continuation
      let exprLines = [];
      while (i < lines.length) {
        const indent = getIndent(lines[i]);
        const line = lines[i].trim();
        if (indent <= baseIndent + 1 && line &&
            (line.startsWith('formatString') || line.startsWith('lineageTag') ||
             line.startsWith('displayFolder') || line.startsWith('description') ||
             line.startsWith('annotation') || line.startsWith('changedProperty') ||
             line.startsWith('kpi') || line === 'isHidden')) break;
        if (indent > baseIndent) {
          exprLines.push(lines[i].replace(/^\t\t\t/, '').replace(/^\t\t/, ''));
        } else break;
        i++;
      }
      meas.expression = exprLines.join('\n').trim();
    }
  } else {
    // Single-line expression, check for continuation
    let exprLines = [expression];
    while (i < lines.length) {
      const indent = getIndent(lines[i]);
      const line = lines[i].trim();
      if (indent <= baseIndent + 1 && line &&
          (line.startsWith('formatString') || line.startsWith('lineageTag') ||
           line.startsWith('displayFolder') || line.startsWith('description') ||
           line.startsWith('annotation') || line.startsWith('changedProperty') ||
           line.startsWith('kpi') || line === 'isHidden')) break;
      if (indent > baseIndent && !line.startsWith('formatString') && !line.startsWith('lineageTag')) {
        exprLines.push(lines[i].replace(/^\t\t\t/, '').replace(/^\t\t/, ''));
        i++;
      } else break;
    }
    if (exprLines.length > 1) meas.expression = exprLines.join('\n').trim();
  }

  // Parse remaining properties
  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (indent <= baseIndent && line && !line.startsWith('///') && !line.startsWith('annotation') &&
        !line.startsWith('changedProperty')) break;
    if (line.startsWith('formatString:')) meas.formatString = line.substring(13).trim();
    if (line.startsWith('displayFolder:')) meas.displayFolder = line.substring(14).trim();
    if (line === 'isHidden') meas.isHidden = true;
    if (line.startsWith('description:')) meas.description = line.substring(12).trim();
    // Skip kpi blocks
    if (line.startsWith('kpi')) {
      i++;
      while (i < lines.length && getIndent(lines[i]) > baseIndent + 1) i++;
      continue;
    }
    i++;
  }

  // Clean up backtick expressions
  if (meas.expression.startsWith('```')) {
    meas.expression = meas.expression.replace(/^```\n?/, '').replace(/\n?```$/, '').trim();
  }

  return { measure: meas, nextIndex: i };
}

function parseTmdlPartition(lines, startIdx) {
  const firstLine = lines[startIdx].trim();
  const partition = { type: 'unknown', expression: '', mode: '' };
  const baseIndent = getIndent(lines[startIdx]);

  // partition Name = m | partition Name = dax | etc.
  const eqIdx = firstLine.indexOf('=');
  if (eqIdx > 0) {
    const typeStr = firstLine.substring(eqIdx + 1).trim().toLowerCase();
    if (typeStr === 'm') partition.type = 'm';
    else if (typeStr === 'dax') partition.type = 'dax';
    else if (typeStr === 'entity') partition.type = 'entity';
    else if (typeStr === 'calculated') partition.type = 'calculated';
  }

  let i = startIdx + 1;
  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (indent <= baseIndent && line) break;
    if (line.startsWith('mode:')) partition.mode = line.substring(5).trim();
    if (line.startsWith('source') && line !== 'source') {
      // source = ... or source\n  expression
    } else if (line === 'source' || line.startsWith('source =')) {
      const exprResult = readTmdlExpression(lines, i);
      partition.expression = exprResult.text;
      i = exprResult.nextIndex;
      continue;
    }
    if (line.startsWith('expression')) {
      const exprResult = readTmdlExpression(lines, i);
      partition.expression = exprResult.text;
      i = exprResult.nextIndex;
      continue;
    }
    i++;
  }

  return { partition, nextIndex: i };
}

function parseTmdlCalcItem(lines, startIdx) {
  const firstLine = lines[startIdx].trim();
  const nameMatch = firstLine.match(/^calculationItem\s+(.+?)(\s*=\s*(.*))?$/);
  const item = { name: '', expression: '', ordinal: 0 };
  if (nameMatch) {
    item.name = unquoteTmdl(nameMatch[1].trim());
    if (nameMatch[3]) item.expression = nameMatch[3].trim();
  }
  const baseIndent = getIndent(lines[startIdx]);
  let i = startIdx + 1;
  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (indent <= baseIndent && line) break;
    if (line.startsWith('ordinal:')) item.ordinal = parseInt(line.split(':')[1]) || 0;
    if (line.startsWith('expression')) {
      const exprResult = readTmdlExpression(lines, i);
      item.expression = exprResult.text;
      i = exprResult.nextIndex;
      continue;
    }
    i++;
  }
  return { item, nextIndex: i };
}

function parseTmdlHierarchy(lines, startIdx) {
  const firstLine = lines[startIdx].trim();
  const nameMatch = firstLine.match(/^hierarchy\s+(.+?)$/);
  const hierarchy = { name: nameMatch ? unquoteTmdl(nameMatch[1]) : '', levels: [] };
  const baseIndent = getIndent(lines[startIdx]);
  let i = startIdx + 1;
  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (indent <= baseIndent && line) break;
    if (line.startsWith('level ')) {
      hierarchy.levels.push(unquoteTmdl(line.substring(6).trim()));
    }
    i++;
  }
  return { hierarchy, nextIndex: i };
}

function parseTmdlRelationships(text) {
  const rels = [];
  const lines = text.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.startsWith('relationship ')) {
      const rel = {
        fromTable: '', fromColumn: '', toTable: '', toColumn: '',
        cardinality: 'manyToOne', crossFilterDirection: 'single', isActive: true,
      };
      i++;
      while (i < lines.length) {
        const inner = lines[i].trim();
        if (!inner || (getIndent(lines[i]) === 0 && inner.startsWith('relationship '))) break;
        if (inner.startsWith('fromColumn:')) {
          const parts = inner.substring(11).trim().split('.');
          if (parts.length >= 2) {
            rel.fromTable = unquoteTmdl(parts[0]);
            rel.fromColumn = unquoteTmdl(parts.slice(1).join('.'));
          }
        }
        if (inner.startsWith('toColumn:')) {
          const parts = inner.substring(9).trim().split('.');
          if (parts.length >= 2) {
            rel.toTable = unquoteTmdl(parts[0]);
            rel.toColumn = unquoteTmdl(parts.slice(1).join('.'));
          }
        }
        if (inner.startsWith('crossFilteringBehavior:')) {
          const val = inner.split(':')[1].trim();
          rel.crossFilterDirection = (val === 'bothDirections' || val === 'bothWays') ? 'both' : 'single';
        }
        if (inner.startsWith('fromCardinality:') || inner.startsWith('toCardinality:')) {
          // Handle explicit cardinality
          if (inner.includes('many')) {
            // Would need both sides to determine, use default manyToOne
          }
        }
        if (inner === 'isActive: false' || inner === 'isActive:false') {
          rel.isActive = false;
        }
        i++;
      }
      rels.push(rel);
      continue;
    }
    i++;
  }
  return rels;
}

function parseTmdlRole(text) {
  const lines = text.split('\n');
  const role = { name: '', tablePermissions: [] };
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.startsWith('role ')) {
      role.name = unquoteTmdl(line.substring(5).trim());
      i++;
      while (i < lines.length) {
        const inner = lines[i].trim();
        if (inner.startsWith('tablePermission ')) {
          const tpName = unquoteTmdl(inner.substring(16).trim());
          i++;
          let filterExpr = '';
          while (i < lines.length && getIndent(lines[i]) > 1) {
            const tpLine = lines[i].trim();
            if (tpLine.startsWith('filterExpression')) {
              const exprResult = readTmdlExpression(lines, i);
              filterExpr = exprResult.text;
              i = exprResult.nextIndex;
              continue;
            }
            i++;
          }
          role.tablePermissions.push({ table: tpName, filterExpression: filterExpr });
          continue;
        }
        i++;
      }
      break;
    }
    i++;
  }
  return role.name ? role : null;
}

function readTmdlExpression(lines, startIdx) {
  const baseIndent = getIndent(lines[startIdx]);
  const firstLine = lines[startIdx].trim();
  let i = startIdx + 1;

  // Check for inline expression after =
  const eqIdx = firstLine.indexOf('=');
  if (eqIdx > 0) {
    const afterEq = firstLine.substring(eqIdx + 1).trim();
    if (afterEq && afterEq !== '```') {
      // Single line with possible continuation
      let exprLines = [afterEq];
      while (i < lines.length && getIndent(lines[i]) > baseIndent) {
        const trimmed = lines[i].trim();
        if (trimmed.startsWith('mode:') || trimmed.startsWith('annotation') ||
            trimmed.startsWith('lineageTag')) break;
        exprLines.push(lines[i].replace(/^\t+/, ''));
        i++;
      }
      return { text: exprLines.join('\n').trim(), nextIndex: i };
    }
  }

  // Multi-line: read indented block
  let exprLines = [];
  while (i < lines.length) {
    const indent = getIndent(lines[i]);
    const line = lines[i].trim();
    if (line === '```') { i++; break; } // closing backtick block
    if (indent <= baseIndent && line) break;
    exprLines.push(lines[i].replace(/^\t\t\t/, '').replace(/^\t\t/, ''));
    i++;
  }
  return { text: exprLines.join('\n').trim(), nextIndex: i };
}

function getIndent(line) {
  if (!line) return 0;
  let count = 0;
  for (const ch of line) {
    if (ch === '\t') count++;
    else if (ch === ' ') count += 0.25; // rough
    else break;
  }
  return Math.floor(count);
}

function unquoteTmdl(s) {
  if (!s) return '';
  s = s.trim();
  if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1);
  if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
  return s;
}

// --- PBIX Parser (metadata only via DataModelSchema if present) ---
async function parsePbix(arrayBuffer) {
  const zip = await JSZip.loadAsync(arrayBuffer);

  // Try DataModelSchema first (present in some .pbix)
  const schemaFile = zip.file('DataModelSchema');
  if (schemaFile) {
    const raw = await schemaFile.async('uint8array');
    const decoder = new TextDecoder('utf-16le');
    let text = decoder.decode(raw);
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    const model = parseBimJson(JSON.parse(text));
    model.sourceFormat = 'pbix';
    return model;
  }

  // DataModel (XPress9 compressed) — decompress and extract metadata+data
  const dataModelFile = zip.file('DataModel');
  if (dataModelFile) {
    const dmBuf = await dataModelFile.async('arraybuffer');

    // Decompress XPress9 → parse ABF → read SQLite metadata
    const decompressed = await decompressXpress9(dmBuf);
    const abf = parseABF(decompressed);
    const sqliteBuf = getDataSlice(abf, 'metadata.sqlitedb');
    const db = readSQLiteTables(sqliteBuf);

    // Build the semantic model from SQLite metadata
    const model = buildModelFromSQLite(db);
    model.sourceFormat = 'pbix';

    // Build column schema for data extraction (Data tab)
    const schema = buildSchemaFromSQLite(db);
    const tableNames = Array.from(schema.keys()).sort();

    // Pre-extract needed file slices, then release the large decompressed buffer
    const fileCache = _buildFileCache(schema, abf);
    abf.data = null; // allow GC of the decompressed DataModel

    // Store for Data tab
    model._pbixDataModel = {
      tableNames,
      schema,
      getTable(tableName) {
        return extractTableData(tableName, schema, fileCache);
      },
      getTableStreaming(tableName, onProgress) {
        return extractTableDataStreaming(tableName, schema, fileCache, onProgress);
      },
      getTableStats(tableName, onProgress) {
        return extractTableStatsStreaming(tableName, schema, fileCache, onProgress);
      }
    };

    return model;
  }

  throw new Error('No DataModelSchema or DataModel found in .pbix file');
}

/**
 * Build the semantic model from the metadata.sqlitedb tables.
 * Uses rowid as ID for all tables (INTEGER PRIMARY KEY is aliased to rowid).
 *
 * Column indices from CREATE TABLE SQL:
 *   Table: rowid=ID, [2]=Name, [4]=Description, [5]=IsHidden
 *   Column: rowid=ID, [1]=TableID, [2]=ExplicitName, [4]=ExplicitDataType,
 *     [7]=Description, [8]=IsHidden, [19]=Type, [22]=Expression
 *   Measure: rowid=ID, [1]=TableID, [2]=Name, [3]=Description, [5]=Expression
 */
function buildModelFromSQLite(db) {
  const model = emptyModel();

  const tableRows = db.getTableRows('Table');
  const tableMap = new Map();

  for (const r of tableRows) {
    const name = r.values[2] || 'Table_' + r.rowid;
    // Skip internal tables (auto-date, hierarchy, relationship, utility)
    if (name.startsWith('LocalDateTable_') ||
        name.startsWith('DateTableTemplate_') ||
        name.startsWith('H$') ||
        name.startsWith('R$') ||
        name.startsWith('U$')) continue;
    const t = emptyTable();
    t.name = name;
    t.description = r.values[4] || '';
    t.isHidden = !!r.values[5];
    model.tables.push(t);
    tableMap.set(r.rowid, t);
  }

  const columnRows = db.getTableRows('Column');
  for (const r of columnRows) {
    const table = tableMap.get(r.values[1]);
    if (!table) continue;
    const colType = r.values[19];
    if (colType === 3) continue;
    const col = {
      name: r.values[2] || '',
      description: r.values[7] || '',
      dataType: mapSQLiteDataType(r.values[4]),
      isHidden: !!r.values[8],
      expression: r.values[22] || '',
    };
    if (colType === 2) col.type = 'calculated';
    table.columns.push(col);
  }

  const measureRows = db.getTableRows('Measure');
  for (const r of measureRows) {
    const table = tableMap.get(r.values[1]);
    if (!table) continue;
    table.measures.push({
      name: r.values[2] || '',
      description: r.values[3] || '',
      expression: r.values[5] || '',
      formatString: r.values[6] || '',
      isHidden: !!r.values[7]
    });
  }

  // Relationships
  // Column indices from CREATE TABLE Relationship:
  //   [3]=IsActive, [5]=CrossFilteringBehavior,
  //   [8]=FromTableID, [9]=FromColumnID, [10]=FromCardinality,
  //   [11]=ToTableID, [12]=ToColumnID, [13]=ToCardinality
  const relRows = db.getTableRows('Relationship');
  const colIdToName = new Map();
  for (const r of columnRows) {
    colIdToName.set(r.rowid, r.values[2]);
  }
  const tableIdToName = new Map();
  for (const r of tableRows) {
    tableIdToName.set(r.rowid, r.values[2]);
  }

  for (const r of relRows) {
    const vals = r.values;
    const fromTableName = tableIdToName.get(vals[8]) || '';
    const toTableName = tableIdToName.get(vals[11]) || '';
    // Skip relationships involving internal tables
    if (!tableMap.has(vals[8]) || !tableMap.has(vals[11])) continue;

    const fromCard = vals[10] === 2 ? 'many' : 'one';
    const toCard = vals[13] === 2 ? 'many' : 'one';

    model.relationships.push({
      fromTable: fromTableName,
      fromColumn: colIdToName.get(vals[9]) || '',
      toTable: toTableName,
      toColumn: colIdToName.get(vals[12]) || '',
      crossFilterBehavior: vals[5] === 2 ? 'bothDirections' : 'oneDirection',
      isActive: vals[3] !== 0,
      cardinality: mapCardinality(fromCard, toCard)
    });
  }

  // Roles
  const roleRows = db.getTableRows('Role');
  const tablePermRows = db.getTableRows('TablePermission');
  for (const r of roleRows) {
    const role = { name: r.values[2] || '', modelPermission: 'read', tablePermissions: [] };
    if (tablePermRows) {
      for (const tp of tablePermRows) {
        if (tp.values[1] === r.rowid) {
          role.tablePermissions.push({
            table: tableIdToName.get(tp.values[2]) || '',
            filterExpression: tp.values[3] || ''
          });
        }
      }
    }
    if (role.tablePermissions.length > 0) model.roles.push(role);
  }

  return model;
}

function mapSQLiteDataType(amoType) {
  switch (amoType) {
    case 2: return 'string';
    case 6: return 'int64';
    case 8: return 'double';
    case 9: return 'dateTime';
    case 10: return 'decimal';
    case 11: return 'boolean';
    case 17: return 'binary';
    default: return 'string';
  }
}

// --- Main parse entry point ---
async function parseFile(file) {
  const name = file.name || '';
  const ext = name.toLowerCase().split('.').pop();
  const arrayBuffer = await file.arrayBuffer();

  // Auto-detect format
  const bytes = new Uint8Array(arrayBuffer.slice(0, 4));
  const isZip = (bytes[0] === 0x50 && bytes[1] === 0x4B);

  if (ext === 'bim' || (!isZip && ext !== 'tmdl' && ext !== 'tmd')) {
    // Try as BIM JSON
    try {
      const text = new TextDecoder('utf-8').decode(arrayBuffer);
      const json = JSON.parse(text);
      const model = parseBimJson(json);
      model.sourceFormat = 'bim';
      model.name = model.name || name.replace(/\.[^.]+$/, '');
      return model;
    } catch (e) {
      throw new Error('Failed to parse as BIM/JSON: ' + e.message);
    }
  }

  if (isZip) {
    const zip = await JSZip.loadAsync(arrayBuffer);

    // Check for .pbit (has DataModelSchema)
    if (zip.file('DataModelSchema')) {
      const model = await parsePbit(arrayBuffer);
      model.name = model.name || name.replace(/\.[^.]+$/, '');
      return model;
    }

    // Check for .pbix
    if (zip.file('DataModel') || zip.file('Connections')) {
      const model = await parsePbix(arrayBuffer);
      model.name = model.name || name.replace(/\.[^.]+$/, '');
      return model;
    }

    // Check for zipped PBIP folder
    const tmdlFiles = new Map();
    let hasTmdl = false;
    let bimContent = null;

    zip.forEach((path, entry) => {
      if (path.endsWith('.tmdl') || path.endsWith('.tmd')) {
        hasTmdl = true;
      }
      if (path.endsWith('model.bim') || path.endsWith('Model.bim')) {
        bimContent = entry;
      }
    });

    if (hasTmdl) {
      for (const [path, entry] of Object.entries(zip.files)) {
        if (!entry.dir && (path.endsWith('.tmdl') || path.endsWith('.tmd'))) {
          const content = await entry.async('string');
          tmdlFiles.set(path, content);
        }
      }
      const model = parseTmdl(tmdlFiles);
      model.name = model.name || name.replace(/\.[^.]+$/, '');
      return model;
    }

    if (bimContent) {
      const text = await bimContent.async('string');
      const model = parseBimJson(JSON.parse(text));
      model.sourceFormat = 'bim';
      model.name = model.name || name.replace(/\.[^.]+$/, '');
      return model;
    }

    throw new Error('Could not identify the format inside this ZIP file');
  }

  throw new Error('Unrecognized file format. Supported: .pbix, .pbit, .pbip, .bim');
}

// Parse folder (from drag-and-drop)
async function parseFolder(entries) {
  const files = new Map();
  for (const entry of entries) {
    if (entry.name.endsWith('.tmdl') || entry.name.endsWith('.tmd')) {
      const file = await getFileFromEntry(entry);
      const text = await file.text();
      files.set(entry.fullPath || entry.name, text);
    }
    if (entry.name === 'model.bim' || entry.name === 'Model.bim') {
      const file = await getFileFromEntry(entry);
      const text = await file.text();
      const model = parseBimJson(JSON.parse(text));
      model.sourceFormat = 'bim';
      return model;
    }
  }
  if (files.size > 0) {
    return parseTmdl(files);
  }
  throw new Error('No .tmdl or model.bim files found in folder');
}

function getFileFromEntry(entry) {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

async function readAllEntries(dirEntry) {
  const entries = [];
  const reader = dirEntry.createReader();
  const readBatch = () => new Promise((resolve, reject) => {
    reader.readEntries(resolve, reject);
  });
  let batch;
  do {
    batch = await readBatch();
    entries.push(...batch);
  } while (batch.length > 0);
  return entries;
}

async function flattenEntries(items) {
  const result = [];
  const queue = [...items];
  while (queue.length > 0) {
    const entry = queue.shift();
    if (entry.isFile) {
      result.push(entry);
    } else if (entry.isDirectory) {
      const children = await readAllEntries(entry);
      queue.push(...children);
    }
  }
  return result;
}

// ============================================================
// DATA PROFILE — Column statistics for LLM copy
// ============================================================

/**
 * Compute statistics for a single column's data array.
 * Designed for streaming: call this on one column at a time, then release the data.
 * @param {string} name - Column name
 * @param {any[]} data - Column values
 * @returns {Object} { name, distinct, nulls, rowCount, min?, max?, avg?, top? }
 */
function _computeColumnStats(name, data) {
  const stat = { name, distinct: 0, nulls: 0, rowCount: data.length };

  let nullCount = 0;
  const seen = new Set();
  const freq = new Map();
  let numCount = 0, numSum = 0, numMin = Infinity, numMax = -Infinity;
  let dateMin = null, dateMax = null;
  let isNumeric = false, isDate = false;

  for (let r = 0; r < data.length; r++) {
    const v = data[r];
    if (v == null) { nullCount++; continue; }

    if (typeof v === 'number' && isFinite(v)) {
      isNumeric = true;
      numCount++;
      numSum += v;
      if (v < numMin) numMin = v;
      if (v > numMax) numMax = v;
    } else if (v instanceof Date) {
      isDate = true;
      if (!dateMin || v < dateMin) dateMin = v;
      if (!dateMax || v > dateMax) dateMax = v;
    }

    // Track frequency for top values (cap map size to avoid memory blow-up)
    const key = v instanceof Date ? v.getTime() : v;
    seen.add(key);
    if (freq.size < 10000) {
      freq.set(key, (freq.get(key) || 0) + 1);
    }
  }

  stat.distinct = seen.size;
  stat.nulls = nullCount;

  if (isNumeric && numCount > 0) {
    stat.min = numMin;
    stat.max = numMax;
    stat.avg = Math.round((numSum / numCount) * 100) / 100;
  }

  if (isDate) {
    stat.min = dateMin;
    stat.max = dateMax;
  }

  // Top values: up to 5 most frequent (for string/low-cardinality columns)
  if (!isNumeric && !isDate && freq.size > 0 && freq.size <= 1000) {
    const sorted = [...freq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    stat.top = sorted.map(([val, count]) => ({
      value: String(val),
      count,
    }));
  }

  return stat;
}

/**
 * Compute stats for all tables. Memory-efficient: extracts one column at a time
 * via getTableStats(), computes stats, then releases column data before the next.
 * Caches results in appState.statsCache.
 *
 * @param {Object} pbixDataModel
 * @param {Function} onProgress - (tableIdx, totalTables, tableName) => void
 * @returns {Promise<Map<string, Object[]>>}
 */
async function computeAllStats(pbixDataModel, onProgress) {
  if (appState.statsCache) return appState.statsCache;

  const statsMap = new Map();
  const names = pbixDataModel.tableNames;

  for (let i = 0; i < names.length; i++) {
    const name = names[i];
    if (onProgress) onProgress(i, names.length, name);

    try {
      const tableStats = await pbixDataModel.getTableStats(name, () => {});
      if (tableStats) statsMap.set(name, tableStats);
    } catch (e) {
      // Skip tables that fail to extract
    }
    // Yield to event loop
    await new Promise(r => setTimeout(r, 0));
  }

  appState.statsCache = statsMap;
  return statsMap;
}

/**
 * Format a stat value for display in markdown.
 */
function _formatStatVal(v) {
  if (v instanceof Date) return v.toISOString().split('T')[0];
  if (typeof v === 'number') {
    if (Math.abs(v) >= 1e6) return v.toExponential(2);
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}

// ============================================================
// MARKDOWN EXPORT
// ============================================================

function modelToMarkdown(model, items, statsMap) {
  // items: null = everything, or Set of item keys
  // statsMap: null = no stats, or Map<tableName, columnStats[]>
  const lines = [];
  const all = !items;

  const tableCount = model.tables.length;
  const measureCount = model.tables.reduce((s, t) => s + t.measures.length, 0);
  const relCount = model.relationships.length;

  lines.push(`# Model: ${model.name}`);
  lines.push(`Compatibility Level: ${model.compatibilityLevel || 'N/A'} | Tables: ${tableCount} | Measures: ${measureCount} | Relationships: ${relCount}`);
  lines.push('');

  // Tables
  const tablesIncluded = model.tables.filter(t => all || items.has('table:' + t.name));
  if (tablesIncluded.length > 0) {
    lines.push('## Tables');
    lines.push('');
    for (const t of tablesIncluded) {
      const typeBadge = t.type !== 'import' ? ` [${t.type}]` : '';
      lines.push(`### ${t.name}${typeBadge}`);
      if (t.description) lines.push(`> ${t.description}`);

      if (t.columns.length > 0) {
        lines.push('| Column | Type | Hidden | Calculated | Format |');
        lines.push('|--------|------|:------:|:----------:|--------|');
        for (const c of t.columns) {
          const hidden = c.isHidden ? 'Yes' : '';
          const calc = c.type === 'calculated' ? 'Yes' : '';
          lines.push(`| ${c.name} | ${c.dataType} | ${hidden} | ${calc} | ${c.formatString || ''} |`);
        }
      }

      // Data profile (inline bullets, only when statsMap provided)
      const tStats = statsMap ? statsMap.get(t.name) : null;
      if (tStats && tStats.length > 0) {
        const rowCount = tStats[0].rowCount || 0;
        lines.push('');
        lines.push(`**Data profile** (${formatNum(rowCount)} rows):`);
        for (const s of tStats) {
          let line = `- **${s.name}** -- ${formatNum(s.distinct)} distinct, ${formatNum(s.nulls)} nulls`;
          if (s.avg !== undefined) {
            line += `, avg: ${_formatStatVal(s.avg)}, range: ${_formatStatVal(s.min)} .. ${_formatStatVal(s.max)}`;
          } else if (s.min !== undefined) {
            line += `, range: ${_formatStatVal(s.min)} .. ${_formatStatVal(s.max)}`;
          }
          if (s.top && s.top.length > 0) {
            const topStr = s.top.map(t => `${t.value} (${formatNum(t.count)})`).join(', ');
            line += `, top: ${topStr}`;
          }
          lines.push(line);
        }
      }

      // Partition source
      const mPartition = t.partitions.find(p => p.type === 'm' && p.expression);
      if (mPartition) {
        lines.push('');
        lines.push('Source (M):');
        lines.push('```');
        lines.push(mPartition.expression);
        lines.push('```');
      }

      // Calculated columns
      const calcCols = t.columns.filter(c => c.type === 'calculated' && c.expression);
      if (calcCols.length > 0) {
        lines.push('');
        for (const c of calcCols) {
          lines.push(`**${t.name}[${c.name}]** (calculated column)`);
          lines.push('```dax');
          lines.push(c.expression);
          lines.push('```');
        }
      }

      lines.push('');
    }
  }

  // Measures
  const allMeasures = [];
  for (const t of model.tables) {
    for (const m of t.measures) {
      if (all || items.has('measure:' + t.name + ':' + m.name)) {
        allMeasures.push({ ...m, tableName: t.name });
      }
    }
  }

  if (allMeasures.length > 0) {
    lines.push('## Measures');
    lines.push('');

    // Group by table
    const byTable = {};
    for (const m of allMeasures) {
      (byTable[m.tableName] = byTable[m.tableName] || []).push(m);
    }

    for (const [tName, measures] of Object.entries(byTable)) {
      lines.push(`### Table: ${tName}`);
      lines.push('');
      for (const m of measures) {
        const fmt = m.formatString ? ` | Format: ${m.formatString}` : '';
        lines.push(`**${m.name}**${fmt}`);
        if (m.description) lines.push(`> ${m.description}`);
        lines.push('```dax');
        lines.push(m.expression);
        lines.push('```');
        lines.push('');
      }
    }
  }

  // Calculation Groups
  const calcGroups = model.tables.filter(t => t.calculationItems.length > 0 && (all || items.has('table:' + t.name)));
  if (calcGroups.length > 0) {
    lines.push('## Calculation Groups');
    lines.push('');
    for (const t of calcGroups) {
      lines.push(`### ${t.name}`);
      for (const ci of t.calculationItems) {
        lines.push(`**${ci.name}**`);
        lines.push('```dax');
        lines.push(ci.expression);
        lines.push('```');
        lines.push('');
      }
    }
  }

  // Relationships
  const relsIncluded = all ? model.relationships : model.relationships.filter(r => items.has('rel:' + r.fromTable + ':' + r.fromColumn + ':' + r.toTable + ':' + r.toColumn));
  if (relsIncluded.length > 0) {
    lines.push('## Relationships');
    lines.push('| From | To | Cardinality | Direction | Active |');
    lines.push('|------|-----|:-----------:|:---------:|:------:|');
    for (const r of relsIncluded) {
      const card = cardinalityLabel(r.cardinality);
      const dir = r.crossFilterDirection === 'both' ? 'Both' : 'Single';
      const active = r.isActive ? 'Yes' : 'No';
      lines.push(`| ${r.fromTable}[${r.fromColumn}] | ${r.toTable}[${r.toColumn}] | ${card} | ${dir} | ${active} |`);
    }
    lines.push('');
  }

  // Roles
  const rolesIncluded = all ? model.roles : model.roles.filter(r => items.has('role:' + r.name));
  if (rolesIncluded.length > 0) {
    lines.push('## Roles');
    lines.push('');
    for (const r of rolesIncluded) {
      lines.push(`**${r.name}**`);
      for (const tp of r.tablePermissions) {
        if (tp.filterExpression) {
          lines.push(`- ${tp.table}: \`${tp.filterExpression}\``);
        }
      }
      lines.push('');
    }
  }

  return lines.join('\n');
}

function cardinalityLabel(c) {
  switch (c) {
    case 'manyToOne': return '*:1';
    case 'oneToMany': return '1:*';
    case 'oneToOne': return '1:1';
    case 'manyToMany': return '*:*';
    default: return c || '*:1';
  }
}

// ============================================================
// UI RENDERING
// ============================================================

function renderApp(model) {
  appState.model = model;
  appState.checkedItems = new Set();
  appState.selectedItem = null;

  // Header
  $('modelName').textContent = model.name || 'Untitled Model';
  $('modelFormat').textContent = model.sourceFormat || 'unknown';

  const tableCount = model.tables.length;
  const measureCount = model.tables.reduce((s, t) => s + t.measures.length, 0);
  const relCount = model.relationships.length;
  const roleCount = model.roles.length;
  let stats = `${tableCount} Tables | ${measureCount} Measures | ${relCount} Relationships`;
  if (roleCount > 0) stats += ` | ${roleCount} Roles`;
  if (model.compatibilityLevel) stats += ` | CL ${model.compatibilityLevel}`;
  $('modelStats').textContent = stats;

  // Update token badge for full model
  const fullMd = modelToMarkdown(model, null);
  $('tokenBadge').textContent = `~${formatNum(estimateTokens(fullMd))} tokens`;

  renderTree(model);
  $('detailPanel').innerHTML = '<div class="detail-empty">Select an item to see details</div>';
  updateSelectedTokens();

  // Initialize Data tab if .pbix data model is available
  if (model._pbixDataModel && typeof initDataTab === 'function') {
    appState.pbixDataModel = model._pbixDataModel;
    appState.statsCache = null; // clear stats cache for new file
    initDataTab(model._pbixDataModel);
    // Show data profile checkboxes
    $('includeStatsHeaderWrap').style.display = '';
    $('includeStatsWrap').style.display = '';
  } else {
    // Hide Data tab and stats checkboxes for non-pbix files
    const dataTabBtn = $('dataTabBtn');
    if (dataTabBtn) dataTabBtn.style.display = 'none';
    $('includeStatsHeaderWrap').style.display = 'none';
    $('includeStatsWrap').style.display = 'none';
  }
}

function renderTree(model, filter = '') {
  const tree = $('treeScroll');
  tree.innerHTML = '';
  const showHidden = $('showHidden').checked;
  const lowerFilter = filter.toLowerCase();

  // Tables section
  const tablesHtml = renderTreeSection('Tables', model.tables.length, () => {
    let html = '';
    for (const t of model.tables) {
      if (!showHidden && t.isHidden) continue;
      if (lowerFilter && !tableMatchesFilter(t, lowerFilter)) continue;
      const key = 'table:' + t.name;
      const checked = appState.checkedItems.has(key) ? 'checked' : '';
      const hiddenClass = t.isHidden ? ' hidden-obj' : '';
      const colCount = t.columns.length;
      const measCount = t.measures.length;
      let meta = `${colCount}c`;
      if (measCount > 0) meta += ` ${measCount}m`;
      html += `<div class="tree-item${hiddenClass}" data-key="${escHtml(key)}">
        <input type="checkbox" ${checked} data-check="${escHtml(key)}">
        <span class="tree-item-label">${escHtml(t.name)}</span>
        <span class="tree-item-meta">${meta}</span>
      </div>`;
    }
    return html;
  });

  // Measures section
  const measuresHtml = renderTreeSection('Measures', model.tables.reduce((s, t) => s + t.measures.length, 0), () => {
    let html = '';
    for (const t of model.tables) {
      const measures = t.measures.filter(m => {
        if (!showHidden && m.isHidden) return false;
        if (lowerFilter && !m.name.toLowerCase().includes(lowerFilter) &&
            !m.expression.toLowerCase().includes(lowerFilter) &&
            !t.name.toLowerCase().includes(lowerFilter)) return false;
        return true;
      });
      if (measures.length === 0) continue;

      // Group by display folder
      const folders = {};
      for (const m of measures) {
        const folder = m.displayFolder || '(no folder)';
        (folders[folder] = folders[folder] || []).push(m);
      }

      const foldersArr = Object.entries(folders);
      const hasMultipleFolders = foldersArr.length > 1 || (foldersArr.length === 1 && foldersArr[0][0] !== '(no folder)');

      html += `<div class="tree-group-header" onclick="this.classList.toggle('collapsed')">
        <span class="arrow">&#9660;</span> ${escHtml(t.name)} (${measures.length})
      </div><div class="tree-group-body">`;

      for (const [folder, fMeasures] of foldersArr) {
        if (hasMultipleFolders) {
          html += `<div class="tree-group-header" style="padding-left:38px" onclick="this.classList.toggle('collapsed')">
            <span class="arrow">&#9660;</span> ${escHtml(folder)}
          </div><div class="tree-group-body">`;
        }
        for (const m of fMeasures) {
          const key = 'measure:' + t.name + ':' + m.name;
          const checked = appState.checkedItems.has(key) ? 'checked' : '';
          const hiddenClass = m.isHidden ? ' hidden-obj' : '';
          const indent = hasMultipleFolders ? ' tree-item-indent2' : '';
          html += `<div class="tree-item${hiddenClass}${indent}" data-key="${escHtml(key)}">
            <input type="checkbox" ${checked} data-check="${escHtml(key)}">
            <span class="tree-item-label">${escHtml(m.name)}</span>
          </div>`;
        }
        if (hasMultipleFolders) html += '</div>';
      }

      html += '</div>';
    }
    return html;
  });

  // Relationships section
  const relsHtml = renderTreeSection('Relationships', model.relationships.length, () => {
    let html = '';
    for (const r of model.relationships) {
      if (lowerFilter && !r.fromTable.toLowerCase().includes(lowerFilter) &&
          !r.toTable.toLowerCase().includes(lowerFilter)) continue;
      const key = 'rel:' + r.fromTable + ':' + r.fromColumn + ':' + r.toTable + ':' + r.toColumn;
      const checked = appState.checkedItems.has(key) ? 'checked' : '';
      const label = `${r.fromTable} → ${r.toTable}`;
      const meta = cardinalityLabel(r.cardinality);
      const inactive = r.isActive ? '' : ' (inactive)';
      html += `<div class="tree-item" data-key="${escHtml(key)}">
        <input type="checkbox" ${checked} data-check="${escHtml(key)}">
        <span class="tree-item-label">${escHtml(label)}${inactive}</span>
        <span class="tree-item-meta">${meta}</span>
      </div>`;
    }
    return html;
  });

  // Roles section
  const rolesHtml = model.roles.length > 0 ? renderTreeSection('Roles', model.roles.length, () => {
    let html = '';
    for (const r of model.roles) {
      if (lowerFilter && !r.name.toLowerCase().includes(lowerFilter)) continue;
      const key = 'role:' + r.name;
      const checked = appState.checkedItems.has(key) ? 'checked' : '';
      html += `<div class="tree-item" data-key="${escHtml(key)}">
        <input type="checkbox" ${checked} data-check="${escHtml(key)}">
        <span class="tree-item-label">${escHtml(r.name)}</span>
      </div>`;
    }
    return html;
  }) : '';

  tree.innerHTML = tablesHtml + measuresHtml + relsHtml + rolesHtml;
}

function renderTreeSection(title, count, contentFn) {
  return `<div class="tree-section">
    <div class="tree-section-header" onclick="this.classList.toggle('collapsed')">
      <span class="arrow">&#9660;</span> ${title} (${count})
    </div>
    <div class="tree-section-body">${contentFn()}</div>
  </div>`;
}

function tableMatchesFilter(t, filter) {
  if (t.name.toLowerCase().includes(filter)) return true;
  for (const c of t.columns) if (c.name.toLowerCase().includes(filter)) return true;
  for (const m of t.measures) {
    if (m.name.toLowerCase().includes(filter)) return true;
    if (m.expression.toLowerCase().includes(filter)) return true;
  }
  return false;
}

// Detail panel rendering
function renderDetail(key) {
  const panel = $('detailPanel');
  if (!key || !appState.model) {
    panel.innerHTML = '<div class="detail-empty">Select an item to see details</div>';
    return;
  }

  const parts = key.split(':');
  const type = parts[0];

  if (type === 'table') {
    const tName = parts[1];
    const table = appState.model.tables.find(t => t.name === tName);
    if (!table) return;
    renderTableDetail(panel, table);
  } else if (type === 'measure') {
    const tName = parts[1];
    const mName = parts.slice(2).join(':');
    const table = appState.model.tables.find(t => t.name === tName);
    const measure = table ? table.measures.find(m => m.name === mName) : null;
    if (!measure) return;
    renderMeasureDetail(panel, measure, tName);
  } else if (type === 'rel') {
    const r = appState.model.relationships.find(r =>
      r.fromTable === parts[1] && r.fromColumn === parts[2] &&
      r.toTable === parts[3] && r.toColumn === parts[4]);
    if (!r) return;
    renderRelDetail(panel, r);
  } else if (type === 'role') {
    const role = appState.model.roles.find(r => r.name === parts[1]);
    if (!role) return;
    renderRoleDetail(panel, role);
  }
}

function renderTableDetail(panel, table) {
  const typeBadge = table.type !== 'import' ? `<span class="badge badge-type">${table.type}</span>` : '<span class="badge badge-type">import</span>';
  let html = `<div class="detail-title">${escHtml(table.name)} ${typeBadge}</div>`;
  if (table.isHidden) html += '<span class="badge badge-hidden">hidden</span>';
  if (table.description) html += `<div class="detail-subtitle">${escHtml(table.description)}</div>`;
  else html += '<div class="detail-subtitle">&nbsp;</div>';

  // Columns table
  if (table.columns.length > 0) {
    html += '<div class="detail-section"><div class="detail-section-title">Columns</div>';
    html += '<table class="detail-table"><tr><th>Name</th><th>Type</th><th>Format</th><th></th></tr>';
    for (const c of table.columns) {
      const badges = [];
      if (c.isHidden) badges.push('<span class="badge badge-hidden">hidden</span>');
      if (c.type === 'calculated') badges.push('<span class="badge badge-calc">calc</span>');
      html += `<tr><td>${escHtml(c.name)}</td><td>${escHtml(c.dataType)}</td><td>${escHtml(c.formatString || '')}</td><td>${badges.join(' ')}</td></tr>`;
    }
    html += '</table></div>';
  }

  // Measures
  if (table.measures.length > 0) {
    html += `<div class="detail-section"><div class="detail-section-title">Measures (${table.measures.length})</div>`;
    for (const m of table.measures) {
      html += `<div style="margin-bottom:8px"><strong>${escHtml(m.name)}</strong>`;
      if (m.formatString) html += ` <span class="badge">${escHtml(m.formatString)}</span>`;
      html += `<div class="detail-code" style="margin-top:4px">${highlightDax(m.expression)}</div></div>`;
    }
    html += '</div>';
  }

  // Partition source
  const mPart = table.partitions.find(p => p.expression);
  if (mPart) {
    html += `<div class="detail-section"><div class="detail-section-title">Source (${mPart.type})</div>`;
    html += `<div class="detail-code">${escHtml(mPart.expression)}</div></div>`;
  }

  // Calculation items
  if (table.calculationItems.length > 0) {
    html += '<div class="detail-section"><div class="detail-section-title">Calculation Items</div>';
    for (const ci of table.calculationItems) {
      html += `<div style="margin-bottom:8px"><strong>${escHtml(ci.name)}</strong>`;
      html += `<div class="detail-code" style="margin-top:4px">${highlightDax(ci.expression)}</div></div>`;
    }
    html += '</div>';
  }

  panel.innerHTML = html;
}

function renderMeasureDetail(panel, measure, tableName) {
  let html = `<div class="detail-title">${escHtml(measure.name)}</div>`;
  html += `<div class="detail-subtitle">Table: ${escHtml(tableName)}</div>`;

  html += '<div class="detail-section">';
  html += `<div class="detail-code"><button class="copy-code-btn" onclick="copyDax(this)">Copy DAX</button>${highlightDax(measure.expression)}</div>`;
  html += '</div>';

  html += '<div class="detail-section"><dl class="detail-meta">';
  if (measure.formatString) html += `<dt>Format</dt><dd>${escHtml(measure.formatString)}</dd>`;
  if (measure.displayFolder) html += `<dt>Folder</dt><dd>${escHtml(measure.displayFolder)}</dd>`;
  if (measure.description) html += `<dt>Description</dt><dd>${escHtml(measure.description)}</dd>`;
  if (measure.isHidden) html += '<dt>Hidden</dt><dd>Yes</dd>';
  html += '</dl></div>';

  panel.innerHTML = html;
}

function renderRelDetail(panel, r) {
  const card = cardinalityLabel(r.cardinality);
  const dir = r.crossFilterDirection === 'both' ? 'Both' : 'Single';
  let html = `<div class="detail-title">${escHtml(r.fromTable)} → ${escHtml(r.toTable)}</div>`;
  html += `<div class="detail-subtitle">${escHtml(r.fromColumn)} → ${escHtml(r.toColumn)}</div>`;
  html += '<div class="detail-section"><dl class="detail-meta">';
  html += `<dt>Cardinality</dt><dd>${card}</dd>`;
  html += `<dt>Filter Direction</dt><dd>${dir}</dd>`;
  html += `<dt>Active</dt><dd>${r.isActive ? 'Yes' : 'No'}</dd>`;
  html += '</dl></div>';
  panel.innerHTML = html;
}

function renderRoleDetail(panel, role) {
  let html = `<div class="detail-title">${escHtml(role.name)}</div>`;
  html += '<div class="detail-subtitle">Security Role</div>';
  if (role.tablePermissions.length > 0) {
    html += '<div class="detail-section"><div class="detail-section-title">Table Permissions</div>';
    for (const tp of role.tablePermissions) {
      html += `<div style="margin-bottom:6px"><strong>${escHtml(tp.table)}</strong>`;
      if (tp.filterExpression) {
        html += `<div class="detail-code" style="margin-top:4px">${highlightDax(tp.filterExpression)}</div>`;
      } else {
        html += '<div style="color:var(--text2);font-size:12px">(no filter — full access)</div>';
      }
      html += '</div>';
    }
    html += '</div>';
  }
  panel.innerHTML = html;
}

// Basic DAX syntax highlighting
function highlightDax(code) {
  if (!code) return '';
  code = escHtml(code);
  // Comments
  code = code.replace(/(\/\/.*$)/gm, '<span class="dax-cm">$1</span>');
  code = code.replace(/(--.*$)/gm, '<span class="dax-cm">$1</span>');
  // Strings
  code = code.replace(/(&quot;[^&]*?&quot;)/g, '<span class="dax-str">$1</span>');
  // Numbers
  code = code.replace(/\b(\d+\.?\d*)\b/g, '<span class="dax-num">$1</span>');
  // Keywords
  const kws = ['VAR','RETURN','IF','SWITCH','TRUE','FALSE','NOT','AND','OR','IN','BLANK','ISBLANK','DEFINE','EVALUATE','ORDER BY','ASC','DESC'];
  for (const kw of kws) {
    code = code.replace(new RegExp('\\b(' + kw + ')\\b', 'gi'), '<span class="dax-kw">$1</span>');
  }
  return code;
}

function copyDax(btn) {
  const code = btn.parentElement.textContent.replace('Copy DAX', '').trim();
  copyText(code).then(() => toast('DAX copied'));
}

// ============================================================
// DIAGRAM (Cytoscape.js)
// ============================================================

function renderDiagram(model) {
  if (!window.cytoscape) {
    $('diagramContainer').innerHTML = '<div style="padding:40px;text-align:center;color:var(--text2)">Diagram library not available</div>';
    return;
  }

  const showHidden = $('dgShowHidden').checked;
  const elements = [];

  // Nodes (tables)
  for (const t of model.tables) {
    if (!showHidden && t.isHidden) continue;
    const measCount = t.measures.length;
    const colCount = t.columns.length;
    let label = t.name;
    elements.push({
      group: 'nodes',
      data: {
        id: t.name,
        label,
        type: t.type,
        colCount,
        measCount,
        isHidden: t.isHidden,
      },
    });
  }

  // Edges (relationships)
  for (const r of model.relationships) {
    const fromExists = elements.some(e => e.data.id === r.fromTable);
    const toExists = elements.some(e => e.data.id === r.toTable);
    if (!fromExists || !toExists) continue;

    const card = cardinalityLabel(r.cardinality);
    // Arrow direction: from dimension (one/toTable) → fact (many/fromTable)
    elements.push({
      group: 'edges',
      data: {
        id: `${r.fromTable}_${r.fromColumn}_${r.toTable}_${r.toColumn}`,
        source: r.toTable,
        target: r.fromTable,
        label: `${r.toColumn} → ${r.fromColumn} (${card})`,
        cardinality: card,
        direction: r.crossFilterDirection,
        isActive: r.isActive,
        fromColumn: r.fromColumn,
        toColumn: r.toColumn,
        fromTable: r.fromTable,
        toTable: r.toTable,
      },
    });
  }

  if (appState.cy) {
    appState.cy.destroy();
  }

  const cy = cytoscape({
    container: $('diagramContainer'),
    elements,
    style: [
      {
        selector: 'node',
        style: {
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': '#2d4a3e',
          'color': '#e0e0e8',
          'border-color': '#60c0a0',
          'border-width': 2,
          'shape': 'roundrectangle',
          'width': 'label',
          'height': 36,
          'padding': '12px',
          'font-size': '12px',
          'font-family': 'Segoe UI, system-ui, sans-serif',
          'text-wrap': 'none',
        },
      },
      {
        selector: 'node[type = "directQuery"]',
        style: { 'border-color': '#d0a040', 'background-color': '#3a3a28' },
      },
      {
        selector: 'node[type = "calculated"]',
        style: { 'border-color': '#a080d0', 'background-color': '#2e2840' },
      },
      {
        selector: 'node[type = "dual"]',
        style: { 'border-color': '#6090d0', 'background-color': '#283040' },
      },
      {
        selector: 'node[?isHidden]',
        style: { 'opacity': 0.5 },
      },
      {
        selector: 'node:selected',
        style: { 'border-color': '#80e0c0', 'border-width': 3, 'background-color': '#345a4a' },
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#4a6a5a',
          'target-arrow-color': '#4a6a5a',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'label': 'data(cardinality)',
          'font-size': '10px',
          'color': '#808098',
          'text-background-color': '#1e1e2e',
          'text-background-opacity': 0.8,
          'text-background-padding': '2px',
          'font-family': 'Consolas, monospace',
        },
      },
      {
        selector: 'edge[direction = "both"]',
        style: {
          'source-arrow-shape': 'triangle',
          'source-arrow-color': '#d0a040',
          'target-arrow-color': '#d0a040',
          'line-color': '#d0a040',
        },
      },
      {
        selector: 'edge[!isActive]',
        style: {
          'line-style': 'dashed',
          'line-color': '#555568',
          'target-arrow-color': '#555568',
          'opacity': 0.6,
        },
      },
      {
        selector: 'edge:selected',
        style: { 'line-color': '#80e0c0', 'target-arrow-color': '#80e0c0', 'width': 3 },
      },
    ],
    layout: {
      name: 'cose',
      nodeRepulsion: () => 8000,
      idealEdgeLength: () => 120,
      gravity: 0.4,
      numIter: 500,
      animate: false,
    },
    minZoom: 0.2,
    maxZoom: 3,
    wheelSensitivity: 0.3,
  });

  cy.on('tap', 'node', function(evt) {
    const nodeId = evt.target.id();
    const table = model.tables.find(t => t.name === nodeId);
    if (table) showDiagramSidePanel(table);
  });

  cy.on('tap', 'edge', function(evt) {
    const data = evt.target.data();
    showDiagramEdgePanel(data);
  });

  cy.on('tap', function(evt) {
    if (evt.target === cy) {
      $('diagramSidePanel').classList.remove('open');
      requestAnimationFrame(() => cy.resize());
    }
  });

  appState.cy = cy;
}

function showDiagramSidePanel(table) {
  const panel = $('diagramSidePanel');
  let html = `<h3>${escHtml(table.name)}</h3>`;
  html += `<div class="badge badge-type" style="margin-bottom:8px">${table.type}</div>`;

  if (table.columns.length > 0) {
    html += '<div style="margin-top:8px"><strong style="color:var(--text2);font-size:11px">COLUMNS</strong>';
    for (const c of table.columns) {
      const badges = [];
      if (c.isHidden) badges.push(' <span class="badge badge-hidden">H</span>');
      if (c.type === 'calculated') badges.push(' <span class="badge badge-calc">C</span>');
      html += `<div style="padding:2px 0;font-size:12px">${escHtml(c.name)} <span style="color:var(--text2)">${c.dataType}</span>${badges.join('')}</div>`;
    }
    html += '</div>';
  }

  if (table.measures.length > 0) {
    html += `<div style="margin-top:12px"><strong style="color:var(--text2);font-size:11px">MEASURES</strong>`;
    for (const m of table.measures) {
      html += `<div style="padding:2px 0;font-size:12px">${escHtml(m.name)}</div>`;
    }
    html += '</div>';
  }

  panel.innerHTML = html;
  panel.classList.add('open');
  // Resize Cytoscape so it reflows around the newly visible panel
  if (appState.cy) requestAnimationFrame(() => appState.cy.resize());
}

function showDiagramEdgePanel(data) {
  const panel = $('diagramSidePanel');
  const fromT = data.fromTable || data.target;
  const toT = data.toTable || data.source;
  let html = `<h3>${escHtml(fromT)} → ${escHtml(toT)}</h3>`;
  html += `<dl class="detail-meta" style="margin-top:8px">`;
  html += `<dt>From (many)</dt><dd>${escHtml(fromT)}[${escHtml(data.fromColumn)}]</dd>`;
  html += `<dt>To (one)</dt><dd>${escHtml(toT)}[${escHtml(data.toColumn)}]</dd>`;
  html += `<dt>Cardinality</dt><dd>${data.cardinality}</dd>`;
  html += `<dt>Direction</dt><dd>${data.direction === 'both' ? 'Both' : 'Single'}</dd>`;
  html += `<dt>Active</dt><dd>${data.isActive ? 'Yes' : 'No'}</dd>`;
  html += `</dl>`;
  panel.innerHTML = html;
  panel.classList.add('open');
  if (appState.cy) requestAnimationFrame(() => appState.cy.resize());
}

// ============================================================
// EVENT HANDLERS
// ============================================================

function initEvents() {
  const dz = $('dropZone');
  const fi = $('fileInput');

  // Drag and drop
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag-over'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('drag-over'));
  dz.addEventListener('drop', async e => {
    e.preventDefault();
    dz.classList.remove('drag-over');

    // Check for folder drop
    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      const entries = [];
      for (let i = 0; i < items.length; i++) {
        const entry = items[i].webkitGetAsEntry ? items[i].webkitGetAsEntry() : null;
        if (entry) entries.push(entry);
      }

      // Check if any entry is a directory
      const dirs = entries.filter(e => e.isDirectory);
      if (dirs.length > 0) {
        await processDirectory(dirs[0]);
        return;
      }
    }

    // Regular file drop
    const files = e.dataTransfer.files;
    if (files.length > 0) await processFile(files[0]);
  });

  // Browse button
  fi.addEventListener('change', async () => {
    if (fi.files.length > 0) await processFile(fi.files[0]);
    fi.value = '';
  });

  // Click on drop zone (not the button)
  dz.addEventListener('click', (e) => {
    if (e.target === dz || e.target.tagName === 'H2' || e.target.tagName === 'P' || e.target.classList.contains('file-types')) {
      fi.click();
    }
  });

  // Tab switching
  $('tabBar').addEventListener('click', e => {
    const btn = e.target.closest('.tab-btn');
    if (!btn) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    $('tab-' + tab).classList.add('active');

    if (tab === 'diagram' && appState.model) {
      // Delay render/resize until after browser has laid out the container
      requestAnimationFrame(() => {
        if (!appState.cy) {
          renderDiagram(appState.model);
        } else {
          appState.cy.resize();
          appState.cy.fit(null, 40);
        }
      });
    }
  });

  // Tree interactions
  $('treeScroll').addEventListener('click', e => {
    // Checkbox
    const cb = e.target.closest('input[type="checkbox"][data-check]');
    if (cb) {
      const key = cb.dataset.check;
      if (cb.checked) appState.checkedItems.add(key);
      else appState.checkedItems.delete(key);
      updateSelectedTokens();
      e.stopPropagation();
      return;
    }

    // Tree item click (select for detail)
    const item = e.target.closest('.tree-item');
    if (item) {
      document.querySelectorAll('.tree-item.selected').forEach(i => i.classList.remove('selected'));
      item.classList.add('selected');
      const key = item.dataset.key;
      appState.selectedItem = key;
      renderDetail(key);
    }
  });

  // Select all
  $('selectAll').addEventListener('change', e => {
    const checked = e.target.checked;
    appState.checkedItems.clear();
    if (checked) {
      // Add all items
      const model = appState.model;
      if (!model) return;
      for (const t of model.tables) {
        appState.checkedItems.add('table:' + t.name);
        for (const m of t.measures) {
          appState.checkedItems.add('measure:' + t.name + ':' + m.name);
        }
      }
      for (const r of model.relationships) {
        appState.checkedItems.add('rel:' + r.fromTable + ':' + r.fromColumn + ':' + r.toTable + ':' + r.toColumn);
      }
      for (const role of model.roles) {
        appState.checkedItems.add('role:' + role.name);
      }
    }
    // Re-render tree to update checkboxes
    renderTree(appState.model, $('treeSearch').value);
    updateSelectedTokens();
  });

  // Show hidden toggle
  $('showHidden').addEventListener('change', () => {
    renderTree(appState.model, $('treeSearch').value);
  });

  // Search
  $('treeSearch').addEventListener('input', e => {
    renderTree(appState.model, e.target.value);
  });

  // Copy All
  $('copyAllBtn').addEventListener('click', async () => {
    if (!appState.model) return;
    const includeStats = $('includeStatsHeader').checked && appState.pbixDataModel;
    let statsMap = null;
    if (includeStats) {
      const btn = $('copyAllBtn');
      btn.textContent = 'Computing stats...';
      btn.disabled = true;
      try {
        statsMap = await computeAllStats(appState.pbixDataModel, (i, total, name) => {
          btn.textContent = `Stats ${i + 1}/${total}...`;
        });
      } finally {
        btn.textContent = 'Copy All';
        btn.disabled = false;
      }
    }
    const prompt = $('promptSelectHeader').value;
    let text = modelToMarkdown(appState.model, null, statsMap);
    if (prompt && PROMPTS[prompt]) text = PROMPTS[prompt] + text;
    await copyText(text);
    toast(`Copied ~${formatNum(estimateTokens(text))} tokens`);
  });

  // Copy Selected
  $('copySelectedBtn').addEventListener('click', async () => {
    if (!appState.model || appState.checkedItems.size === 0) {
      toast('No items selected');
      return;
    }
    const includeStats = $('includeStats').checked && appState.pbixDataModel;
    let statsMap = null;
    if (includeStats) {
      const btn = $('copySelectedBtn');
      btn.textContent = 'Computing stats...';
      btn.disabled = true;
      try {
        statsMap = await computeAllStats(appState.pbixDataModel, (i, total, name) => {
          btn.textContent = `Stats ${i + 1}/${total}...`;
        });
      } finally {
        btn.textContent = 'Copy Selected';
        btn.disabled = false;
      }
    }
    const prompt = $('promptSelect').value;
    let text = modelToMarkdown(appState.model, appState.checkedItems, statsMap);
    if (prompt && PROMPTS[prompt]) text = PROMPTS[prompt] + text;
    await copyText(text);
    toast(`Copied ~${formatNum(estimateTokens(text))} tokens`);
  });

  // Sync stats checkboxes and update token badges
  $('includeStatsHeader').addEventListener('change', () => {
    $('includeStats').checked = $('includeStatsHeader').checked;
    updateTokenBadges();
  });
  $('includeStats').addEventListener('change', () => {
    $('includeStatsHeader').checked = $('includeStats').checked;
    updateTokenBadges();
  });

  // New file
  $('newFileBtn').addEventListener('click', () => {
    hide('appWrap');
    hide('errorBanner');
    show('dropZoneWrap');
    if (appState.cy) { appState.cy.destroy(); appState.cy = null; }
    appState.model = null;
    appState.checkedItems.clear();
    appState.selectedItem = null;
    appState.pbixDataModel = null;
    appState.statsCache = null;
    $('includeStatsHeader').checked = false;
    $('includeStats').checked = false;
    if (typeof resetDataTab === 'function') resetDataTab();
  });

  // Diagram controls
  $('dgZoomIn').addEventListener('click', () => { if (appState.cy) appState.cy.zoom(appState.cy.zoom() * 1.3); });
  $('dgZoomOut').addEventListener('click', () => { if (appState.cy) appState.cy.zoom(appState.cy.zoom() * 0.7); });
  $('dgFit').addEventListener('click', () => { if (appState.cy) appState.cy.fit(null, 40); });
  $('dgRelayout').addEventListener('click', () => {
    if (appState.cy) {
      appState.cy.layout({
        name: 'cose',
        nodeRepulsion: () => 8000,
        idealEdgeLength: () => 120,
        gravity: 0.4,
        numIter: 500,
        animate: true,
        animationDuration: 500,
      }).run();
    }
  });

  // Diagram search
  $('diagramSearch').addEventListener('input', e => {
    if (!appState.cy) return;
    const q = e.target.value.toLowerCase();
    appState.cy.nodes().forEach(n => {
      if (!q || n.data('label').toLowerCase().includes(q)) {
        n.style('opacity', 1);
      } else {
        n.style('opacity', 0.15);
      }
    });
  });

  // Diagram show hidden toggle
  $('dgShowHidden').addEventListener('change', () => {
    if (appState.model) {
      if (appState.cy) { appState.cy.destroy(); appState.cy = null; }
      renderDiagram(appState.model);
    }
  });
}

function updateSelectedTokens() {
  const count = appState.checkedItems.size;
  if (count === 0) {
    $('selectedTokenBadge').textContent = '~0 tokens';
    return;
  }
  const md = modelToMarkdown(appState.model, appState.checkedItems);
  const base = estimateTokens(md);
  const statsChecked = $('includeStats').checked && appState.statsCache;
  if (statsChecked) {
    const withStats = modelToMarkdown(appState.model, appState.checkedItems, appState.statsCache);
    const total = estimateTokens(withStats);
    const diff = total - base;
    $('selectedTokenBadge').textContent = `~${formatNum(total)} tokens (+${formatNum(diff)} stats)`;
  } else {
    $('selectedTokenBadge').textContent = `~${formatNum(base)} tokens`;
  }
}

function updateTokenBadges() {
  if (!appState.model) return;
  // Header badge
  const fullMd = modelToMarkdown(appState.model, null);
  const base = estimateTokens(fullMd);
  const statsChecked = $('includeStatsHeader').checked && appState.statsCache;
  if (statsChecked) {
    const withStats = modelToMarkdown(appState.model, null, appState.statsCache);
    const total = estimateTokens(withStats);
    const diff = total - base;
    $('tokenBadge').textContent = `~${formatNum(total)} tokens (+${formatNum(diff)} stats)`;
  } else {
    $('tokenBadge').textContent = `~${formatNum(base)} tokens`;
  }
  // Selected badge
  updateSelectedTokens();
}

// ============================================================
// FILE PROCESSING
// ============================================================

async function processFile(file) {
  hide('dropZoneWrap');
  show('loadingWrap');
  $('loadingText').textContent = file.size > 50 * 1024 * 1024
    ? `Parsing ${(file.size / 1024 / 1024).toFixed(0)}MB model...`
    : 'Parsing model...';

  try {
    const model = await parseFile(file);
    hide('loadingWrap');
    hide('errorBanner');
    show('appWrap');
    renderApp(model);
  } catch (err) {
    hide('loadingWrap');
    showError([err.message || 'Unknown error']);
    show('dropZoneWrap');
  }
}

async function processDirectory(dirEntry) {
  hide('dropZoneWrap');
  show('loadingWrap');
  $('loadingText').textContent = 'Reading folder...';

  try {
    const allEntries = await flattenEntries([dirEntry]);
    const model = await parseFolder(allEntries);
    hide('loadingWrap');
    hide('errorBanner');
    show('appWrap');
    renderApp(model);
  } catch (err) {
    hide('loadingWrap');
    showError([err.message || 'Unknown error']);
    show('dropZoneWrap');
  }
}

function showError(errors) {
  const banner = $('errorBanner');
  const list = $('errorList');
  list.innerHTML = errors.map(e => `<li>${escHtml(e)}</li>`).join('');
  banner.style.display = 'block';
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  // Check for JSZip
  if (typeof JSZip === 'undefined') {
    // Try to load dynamically - but for the bundled version, it should be inline above
    console.warn('JSZip not loaded. ZIP file support disabled.');
  }
  initEvents();
});
