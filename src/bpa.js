
// ============================================================
// Best Practice Analyzer (BPA) — Rule Engine + 55 Rules
// ============================================================
//
// Each rule is a plain object:
//   { id, name, category, severity, description, check(model) }
//
// check(model) returns an array of violations:
//   [{ table?, column?, measure?, relationship?, object?, message }]
//
// The engine runs every rule, collects results, and exposes helpers
// for the UI (filter, sort, group, export).
// ============================================================

const BPA_RULES = [];

// Helper: register a rule
function bpaRule(r) { BPA_RULES.push(r); }

// ── Severity constants ──────────────────────────────────────
const SEV = { error: 'error', warning: 'warning', info: 'info' };

// ── Category constants ──────────────────────────────────────
const CAT = {
  perf:   'Performance',
  dax:    'DAX',
  name:   'Naming',
  meta:   'Metadata',
  model:  'Modeling',
  fmt:    'Formatting',
  sec:    'Security',
};

// ============================================================
// RULES — Performance
// ============================================================

bpaRule({
  id: 'PERF_001', name: 'Avoid bi-directional relationships',
  category: CAT.perf, severity: SEV.warning,
  description: 'Bi-directional cross-filtering can cause ambiguous filter paths and degrade performance.',
  check: m => m.relationships
    .filter(r => r.crossFilterDirection === 'both')
    .map(r => ({ relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: 'Relationship uses bi-directional cross-filtering.' })),
});

bpaRule({
  id: 'PERF_002', name: 'Avoid many-to-many relationships',
  category: CAT.perf, severity: SEV.warning,
  description: 'Many-to-many relationships are expensive and often indicate modeling issues.',
  check: m => m.relationships
    .filter(r => r.cardinality === 'manyToMany')
    .map(r => ({ relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: 'Many-to-many cardinality detected.' })),
});

bpaRule({
  id: 'PERF_003', name: 'Prefer measures over calculated columns',
  category: CAT.perf, severity: SEV.info,
  description: 'Calculated columns consume memory and are computed at refresh time. Measures are computed at query time and are more flexible.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.type === 'calculated')
      .map(c => ({ table: t.name, column: c.name, message: `Calculated column found. Consider converting to a measure if possible.` }))
  ),
});

bpaRule({
  id: 'PERF_004', name: 'Tables with high column count',
  category: CAT.perf, severity: SEV.warning,
  description: 'Tables with more than 30 columns may indicate the model needs normalization.',
  check: m => m.tables
    .filter(t => t.columns.length > 30)
    .map(t => ({ table: t.name, message: `Table has ${t.columns.length} columns. Consider splitting or removing unused columns.` })),
});

bpaRule({
  id: 'PERF_005', name: 'Remove unused columns',
  category: CAT.perf, severity: SEV.info,
  description: 'Hidden columns that are not used in any relationship, hierarchy, or sort-by may be unnecessary and waste memory.',
  check: m => {
    // Columns referenced by relationships
    const relCols = new Set();
    for (const r of m.relationships) {
      relCols.add(r.fromTable + '|' + r.fromColumn);
      relCols.add(r.toTable + '|' + r.toColumn);
    }
    // Columns referenced by sortByColumn
    const sortCols = new Set();
    for (const t of m.tables) {
      for (const c of t.columns) {
        if (c.sortByColumn) sortCols.add(t.name + '|' + c.sortByColumn);
      }
    }
    // Columns referenced by hierarchies
    const hierCols = new Set();
    for (const t of m.tables) {
      for (const h of t.hierarchies) {
        for (const l of (h.levels || [])) {
          hierCols.add(t.name + '|' + l.column);
        }
      }
    }
    const used = new Set([...relCols, ...sortCols, ...hierCols]);
    return m.tables.flatMap(t =>
      t.columns.filter(c => c.isHidden && c.type !== 'rowNumber' && !used.has(t.name + '|' + c.name))
        .map(c => ({ table: t.name, column: c.name, message: 'Hidden column not used in any relationship, hierarchy, or sort-by.' }))
    );
  },
});

bpaRule({
  id: 'PERF_006', name: 'Avoid floating-point data types',
  category: CAT.perf, severity: SEV.info,
  description: 'Double (floating-point) columns compress poorly. Use Decimal (fixed) or Int64 where possible.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.dataType === 'double')
      .map(c => ({ table: t.name, column: c.name, message: 'Column uses Double data type. Consider Decimal or Int64 for better compression.' }))
  ),
});

bpaRule({
  id: 'PERF_007', name: 'Reduce inactive relationships',
  category: CAT.perf, severity: SEV.info,
  description: 'Inactive relationships add complexity. Use USERELATIONSHIP in DAX only when truly needed.',
  check: m => m.relationships
    .filter(r => !r.isActive)
    .map(r => ({ relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: 'Inactive relationship. Verify it is used with USERELATIONSHIP.' })),
});

bpaRule({
  id: 'PERF_008', name: 'Avoid auto date/time tables',
  category: CAT.perf, severity: SEV.warning,
  description: 'Auto date/time generates hidden date tables for every date column, bloating the model.',
  check: m => m.tables
    .filter(t => /^LocalDateTable_|^DateTableTemplate_/i.test(t.name))
    .map(t => ({ table: t.name, message: 'Auto date/time table detected. Disable auto date/time in Power BI options and use an explicit date table.' })),
});

// ============================================================
// RULES — DAX
// ============================================================

bpaRule({
  id: 'DAX_001', name: 'Avoid IFERROR / ISERROR',
  category: CAT.dax, severity: SEV.warning,
  description: 'IFERROR and ISERROR force the engine to evaluate the expression twice. Use DIVIDE or conditional logic instead.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && /\b(IFERROR|ISERROR)\s*\(/i.test(me.expression))
      .map(me => ({ table: t.name, measure: me.name, message: `Uses IFERROR/ISERROR. Replace with DIVIDE() or IF(ISERROR()) alternatives.` }))
  ),
});

bpaRule({
  id: 'DAX_002', name: 'Use DIVIDE instead of /',
  category: CAT.dax, severity: SEV.info,
  description: 'DIVIDE() handles division by zero gracefully. The / operator may cause errors.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      // Simple heuristic: look for / not inside comments or strings that looks like division
      const expr = me.expression.replace(/\/\/.*/g, '').replace(/"[^"]*"/g, '');
      return /[)\]a-zA-Z_]\s*\/\s*[(\[a-zA-Z_]/i.test(expr);
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'Uses / operator for division. Consider DIVIDE() for safe division by zero handling.' }))
  ),
});

bpaRule({
  id: 'DAX_003', name: 'Avoid CALCULATE with no filter',
  category: CAT.dax, severity: SEV.info,
  description: 'CALCULATE without filter arguments is redundant and may confuse readers.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      // Match CALCULATE( <expr> ) with no comma (no filters)
      const stripped = me.expression.replace(/\/\/.*/g, '').replace(/"[^"]*"/g, '');
      return /\bCALCULATE\s*\([^,)]+\)\s*$/im.test(stripped);
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'CALCULATE used without filter arguments. It may be redundant.' }))
  ),
});

bpaRule({
  id: 'DAX_004', name: 'Avoid using VALUES when SELECTEDVALUE is appropriate',
  category: CAT.dax, severity: SEV.info,
  description: 'SELECTEDVALUE is cleaner and safer when you expect a single value from a filter context.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && /\bVALUES\s*\(/i.test(me.expression) && !/\bSELECTEDVALUE\s*\(/i.test(me.expression))
      .map(me => ({ table: t.name, measure: me.name, message: 'Uses VALUES(). If expecting a single value, consider SELECTEDVALUE().' }))
  ),
});

bpaRule({
  id: 'DAX_005', name: 'Avoid FILTER on entire table',
  category: CAT.dax, severity: SEV.warning,
  description: 'FILTER(Table, ...) iterates the entire table. Use FILTER with KEEPFILTERS or column references for better performance.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      // Heuristic: FILTER( followed by a table name (no bracket = entire table)
      return /\bFILTER\s*\(\s*[A-Za-z_'][A-Za-z0-9_ ']*\s*,/i.test(me.expression) &&
        !/\bFILTER\s*\(\s*ALL\s*\(/i.test(me.expression) &&
        !/\bFILTER\s*\(\s*VALUES\s*\(/i.test(me.expression) &&
        !/\bFILTER\s*\(\s*KEEPFILTERS\s*\(/i.test(me.expression);
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'FILTER used on an entire table. Use column filters (ALL/VALUES) for better performance.' }))
  ),
});

bpaRule({
  id: 'DAX_006', name: 'Avoid SUMX/AVERAGEX on large tables without variables',
  category: CAT.dax, severity: SEV.info,
  description: 'Complex iterator expressions (SUMX, AVERAGEX, etc.) should use VAR to avoid repeated evaluation.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      return /\b(SUMX|AVERAGEX|MAXX|MINX|COUNTX)\s*\(/i.test(me.expression) && !/\bVAR\b/i.test(me.expression);
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'Uses iterator (SUMX/AVERAGEX/etc.) without VAR. Consider storing sub-expressions in variables.' }))
  ),
});

bpaRule({
  id: 'DAX_007', name: 'Avoid nested CALCULATE',
  category: CAT.dax, severity: SEV.warning,
  description: 'Nested CALCULATE can cause unexpected context transitions. Simplify or combine filters.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      const count = (me.expression.match(/\bCALCULATE\s*\(/gi) || []).length;
      return count > 1;
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'Multiple CALCULATE calls detected. Review for unnecessary nesting.' }))
  ),
});

bpaRule({
  id: 'DAX_008', name: 'Measures should not reference other models directly',
  category: CAT.dax, severity: SEV.warning,
  description: 'Expressions referencing hardcoded table names from other databases or external connections may break in deployment.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && /\b(EXTERNALMEASURE|DETAILROWS)\b/i.test(me.expression))
      .map(me => ({ table: t.name, measure: me.name, message: 'References external measure or detail rows expression.' }))
  ),
});

bpaRule({
  id: 'DAX_009', name: 'Avoid ALLEXCEPT in most scenarios',
  category: CAT.dax, severity: SEV.info,
  description: 'ALLEXCEPT keeps filters on specified columns. It is often misunderstood and can be replaced by clearer patterns.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && /\bALLEXCEPT\s*\(/i.test(me.expression))
      .map(me => ({ table: t.name, measure: me.name, message: 'Uses ALLEXCEPT. Consider if ALL + VALUES/KEEPFILTERS is clearer.' }))
  ),
});

bpaRule({
  id: 'DAX_010', name: 'Avoid long measure expressions',
  category: CAT.dax, severity: SEV.info,
  description: 'Very long DAX expressions (>500 chars) may benefit from refactoring into helper measures.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && me.expression.length > 500)
      .map(me => ({ table: t.name, measure: me.name, message: `Measure expression is ${me.expression.length} characters. Consider breaking into helper measures.` }))
  ),
});

// ============================================================
// RULES — Naming
// ============================================================

bpaRule({
  id: 'NAME_001', name: 'Measure names should not contain special characters',
  category: CAT.name, severity: SEV.warning,
  description: 'Measure names with special characters (except spaces) can cause issues in formulas and reports.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => /[^a-zA-Z0-9 _()%#\-/.]/.test(me.name))
      .map(me => ({ table: t.name, measure: me.name, message: `Measure name contains special characters.` }))
  ),
});

bpaRule({
  id: 'NAME_002', name: 'Column names should not contain special characters',
  category: CAT.name, severity: SEV.warning,
  description: 'Column names with special characters can cause DAX formula issues.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.type !== 'rowNumber' && /[^a-zA-Z0-9 _()%#\-/.]/.test(c.name))
      .map(c => ({ table: t.name, column: c.name, message: `Column name contains special characters.` }))
  ),
});

bpaRule({
  id: 'NAME_003', name: 'Table names should not contain special characters',
  category: CAT.name, severity: SEV.warning,
  description: 'Table names with special characters require quoting in DAX and are error-prone.',
  check: m => m.tables
    .filter(t => /[^a-zA-Z0-9 _\-]/.test(t.name))
    .map(t => ({ table: t.name, message: 'Table name contains special characters.' })),
});

bpaRule({
  id: 'NAME_004', name: 'Avoid spaces in column names (prefer underscores)',
  category: CAT.name, severity: SEV.info,
  description: 'Columns with spaces require square brackets in DAX. Underscores or PascalCase improve readability.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.type !== 'rowNumber' && / /.test(c.name))
      .map(c => ({ table: t.name, column: c.name, message: 'Column name contains spaces.' }))
  ),
});

bpaRule({
  id: 'NAME_005', name: 'Measure names should not start with a number',
  category: CAT.name, severity: SEV.warning,
  description: 'Measure names starting with a number can cause confusion and are unconventional.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => /^\d/.test(me.name))
      .map(me => ({ table: t.name, measure: me.name, message: 'Measure name starts with a number.' }))
  ),
});

bpaRule({
  id: 'NAME_006', name: 'Avoid reserved DAX keywords as object names',
  category: CAT.name, severity: SEV.error,
  description: 'Using DAX reserved words (e.g., Date, Year, Month, Value) as column names causes confusion.',
  check: m => {
    const reserved = new Set(['date','year','month','day','hour','minute','second','value','currency','format','path','type','name','table','column','measure','var','return','true','false','blank','error']);
    return m.tables.flatMap(t =>
      t.columns.filter(c => c.type !== 'rowNumber' && reserved.has(c.name.toLowerCase()))
        .map(c => ({ table: t.name, column: c.name, message: `Column name '${c.name}' is a reserved DAX keyword.` }))
    );
  },
});

bpaRule({
  id: 'NAME_007', name: 'Table names should be plural or descriptive',
  category: CAT.name, severity: SEV.info,
  description: 'Tables typically hold multiple rows, so plural names (e.g., "Sales", "Products") are conventional.',
  check: m => m.tables
    .filter(t => !t.isHidden && t.calculationItems.length === 0 && /^[A-Z][a-z]+$/.test(t.name) && !t.name.endsWith('s') && !t.name.endsWith('data') && t.name.length < 20)
    .map(t => ({ table: t.name, message: 'Table name appears singular. Consider using plural names for fact/dimension tables.' })),
});

bpaRule({
  id: 'NAME_008', name: 'Consistent naming: columns across tables',
  category: CAT.name, severity: SEV.info,
  description: 'Related columns (used in relationships) with different names hinder readability.',
  check: m => m.relationships
    .filter(r => r.fromColumn !== r.toColumn)
    .map(r => ({ relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: `Relationship columns have different names: "${r.fromColumn}" vs "${r.toColumn}".` })),
});

// ============================================================
// RULES — Metadata
// ============================================================

bpaRule({
  id: 'META_001', name: 'Tables should have descriptions',
  category: CAT.meta, severity: SEV.warning,
  description: 'Descriptions help report builders and AI tools understand table purpose.',
  check: m => m.tables
    .filter(t => !t.isHidden && !t.description)
    .map(t => ({ table: t.name, message: 'Visible table has no description.' })),
});

bpaRule({
  id: 'META_002', name: 'Measures should have descriptions',
  category: CAT.meta, severity: SEV.warning,
  description: 'Measure descriptions improve discoverability and LLM comprehension.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => !me.isHidden && !me.description)
      .map(me => ({ table: t.name, measure: me.name, message: 'Visible measure has no description.' }))
  ),
});

bpaRule({
  id: 'META_003', name: 'Hidden tables with no visible dependents',
  category: CAT.meta, severity: SEV.info,
  description: 'Hidden tables that are not referenced by any visible measure or column may be unnecessary.',
  check: m => m.tables
    .filter(t => t.isHidden && t.measures.every(me => me.isHidden))
    .map(t => ({ table: t.name, message: 'Hidden table with no visible measures. Verify it is still needed.' })),
});

bpaRule({
  id: 'META_004', name: 'Columns without proper data types',
  category: CAT.meta, severity: SEV.info,
  description: 'Columns with generic or unset data types may not display or aggregate correctly.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.type !== 'rowNumber' && (!c.dataType || c.dataType === 'unknown'))
      .map(c => ({ table: t.name, column: c.name, message: 'Column has no explicit data type.' }))
  ),
});

bpaRule({
  id: 'META_005', name: 'Visible columns on hidden tables',
  category: CAT.meta, severity: SEV.warning,
  description: 'If a table is hidden, its columns should also be hidden for a clean field list.',
  check: m => m.tables.filter(t => t.isHidden).flatMap(t =>
    t.columns.filter(c => !c.isHidden && c.type !== 'rowNumber')
      .map(c => ({ table: t.name, column: c.name, message: 'Visible column on a hidden table.' }))
  ),
});

bpaRule({
  id: 'META_006', name: 'Key columns should be hidden',
  category: CAT.meta, severity: SEV.info,
  description: 'ID/key columns used for relationships are usually not useful for report builders and should be hidden.',
  check: m => {
    const relCols = new Set();
    for (const r of m.relationships) {
      relCols.add(r.fromTable + '|' + r.fromColumn);
      relCols.add(r.toTable + '|' + r.toColumn);
    }
    return m.tables.flatMap(t =>
      t.columns.filter(c => !c.isHidden && c.type !== 'rowNumber' && relCols.has(t.name + '|' + c.name) &&
        (/id$/i.test(c.name) || /key$/i.test(c.name) || /^id /i.test(c.name) || /^fk_/i.test(c.name) || /^sk_/i.test(c.name)))
        .map(c => ({ table: t.name, column: c.name, message: 'Key/ID column used in a relationship is visible. Consider hiding it.' }))
    );
  },
});

bpaRule({
  id: 'META_007', name: 'Measures not in display folders',
  category: CAT.meta, severity: SEV.info,
  description: 'Grouping measures in display folders improves navigation in reports.',
  check: m => {
    const measCount = m.tables.reduce((s, t) => s + t.measures.length, 0);
    if (measCount < 10) return []; // Not worth it for small models
    return m.tables.flatMap(t =>
      t.measures.filter(me => !me.isHidden && !me.displayFolder)
        .map(me => ({ table: t.name, measure: me.name, message: 'Measure not assigned to a display folder.' }))
    );
  },
});

bpaRule({
  id: 'META_008', name: 'Empty tables',
  category: CAT.meta, severity: SEV.warning,
  description: 'Tables with no columns and no measures may be left over from development.',
  check: m => m.tables
    .filter(t => t.columns.length === 0 && t.measures.length === 0 && t.calculationItems.length === 0)
    .map(t => ({ table: t.name, message: 'Table has no columns, measures, or calculation items.' })),
});

// ============================================================
// RULES — Modeling
// ============================================================

bpaRule({
  id: 'MODEL_001', name: 'Tables without relationships',
  category: CAT.model, severity: SEV.warning,
  description: 'Tables not connected via any relationship may be disconnected from the model.',
  check: m => {
    const connected = new Set();
    for (const r of m.relationships) {
      connected.add(r.fromTable);
      connected.add(r.toTable);
    }
    return m.tables
      .filter(t => !connected.has(t.name) && t.columns.length > 0 && t.calculationItems.length === 0 && !/^(LocalDateTable_|DateTableTemplate_)/i.test(t.name))
      .map(t => ({ table: t.name, message: 'Table has no relationships. It may be disconnected from the model.' }));
  },
});

bpaRule({
  id: 'MODEL_002', name: 'Multiple relationships between the same tables',
  category: CAT.model, severity: SEV.info,
  description: 'Having more than one relationship between two tables adds complexity and requires USERELATIONSHIP.',
  check: m => {
    const pairs = {};
    for (const r of m.relationships) {
      const key = [r.fromTable, r.toTable].sort().join('↔');
      (pairs[key] = pairs[key] || []).push(r);
    }
    return Object.entries(pairs)
      .filter(([, rels]) => rels.length > 1)
      .map(([key, rels]) => ({ relationship: key, message: `${rels.length} relationships between these tables. Only one can be active.` }));
  },
});

bpaRule({
  id: 'MODEL_003', name: 'Snowflake dimensions (chain relationships)',
  category: CAT.model, severity: SEV.info,
  description: 'Chained dimension tables (snowflake schema) increase filter propagation hops and can reduce performance.',
  check: m => {
    // Find tables that are "in the middle" — have both incoming and outgoing m:1 relationships
    const fromTables = new Set(m.relationships.filter(r => r.cardinality === 'manyToOne').map(r => r.fromTable));
    const toTables = new Set(m.relationships.filter(r => r.cardinality === 'manyToOne').map(r => r.toTable));
    const middle = [...toTables].filter(t => fromTables.has(t));
    return middle.map(t => ({ table: t, message: 'Table appears in a snowflake pattern (both fact-side and dimension-side of relationships).' }));
  },
});

bpaRule({
  id: 'MODEL_004', name: 'One-to-one relationships',
  category: CAT.model, severity: SEV.info,
  description: 'One-to-one relationships usually mean tables could be merged.',
  check: m => m.relationships
    .filter(r => r.cardinality === 'oneToOne')
    .map(r => ({ relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: 'One-to-one relationship. Consider merging these tables.' })),
});

bpaRule({
  id: 'MODEL_005', name: 'Date table best practices',
  category: CAT.model, severity: SEV.warning,
  description: 'The model should have a dedicated Date dimension table, not rely on auto date/time.',
  check: m => {
    const hasDateTable = m.tables.some(t => {
      const lower = t.name.toLowerCase();
      return (lower === 'date' || lower === 'dates' || lower === 'calendar' || lower === 'dim_date' || lower === 'dimdate' || lower === 'dim date')
        && t.columns.some(c => c.dataType === 'dateTime' || c.dataType === 'date');
    });
    if (hasDateTable) return [];
    const hasDateCols = m.tables.some(t => t.columns.some(c => (c.dataType === 'dateTime' || c.dataType === 'date') && !t.isHidden));
    if (!hasDateCols) return [];
    return [{ message: 'No dedicated Date dimension table found. Create a Date/Calendar table for proper time intelligence.' }];
  },
});

bpaRule({
  id: 'MODEL_006', name: 'Relationship to a hidden table',
  category: CAT.model, severity: SEV.info,
  description: 'Relationships connecting to hidden tables are harder to discover for report builders.',
  check: m => {
    const hiddenTables = new Set(m.tables.filter(t => t.isHidden).map(t => t.name));
    return m.relationships
      .filter(r => hiddenTables.has(r.toTable) || hiddenTables.has(r.fromTable))
      .map(r => {
        const which = hiddenTables.has(r.toTable) ? r.toTable : r.fromTable;
        return { relationship: `${r.fromTable}[${r.fromColumn}] → ${r.toTable}[${r.toColumn}]`, message: `Relationship involves hidden table '${which}'.` };
      });
  },
});

bpaRule({
  id: 'MODEL_007', name: 'Avoid DirectQuery + Import mixed mode when unnecessary',
  category: CAT.model, severity: SEV.warning,
  description: 'Mixing DirectQuery and Import partitions adds complexity and potential inconsistency.',
  check: m => {
    const modes = new Set();
    for (const t of m.tables) {
      for (const p of t.partitions) {
        if (p.mode) modes.add(p.mode.toLowerCase());
      }
    }
    if (modes.has('directquery') && modes.has('import')) {
      return [{ message: 'Model mixes DirectQuery and Import modes. Ensure this is intentional.' }];
    }
    return [];
  },
});

bpaRule({
  id: 'MODEL_008', name: 'Hierarchies without enough levels',
  category: CAT.model, severity: SEV.info,
  description: 'A hierarchy with only one level provides no drill-down value.',
  check: m => m.tables.flatMap(t =>
    t.hierarchies.filter(h => (h.levels || []).length < 2)
      .map(h => ({ table: t.name, object: h.name, message: `Hierarchy '${h.name}' has fewer than 2 levels.` }))
  ),
});

bpaRule({
  id: 'MODEL_009', name: 'Tables with measures only (measure tables)',
  category: CAT.model, severity: SEV.info,
  description: 'Measure tables (no data columns, only measures) should be hidden to keep the field list clean.',
  check: m => m.tables
    .filter(t => t.measures.length > 0 && t.columns.filter(c => c.type !== 'rowNumber').length === 0 && !t.isHidden)
    .map(t => ({ table: t.name, message: 'Table appears to be a measure table (no data columns). Consider hiding it.' })),
});

// ============================================================
// RULES — Formatting
// ============================================================

bpaRule({
  id: 'FMT_001', name: 'Measures without format strings',
  category: CAT.fmt, severity: SEV.warning,
  description: 'Measures without explicit format strings display raw numbers, hurting readability.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => !me.isHidden && !me.formatString)
      .map(me => ({ table: t.name, measure: me.name, message: 'Measure has no format string. Add a format like "#,0", "0.0%", etc.' }))
  ),
});

bpaRule({
  id: 'FMT_002', name: 'Percentage measures without % format',
  category: CAT.fmt, severity: SEV.info,
  description: 'Measures with "percent" or "%" in the name should have a percentage format string.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => /(percent|pct|%|ratio)/i.test(me.name) && me.formatString && !me.formatString.includes('%'))
      .map(me => ({ table: t.name, measure: me.name, message: 'Measure name suggests a percentage but format string lacks %.' }))
  ),
});

bpaRule({
  id: 'FMT_003', name: 'Date columns without date format',
  category: CAT.fmt, severity: SEV.info,
  description: 'Date/DateTime columns should have an explicit date format for consistent display.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => (c.dataType === 'dateTime' || c.dataType === 'date') && !c.formatString && !c.isHidden && c.type !== 'rowNumber')
      .map(c => ({ table: t.name, column: c.name, message: 'Date column has no format string.' }))
  ),
});

bpaRule({
  id: 'FMT_004', name: 'Currency measures should use currency format',
  category: CAT.fmt, severity: SEV.info,
  description: 'Measures with "amount", "revenue", "cost", "price" in the name should have a currency format.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => /(amount|revenue|cost|price|sales|spend|budget|profit)/i.test(me.name) && me.formatString && !/[\$€£¥]/.test(me.formatString) && !me.formatString.includes('"'))
      .map(me => ({ table: t.name, measure: me.name, message: 'Measure name suggests currency but format string has no currency symbol.' }))
  ),
});

// ============================================================
// RULES — Security
// ============================================================

bpaRule({
  id: 'SEC_001', name: 'No RLS roles defined',
  category: CAT.sec, severity: SEV.info,
  description: 'The model has no Row-Level Security roles. If data access control is needed, define RLS.',
  check: m => {
    if (m.roles.length > 0) return [];
    if (m.tables.length < 3) return []; // Trivial models don't need RLS
    return [{ message: 'No Row-Level Security (RLS) roles defined. Consider adding RLS if data access control is required.' }];
  },
});

bpaRule({
  id: 'SEC_002', name: 'RLS roles with no filter expressions',
  category: CAT.sec, severity: SEV.error,
  description: 'An RLS role without any table filter expressions grants full access, which may be unintended.',
  check: m => m.roles
    .filter(r => r.tablePermissions.length === 0 || r.tablePermissions.every(tp => !tp.filterExpression))
    .map(r => ({ object: r.name, message: `RLS role '${r.name}' has no filter expressions. It grants full data access.` })),
});

bpaRule({
  id: 'SEC_003', name: 'RLS using USERNAME() instead of USERPRINCIPALNAME()',
  category: CAT.sec, severity: SEV.warning,
  description: 'USERNAME() may return domain\\username in some environments. USERPRINCIPALNAME() is more reliable.',
  check: m => m.roles.flatMap(r =>
    r.tablePermissions.filter(tp => tp.filterExpression && /\bUSERNAME\s*\(\s*\)/i.test(tp.filterExpression))
      .map(tp => ({ object: r.name, message: `RLS role '${r.name}' uses USERNAME(). Consider USERPRINCIPALNAME() instead.` }))
  ),
});

// ============================================================
// Additional Performance Rules
// ============================================================

bpaRule({
  id: 'PERF_009', name: 'Avoid high-cardinality text columns',
  category: CAT.perf, severity: SEV.info,
  description: 'Text columns with unique values on every row (IDs, GUIDs) compress poorly and bloat the model.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.dataType === 'string' && !c.isHidden && c.type !== 'rowNumber' &&
      (/guid|uuid|hash|token/i.test(c.name)))
      .map(c => ({ table: t.name, column: c.name, message: 'Text column name suggests high-cardinality data (GUID/UUID/Hash). Consider hiding or removing if unused.' }))
  ),
});

bpaRule({
  id: 'PERF_010', name: 'SortByColumn not set on month name columns',
  category: CAT.perf, severity: SEV.warning,
  description: 'Month name columns without SortByColumn will sort alphabetically instead of chronologically.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => /^(month\s*name|monthname|month\s*label)$/i.test(c.name) && !c.sortByColumn && c.dataType === 'string')
      .map(c => ({ table: t.name, column: c.name, message: 'Month name column has no SortByColumn. It will sort alphabetically.' }))
  ),
});

// ============================================================
// Additional Naming Rules
// ============================================================

bpaRule({
  id: 'NAME_009', name: 'Avoid prefixes on measures',
  category: CAT.name, severity: SEV.info,
  description: 'Hungarian notation or prefixes like "m_" or "Measure_" on measures add noise. Use display folders instead.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => /^(m_|msr_|measure_)/i.test(me.name))
      .map(me => ({ table: t.name, measure: me.name, message: 'Measure uses a prefix notation. Use display folders to organize measures instead.' }))
  ),
});

bpaRule({
  id: 'NAME_010', name: 'Avoid prefixes on tables',
  category: CAT.name, severity: SEV.info,
  description: 'Prefixes like "tbl_", "dim_", "fact_" are common in databases but not recommended for semantic models where user-friendly names matter.',
  check: m => m.tables
    .filter(t => /^(tbl_|tbl |dim_|fact_)/i.test(t.name) && !t.isHidden)
    .map(t => ({ table: t.name, message: 'Table uses a database-style prefix. Consider a more user-friendly name.' })),
});

// ============================================================
// Additional DAX Rules
// ============================================================

bpaRule({
  id: 'DAX_011', name: 'Avoid SWITCH(TRUE, ...) for simple comparisons',
  category: CAT.dax, severity: SEV.info,
  description: 'SWITCH(TRUE, ...) is useful for multiple conditions but IF is cleaner for simple binary checks.',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => me.expression && /\bSWITCH\s*\(\s*TRUE/i.test(me.expression))
      .map(me => ({ table: t.name, measure: me.name, message: 'Uses SWITCH(TRUE, ...). Verify it could not be simplified to IF().' }))
  ),
});

bpaRule({
  id: 'DAX_012', name: 'Measures referencing columns without table prefix',
  category: CAT.dax, severity: SEV.info,
  description: 'Column references should always include the table name for clarity: TableName[Column].',
  check: m => m.tables.flatMap(t =>
    t.measures.filter(me => {
      if (!me.expression) return false;
      // Heuristic: look for [ColumnName] not preceded by a table reference or quoted name
      return /(?<![A-Za-z0-9_'")\]])\[[A-Za-z]/i.test(me.expression);
    })
      .map(me => ({ table: t.name, measure: me.name, message: 'Contains unqualified column reference [Column] without table prefix.' }))
  ),
});

// ============================================================
// Additional Metadata Rules
// ============================================================

bpaRule({
  id: 'META_009', name: 'Summarize by set to non-"none" for non-numeric columns',
  category: CAT.meta, severity: SEV.info,
  description: 'Text/date columns with default summarization may unintentionally show counts in reports.',
  check: m => m.tables.flatMap(t =>
    t.columns.filter(c => c.type !== 'rowNumber' && c.summarizeBy && c.summarizeBy !== 'none' &&
      (c.dataType === 'string' || c.dataType === 'dateTime' || c.dataType === 'date' || c.dataType === 'boolean'))
      .map(c => ({ table: t.name, column: c.name, message: `Non-numeric column has summarizeBy='${c.summarizeBy}'. Set to 'None'.` }))
  ),
});

bpaRule({
  id: 'META_010', name: 'Tables with very few columns',
  category: CAT.meta, severity: SEV.info,
  description: 'Tables with only 1-2 columns (excluding row number) may not warrant being separate tables.',
  check: m => m.tables
    .filter(t => {
      const realCols = t.columns.filter(c => c.type !== 'rowNumber');
      return realCols.length > 0 && realCols.length <= 2 && t.measures.length === 0 && t.calculationItems.length === 0 && !t.isHidden;
    })
    .map(t => ({ table: t.name, message: `Table has only ${t.columns.filter(c => c.type !== 'rowNumber').length} column(s). Consider merging with a related table.` })),
});

// ============================================================
// BPA Engine
// ============================================================

function runBpa(model) {
  const results = [];
  for (const rule of BPA_RULES) {
    try {
      const violations = rule.check(model);
      results.push({
        rule,
        violations: violations || [],
        passed: (violations || []).length === 0,
        error: null,
      });
    } catch (e) {
      results.push({ rule, violations: [], passed: true, error: e.message });
    }
  }
  return results;
}

function bpaSummary(results) {
  let total = results.length;
  let passed = results.filter(r => r.passed).length;
  let failed = total - passed;
  let errors = results.filter(r => !r.passed && r.rule.severity === 'error').reduce((s, r) => s + r.violations.length, 0);
  let warnings = results.filter(r => !r.passed && r.rule.severity === 'warning').reduce((s, r) => s + r.violations.length, 0);
  let infos = results.filter(r => !r.passed && r.rule.severity === 'info').reduce((s, r) => s + r.violations.length, 0);
  let totalViolations = errors + warnings + infos;
  let score = total > 0 ? Math.round((passed / total) * 100) : 100;
  return { total, passed, failed, errors, warnings, infos, totalViolations, score };
}

// ============================================================
// BPA UI Rendering
// ============================================================

function renderBpaTab(model) {
  const results = runBpa(model);
  const summary = bpaSummary(results);

  // Store results for export
  appState.bpaResults = results;

  const container = $('bpa-content');
  if (!container) return;

  // --- Summary Bar ---
  let html = '<div class="bpa-summary">';
  html += `<div class="bpa-score bpa-score-${summary.score >= 80 ? 'good' : summary.score >= 50 ? 'ok' : 'bad'}">${summary.score}%</div>`;
  html += '<div class="bpa-summary-stats">';
  html += `<span class="bpa-stat">${summary.passed}/${summary.total} rules passed</span>`;
  if (summary.errors > 0) html += `<span class="bpa-badge bpa-sev-error">${summary.errors} error${summary.errors > 1 ? 's' : ''}</span>`;
  if (summary.warnings > 0) html += `<span class="bpa-badge bpa-sev-warning">${summary.warnings} warning${summary.warnings > 1 ? 's' : ''}</span>`;
  if (summary.infos > 0) html += `<span class="bpa-badge bpa-sev-info">${summary.infos} info</span>`;
  html += '</div>';
  html += '<div class="bpa-actions">';
  html += '<select class="bpa-filter" id="bpaFilter"><option value="all">All rules</option><option value="failed">Failed only</option><option value="error">Errors</option><option value="warning">Warnings</option><option value="info">Info</option>';
  // Category options
  const cats = [...new Set(BPA_RULES.map(r => r.category))].sort();
  for (const c of cats) html += `<option value="cat:${c}">${c}</option>`;
  html += '</select>';
  html += '<button class="btn btn-small" id="bpaCopyBtn" title="Copy BPA report as Markdown">Copy Report</button>';
  html += '<button class="btn btn-primary btn-small" id="bpaFixBtn" title="Copy BPA violations with model context for LLM-assisted fixing">Copy Fix Prompt</button>';
  html += '</div>';
  html += '</div>';

  // --- Rules List ---
  html += '<div class="bpa-rules" id="bpaRules">';
  html += renderBpaRules(results, 'all');
  html += '</div>';

  container.innerHTML = html;

  // --- Event listeners ---
  $('bpaFilter').addEventListener('change', e => {
    $('bpaRules').innerHTML = renderBpaRules(results, e.target.value);
  });

  $('bpaCopyBtn').addEventListener('click', async () => {
    const md = bpaToMarkdown(results, model);
    await copyText(md);
    toast(`Copied BPA report (~${formatNum(estimateTokens(md))} tokens)`);
  });

  $('bpaFixBtn').addEventListener('click', async () => {
    const md = bpaFixPrompt(results, model);
    await copyText(md);
    toast(`Copied fix prompt (~${formatNum(estimateTokens(md))} tokens)`);
  });
}

function renderBpaRules(results, filter) {
  let filtered = results;
  if (filter === 'failed') filtered = results.filter(r => !r.passed);
  else if (filter === 'error') filtered = results.filter(r => r.rule.severity === 'error');
  else if (filter === 'warning') filtered = results.filter(r => r.rule.severity === 'warning');
  else if (filter === 'info') filtered = results.filter(r => r.rule.severity === 'info');
  else if (filter.startsWith('cat:')) {
    const cat = filter.slice(4);
    filtered = results.filter(r => r.rule.category === cat);
  }

  // Sort: failed first, then by severity (error > warning > info)
  const sevOrder = { error: 0, warning: 1, info: 2 };
  filtered = [...filtered].sort((a, b) => {
    if (a.passed !== b.passed) return a.passed ? 1 : -1;
    return (sevOrder[a.rule.severity] || 3) - (sevOrder[b.rule.severity] || 3);
  });

  if (filtered.length === 0) return '<div class="bpa-empty">No rules match this filter.</div>';

  let html = '';
  for (const r of filtered) {
    const sevClass = `bpa-sev-${r.rule.severity}`;
    const statusClass = r.passed ? 'bpa-passed' : 'bpa-failed';
    const statusIcon = r.passed ? '&#10003;' : '&#10007;';
    const count = r.violations.length;

    html += `<details class="bpa-rule ${statusClass}">`;
    html += `<summary class="bpa-rule-header">`;
    html += `<span class="bpa-status-icon ${statusClass}">${statusIcon}</span>`;
    html += `<span class="bpa-badge ${sevClass}">${r.rule.severity}</span>`;
    html += `<span class="bpa-badge bpa-cat">${escHtml(r.rule.category)}</span>`;
    html += `<span class="bpa-rule-name">${escHtml(r.rule.name)}</span>`;
    if (!r.passed) html += `<span class="bpa-count">${count} issue${count > 1 ? 's' : ''}</span>`;
    html += `<span class="bpa-rule-id">${r.rule.id}</span>`;
    html += `</summary>`;

    html += `<div class="bpa-rule-body">`;
    html += `<p class="bpa-rule-desc">${escHtml(r.rule.description)}</p>`;

    if (r.error) {
      html += `<p class="bpa-error">Rule error: ${escHtml(r.error)}</p>`;
    }

    if (r.violations.length > 0) {
      html += '<table class="bpa-violations-table"><thead><tr>';
      // Determine columns
      const hasTable = r.violations.some(v => v.table);
      const hasCol = r.violations.some(v => v.column);
      const hasMeasure = r.violations.some(v => v.measure);
      const hasRel = r.violations.some(v => v.relationship);
      const hasObj = r.violations.some(v => v.object);
      if (hasTable) html += '<th>Table</th>';
      if (hasCol) html += '<th>Column</th>';
      if (hasMeasure) html += '<th>Measure</th>';
      if (hasRel) html += '<th>Relationship</th>';
      if (hasObj) html += '<th>Object</th>';
      html += '<th>Details</th></tr></thead><tbody>';

      const maxShow = 20;
      const shown = r.violations.slice(0, maxShow);
      for (const v of shown) {
        html += '<tr>';
        if (hasTable) html += `<td>${escHtml(v.table || '')}</td>`;
        if (hasCol) html += `<td>${escHtml(v.column || '')}</td>`;
        if (hasMeasure) html += `<td>${escHtml(v.measure || '')}</td>`;
        if (hasRel) html += `<td>${escHtml(v.relationship || '')}</td>`;
        if (hasObj) html += `<td>${escHtml(v.object || '')}</td>`;
        html += `<td>${escHtml(v.message)}</td>`;
        html += '</tr>';
      }
      html += '</tbody></table>';
      if (r.violations.length > maxShow) {
        html += `<p class="bpa-more">...and ${r.violations.length - maxShow} more</p>`;
      }
    }
    html += '</div></details>';
  }
  return html;
}

// ============================================================
// BPA Markdown Export
// ============================================================

function bpaToMarkdown(results, model) {
  const summary = bpaSummary(results);
  const lines = [];
  lines.push(`# Best Practice Analyzer Report — ${model.name || 'Model'}`);
  lines.push('');
  lines.push(`**Score: ${summary.score}%** | ${summary.passed}/${summary.total} rules passed | ${summary.errors} errors | ${summary.warnings} warnings | ${summary.infos} info`);
  lines.push('');

  const failed = results.filter(r => !r.passed);
  if (failed.length === 0) {
    lines.push('All rules passed! No issues found.');
    return lines.join('\n');
  }

  // Group by severity
  for (const sev of ['error', 'warning', 'info']) {
    const sevRules = failed.filter(r => r.rule.severity === sev);
    if (sevRules.length === 0) continue;
    lines.push(`## ${sev.charAt(0).toUpperCase() + sev.slice(1)}s`);
    lines.push('');
    for (const r of sevRules) {
      lines.push(`### ${r.rule.id}: ${r.rule.name}`);
      lines.push(`> ${r.rule.description}`);
      lines.push('');
      for (const v of r.violations) {
        let loc = '';
        if (v.table) loc += v.table;
        if (v.column) loc += `[${v.column}]`;
        if (v.measure) loc += `[${v.measure}]`;
        if (v.relationship) loc = v.relationship;
        if (v.object) loc = v.object;
        lines.push(`- ${loc ? '**' + loc + '**: ' : ''}${v.message}`);
      }
      lines.push('');
    }
  }
  return lines.join('\n');
}

// ============================================================
// BPA Fix Prompt (for LLM / Power BI MCP)
// ============================================================

function bpaFixPrompt(results, model) {
  const bpaMd = bpaToMarkdown(results, model);
  const modelMd = modelToMarkdown(model, null);

  const prompt = `You are a Power BI / XMLA expert. Below is a Best Practice Analyzer report showing violations found in a semantic model, followed by the full model definition.

Your task:
1. Review each violation and determine the best fix.
2. For each fix, provide the specific action needed (rename, hide, add description, rewrite DAX, change property, etc.)
3. Provide the fixes as executable actions where possible (e.g., exact DAX rewrites, property changes).
4. Prioritize fixes by impact: errors first, then warnings, then info.
5. If using Tabular Editor or XMLA, provide the C# script or TMSL command.

--- BPA REPORT ---
${bpaMd}
--- MODEL DEFINITION ---
${modelMd}`;

  return prompt;
}
