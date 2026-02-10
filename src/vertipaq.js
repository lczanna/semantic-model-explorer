// ============================================================
// VertiPaq Decoder — Extract table row data from .pbix DataModel
//
// Pipeline: .pbix ZIP → DataModel blob → XPress9 decompress →
//           ABF parse → SQLite metadata → VertiPaq column decode
//
// Ported from:
//   - power-query-explorer/wasm/xpress9/datamodel-decoder.js (XPress9 + ABF + SQLite)
//   - pbixray/vertipaq_decoder.py + column_data/ (VertiPaq column formats)
// ============================================================

// --- XPress9 WASM base64 (injected by build.py) ---
const XPRESS9_WASM_B64 = '%%XPRESS9_WASM_B64%%';

let _xp9Module = null;

async function _getXpress9() {
  if (_xp9Module) return _xp9Module;
  if (typeof Xpress9Module === 'undefined') throw new Error('XPress9 WASM module not loaded');
  const bin = Uint8Array.from(atob(XPRESS9_WASM_B64), c => c.charCodeAt(0));
  _xp9Module = await Xpress9Module({ wasmBinary: bin.buffer });
  return _xp9Module;
}

// ============================================================
// XPress9 Decompression
// ============================================================

async function decompressXpress9(dataModelBuf) {
  const mod = await _getXpress9();
  const buf = new Uint8Array(dataModelBuf);
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);

  // Read UTF-16LE signature (first 102 bytes)
  let sig = '';
  for (let i = 0; i < 102; i += 2) {
    const ch = buf[i] | (buf[i + 1] << 8);
    if (ch === 0) break;
    sig += String.fromCharCode(ch);
  }

  const isMultiThread = sig.includes('multithreaded');
  let offset = 102;
  const chunks = [];

  if (isMultiThread) {
    const readU64 = (o) => Number(view.getBigUint64(o, true));
    const mainChunks = readU64(offset); offset += 8;
    const prefixChunks = readU64(offset); offset += 8;
    const prefixThreads = readU64(offset); offset += 8;
    const mainThreads = readU64(offset); offset += 8;
    offset += 8; // chunkSize

    const groups = [];
    for (let t = 0; t < prefixThreads; t++) groups.push(prefixChunks);
    for (let t = 0; t < mainThreads; t++) groups.push(mainChunks);

    for (const nBlocks of groups) {
      mod.ccall('xpress9_free', null, [], []);
      if (!mod.ccall('xpress9_init', 'number', [], [])) throw new Error('XPress9 init failed');
      for (let b = 0; b < nBlocks && offset + 8 <= buf.length; b++) {
        offset = _decompressBlock(mod, buf, view, offset, chunks);
      }
    }
  } else {
    if (!mod.ccall('xpress9_init', 'number', [], [])) throw new Error('XPress9 init failed');
    while (offset + 8 <= buf.length) {
      const prev = offset;
      offset = _decompressBlock(mod, buf, view, offset, chunks);
      if (offset === prev) break;
    }
  }

  mod.ccall('xpress9_free', null, [], []);

  const totalLen = chunks.reduce((s, c) => s + c.length, 0);
  const result = new Uint8Array(totalLen);
  let pos = 0;
  for (const chunk of chunks) { result.set(chunk, pos); pos += chunk.length; }
  return result;
}

function _decompressBlock(mod, buf, view, offset, chunks) {
  const uncompSize = view.getUint32(offset, true);
  const compSize = view.getUint32(offset + 4, true);
  offset += 8;
  if (compSize === 0 || uncompSize === 0 || offset + compSize > buf.length) return offset;

  const srcPtr = mod._malloc(compSize);
  const dstPtr = mod._malloc(uncompSize);
  mod.HEAPU8.set(buf.subarray(offset, offset + compSize), srcPtr);

  const result = mod.ccall('xpress9_decompress', 'number',
    ['number', 'number', 'number', 'number'],
    [srcPtr, compSize, dstPtr, uncompSize]);

  if (result > 0) {
    chunks.push(new Uint8Array(mod.HEAPU8.buffer.slice(dstPtr, dstPtr + result)));
  }

  mod._free(srcPtr);
  mod._free(dstPtr);
  return offset + compSize;
}

// ============================================================
// Xpress8 Decompression (for older .pbix with apply_compression)
// Ported from pbixray/xpress8.py
// ============================================================

function decompressXpress8Chunked(buf) {
  // Chunked format: [uncompSize:u32le, compSize:u32le, data...]...
  const view = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const chunks = [];
  let offset = 0;
  while (offset + 8 <= buf.length) {
    const uncompSize = view.getUint32(offset, true);
    const compSize = view.getUint32(offset + 4, true);
    offset += 8;
    if (compSize === 0 || offset + compSize > buf.length) break;
    if (compSize === uncompSize) {
      // Stored uncompressed
      chunks.push(buf.slice(offset, offset + compSize));
    } else {
      chunks.push(_decompressXpress8Block(buf, offset, compSize, uncompSize));
    }
    offset += compSize;
  }
  const totalLen = chunks.reduce((s, c) => s + c.length, 0);
  const result = new Uint8Array(totalLen);
  let pos = 0;
  for (const c of chunks) { result.set(c, pos); pos += c.length; }
  return result;
}

function _decompressXpress8Block(src, srcOffset, compSize, uncompSize) {
  const out = new Uint8Array(uncompSize);
  let si = srcOffset, di = 0;
  const srcEnd = srcOffset + compSize;

  while (si < srcEnd && di < uncompSize) {
    // Read flag byte
    const flags = src[si++];
    for (let bit = 0; bit < 8 && si < srcEnd && di < uncompSize; bit++) {
      if (flags & (1 << bit)) {
        // Match: 2 bytes encode offset + length
        if (si + 1 >= srcEnd) break;
        const b0 = src[si++];
        const b1 = src[si++];
        const matchOffset = ((b1 & 0xF8) << 5) | b0 | 1;
        let matchLen = (b1 & 0x07) + 3;
        if (matchLen === 10) {
          // Extended length
          if (si >= srcEnd) break;
          matchLen = src[si++] + 10;
          if (matchLen === 265) {
            if (si + 1 >= srcEnd) break;
            matchLen = src[si] | (src[si + 1] << 8);
            si += 2;
          }
        }
        let copyFrom = di - matchOffset;
        for (let j = 0; j < matchLen && di < uncompSize; j++) {
          out[di++] = out[copyFrom++];
        }
      } else {
        // Literal byte
        out[di++] = src[si++];
      }
    }
  }
  return out;
}

// ============================================================
// ABF Parser — Parse decompressed DataModel into a file index
// ============================================================

function parseABF(data) {
  // BackupLogHeader: UTF-16LE XML at offset 72
  let headerXml = '';
  for (let i = 72; i < 4096 - 1; i += 2) {
    const ch = data[i] | (data[i + 1] << 8);
    if (ch === 0) break;
    headerXml += String.fromCharCode(ch);
  }

  const getXmlVal = (xml, tag) => {
    const m = xml.match(new RegExp('<' + tag + '>(.*?)</' + tag + '>'));
    return m ? m[1] : null;
  };

  const vdOffset = parseInt(getXmlVal(headerXml, 'm_cbOffsetHeader'));
  const vdSize = parseInt(getXmlVal(headerXml, 'DataSize'));
  const errorCode = getXmlVal(headerXml, 'ErrorCode') === 'true';
  const applyCompression = getXmlVal(headerXml, 'ApplyCompression') === 'true';
  if (!vdOffset || !vdSize) throw new Error('Invalid ABF BackupLogHeader');

  // VirtualDirectory: UTF-8 XML
  const vdText = new TextDecoder('utf-8').decode(data.subarray(vdOffset, vdOffset + vdSize));
  const vdFiles = {};
  const vdRe = /<BackupFile><Path>(.*?)<\/Path><Size>(\d+)<\/Size><m_cbOffsetHeader>(\d+)<\/m_cbOffsetHeader>/g;
  let m, lastPath = null;
  while ((m = vdRe.exec(vdText)) !== null) {
    vdFiles[m[1]] = { size: parseInt(m[2]), offset: parseInt(m[3]) };
    lastPath = m[1];
  }

  // BackupLog: last VD entry
  if (!lastPath) throw new Error('Empty VirtualDirectory');
  const logEntry = vdFiles[lastPath];
  let logBytes = data.subarray(logEntry.offset, logEntry.offset + logEntry.size);
  if (errorCode && logBytes.length > 4) logBytes = logBytes.subarray(0, logBytes.length - 4);

  let logText;
  if (logBytes[0] === 0xFF && logBytes[1] === 0xFE) logText = new TextDecoder('utf-16le').decode(logBytes.subarray(2));
  else if (logBytes.length > 1 && logBytes[1] === 0) logText = new TextDecoder('utf-16le').decode(logBytes);
  else logText = new TextDecoder('utf-8').decode(logBytes);

  // Build complete file log from BackupLog
  // Maps logical path → VD entry (offset/size in decompressed buffer)
  const fileLog = new Map(); // fileName → { offset, size, sizeFromLog }
  const bfRe = /<BackupFile>[\s\S]*?<Path>(.*?)<\/Path>[\s\S]*?<StoragePath>(.*?)<\/StoragePath>(?:[\s\S]*?<Size>(\d+)<\/Size>)?/g;
  while ((m = bfRe.exec(logText)) !== null) {
    const path = m[1];
    const storagePath = m[2];
    const sizeFromLog = m[3] ? parseInt(m[3]) : 0;
    if (vdFiles[storagePath]) {
      const vd = vdFiles[storagePath];
      // Extract filename from logical path (last segment after \)
      const parts = path.split('\\');
      const fileName = parts[parts.length - 1];
      if (fileName) {
        fileLog.set(fileName, {
          offset: vd.offset,
          size: vd.size,
          sizeFromLog: sizeFromLog,
          path: path
        });
      }
    }
  }

  return {
    data: data,
    fileLog: fileLog,
    errorCode: errorCode,
    applyCompression: applyCompression
  };
}

/**
 * Get a file's data slice from the ABF structure.
 * Handles error_code trimming and optional Xpress8 decompression.
 */
function getDataSlice(abf, fileName) {
  const entry = abf.fileLog.get(fileName);
  if (!entry) throw new Error('File not found in ABF: ' + fileName);

  let slice;
  if (abf.errorCode) {
    slice = abf.data.slice(entry.offset, entry.offset + entry.size - 4);
  } else {
    slice = abf.data.slice(entry.offset, entry.offset + entry.size);
  }

  if (abf.applyCompression) {
    const decompressed = decompressXpress8Chunked(new Uint8Array(slice));
    return decompressed;
  }

  return new Uint8Array(slice);
}

// ============================================================
// Minimal SQLite Reader (from datamodel-decoder.js)
// ============================================================

function readSQLiteTables(dbBuf) {
  const buf = new Uint8Array(dbBuf);
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);

  const magic = new TextDecoder('ascii').decode(buf.subarray(0, 16));
  if (!magic.startsWith('SQLite format 3')) throw new Error('Invalid SQLite database');

  const pageSize = dv.getUint16(16) || 65536;
  const reserved = buf[20];
  const usableSize = pageSize - reserved;

  function getPage(num) { return buf.subarray((num - 1) * pageSize, num * pageSize); }

  function readVarint(data, pos) {
    let result = 0;
    for (let i = 0; i < 8; i++) {
      const b = data[pos + i];
      result = result * 128 + (b & 0x7f);
      if (!(b & 0x80)) return { v: result, n: i + 1 };
    }
    result = result * 256 + data[pos + 8];
    return { v: result, n: 9 };
  }

  function readBE(data, pos, len) {
    let val = 0;
    for (let i = 0; i < len; i++) val = val * 256 + data[pos + i];
    return val;
  }

  function readCellPayload(page, cellPtr) {
    const { v: payloadLen, n: n1 } = readVarint(page, cellPtr);
    const { v: rowid, n: n2 } = readVarint(page, cellPtr + n1);
    let hdrStart = cellPtr + n1 + n2;

    const maxLocal = usableSize - 35;
    const minLocal = ((usableSize - 12) * 32 / 255 | 0) - 23;
    let localSize;
    if (payloadLen <= maxLocal) {
      localSize = payloadLen;
    } else {
      localSize = minLocal + ((payloadLen - minLocal) % (usableSize - 4));
      if (localSize > maxLocal) localSize = minLocal;
    }

    const payload = new Uint8Array(payloadLen);
    payload.set(page.subarray(hdrStart, hdrStart + Math.min(localSize, payloadLen)));

    if (localSize < payloadLen) {
      let overflowPageNum = readBE(page, hdrStart + localSize, 4);
      let written = localSize;
      while (overflowPageNum !== 0 && written < payloadLen) {
        const oPage = getPage(overflowPageNum);
        overflowPageNum = readBE(oPage, 0, 4);
        const avail = Math.min(usableSize - 4, payloadLen - written);
        payload.set(oPage.subarray(4, 4 + avail), written);
        written += avail;
      }
    }

    return { payload, rowid };
  }

  function parseRecord(payload) {
    const { v: headerLen, n: hb } = readVarint(payload, 0);
    const types = [];
    let pos = hb;
    while (pos < headerLen) {
      const { v: st, n: sn } = readVarint(payload, pos);
      types.push(st);
      pos += sn;
    }

    const values = [];
    let dPos = headerLen;
    for (const st of types) {
      if (st === 0) { values.push(null); }
      else if (st >= 1 && st <= 6) {
        const lens = [0, 1, 2, 3, 4, 6, 8];
        const len = lens[st];
        let val = 0;
        for (let i = 0; i < len; i++) val = val * 256 + payload[dPos + i];
        if (len > 0 && payload[dPos] & 0x80) val -= (1 << (len * 8));
        values.push(val);
        dPos += len;
      }
      else if (st === 7) {
        const f64 = new DataView(payload.buffer, payload.byteOffset + dPos, 8).getFloat64(0, false);
        values.push(f64);
        dPos += 8;
      }
      else if (st === 8) { values.push(0); }
      else if (st === 9) { values.push(1); }
      else if (st >= 12 && st % 2 === 0) {
        const len = (st - 12) / 2;
        values.push(payload.slice(dPos, dPos + len));
        dPos += len;
      }
      else if (st >= 13 && st % 2 === 1) {
        const len = (st - 13) / 2;
        values.push(new TextDecoder('utf-8').decode(payload.subarray(dPos, dPos + len)));
        dPos += len;
      }
      else { values.push(null); }
    }
    return values;
  }

  function readTable(rootPage) {
    const rows = [];
    function traverse(pageNum) {
      const page = getPage(pageNum);
      const hdrOff = pageNum === 1 ? 100 : 0;
      const pageType = page[hdrOff];

      if (pageType === 0x0d) {
        const numCells = (page[hdrOff + 3] << 8) | page[hdrOff + 4];
        for (let i = 0; i < numCells; i++) {
          const cellPtr = (page[hdrOff + 8 + i * 2] << 8) | page[hdrOff + 8 + i * 2 + 1];
          const { payload, rowid } = readCellPayload(page, cellPtr);
          try { rows.push({ rowid, values: parseRecord(payload) }); } catch (e) { /* skip corrupt */ }
        }
      } else if (pageType === 0x05) {
        const numCells = (page[hdrOff + 3] << 8) | page[hdrOff + 4];
        const rightChild = readBE(page, hdrOff + 8, 4);
        for (let i = 0; i < numCells; i++) {
          const cellPtr = (page[hdrOff + 12 + i * 2] << 8) | page[hdrOff + 12 + i * 2 + 1];
          const childPage = readBE(page, cellPtr, 4);
          traverse(childPage);
        }
        traverse(rightChild);
      }
    }
    traverse(rootPage);
    return rows;
  }

  // Parse sqlite_master
  const masterRows = readTable(1);
  const tableMap = {};
  for (const row of masterRows) {
    const [type, name, , rootpage] = row.values;
    if (type === 'table' && typeof name === 'string') {
      tableMap[name] = rootpage;
    }
  }

  // Helper: read all rows from a named table
  function getTableRows(tableName) {
    if (!tableMap[tableName]) return [];
    return readTable(tableMap[tableName]);
  }

  return { tableMap, getTableRows };
}

// ============================================================
// Schema Query — Build column metadata from SQLite
// ============================================================

/**
 * Build column schema from the metadata.sqlitedb.
 * Replicates the SQL join from pbixray:
 *   Column → Table, ColumnStorage, ColumnPartitionStorage → StorageFile (IDF)
 *   ColumnStorage → DictionaryStorage → StorageFile (Dictionary)
 *   Column → AttributeHierarchy → AttributeHierarchyStorage → StorageFile (HIDX)
 *
 * Column indices are derived from CREATE TABLE SQL:
 *   Table: rowid=ID, [1]=ModelID, [2]=Name, [4]=Description, [5]=IsHidden
 *   Column: rowid=ID, [1]=TableID, [2]=ExplicitName, [4]=ExplicitDataType,
 *     [7]=Description, [8]=IsHidden, [12]=IsNullable, [18]=ColumnStorageID, [19]=Type
 *   ColumnStorage: rowid=ID, [4]=DictionaryStorageID, [11]=Statistics_DistinctStates
 *   DictionaryStorage: rowid=ID, [5]=BaseId, [6]=Magnitude, [8]=IsNullable, [12]=StorageFileID
 *   ColumnPartitionStorage: rowid=ID, [1]=ColumnStorageID, [6]=StorageFileID
 *   StorageFile: rowid=ID, [4]=FileName
 *   AttributeHierarchy: rowid=ID, [1]=ColumnID, [3]=AttributeHierarchyStorageID
 *   AttributeHierarchyStorage: rowid=ID, [9]=StorageFileID
 *
 * Returns: Map<tableName, { columns: [...] }>
 */
function buildSchemaFromSQLite(db) {
  const tableRows = db.getTableRows('Table');
  const columnRows = db.getTableRows('Column');
  const columnStorageRows = db.getTableRows('ColumnStorage');
  const columnPartitionStorageRows = db.getTableRows('ColumnPartitionStorage');
  const dictionaryStorageRows = db.getTableRows('DictionaryStorage');
  const storageFileRows = db.getTableRows('StorageFile');
  const attrHierRows = db.getTableRows('AttributeHierarchy');
  const attrHierStorageRows = db.getTableRows('AttributeHierarchyStorage');

  // Table: rowid → name
  const tables = new Map();
  for (const r of tableRows) {
    tables.set(r.rowid, { name: r.values[2] });
  }

  // StorageFile: rowid → FileName (values[4])
  const storageFiles = new Map();
  for (const r of storageFileRows) {
    storageFiles.set(r.rowid, r.values[4]);
  }

  // ColumnStorage: rowid → { dictStorageId, cardinality }
  const colStorageMap = new Map();
  for (const r of columnStorageRows) {
    colStorageMap.set(r.rowid, {
      dictStorageId: r.values[4],    // DictionaryStorageID
      cardinality: r.values[11]      // Statistics_DistinctStates
    });
  }

  // DictionaryStorage: rowid → { baseId, magnitude, isNullable, storageFileId }
  const dictStorageMap = new Map();
  for (const r of dictionaryStorageRows) {
    dictStorageMap.set(r.rowid, {
      baseId: r.values[5],           // BaseId
      magnitude: r.values[6],        // Magnitude
      isNullable: r.values[8],       // IsNullable
      storageFileId: r.values[12]    // StorageFileID
    });
  }

  // ColumnPartitionStorage: ColumnStorageID(values[1]) → StorageFileID(values[6])
  const colPartStorageMap = new Map();
  for (const r of columnPartitionStorageRows) {
    colPartStorageMap.set(r.values[1], r.values[6]);
  }

  // AttributeHierarchy: ColumnID(values[1]) → AttributeHierarchyStorageID(values[3])
  const attrHierMap = new Map();
  for (const r of attrHierRows) {
    const colId = r.values[1];
    const ahsId = r.values[3];
    if (colId != null) attrHierMap.set(colId, ahsId);
  }

  // AttributeHierarchyStorage: rowid → StorageFileID(values[9])
  const attrHierStorageMap = new Map();
  for (const r of attrHierStorageRows) {
    attrHierStorageMap.set(r.rowid, r.values[9]);
  }

  const result = new Map();

  for (const r of columnRows) {
    const colId = r.rowid;
    const tableId = r.values[1];        // TableID
    const colName = r.values[2];        // ExplicitName
    const dataType = r.values[4];       // ExplicitDataType
    const colStorageId = r.values[18];  // ColumnStorageID
    const colType = r.values[19];       // Type (1=regular, 2=calculated, 3=rowNumber)

    // Only physical columns
    if (colType !== 1 && colType !== 2) continue;

    const tableInfo = tables.get(tableId);
    if (!tableInfo) continue;
    const tableName = tableInfo.name;

    // Skip internal tables (auto-date, hierarchy, relationship, utility)
    if (tableName.startsWith('LocalDateTable_') ||
        tableName.startsWith('DateTableTemplate_') ||
        tableName.startsWith('H$') ||
        tableName.startsWith('R$') ||
        tableName.startsWith('U$')) continue;

    const cs = colStorageMap.get(colStorageId);
    if (!cs) continue;

    // IDF filename
    const idfSfId = colPartStorageMap.get(colStorageId);
    const idfFile = idfSfId != null ? storageFiles.get(idfSfId) : null;
    if (!idfFile) continue;

    // Dictionary filename
    let dictFile = null;
    let baseId = 0;
    let magnitude = 1;
    let isNullable = false;
    if (cs.dictStorageId != null) {
      const ds = dictStorageMap.get(cs.dictStorageId);
      if (ds) {
        dictFile = ds.storageFileId != null ? storageFiles.get(ds.storageFileId) : null;
        baseId = ds.baseId || 0;
        magnitude = ds.magnitude || 1;
        isNullable = !!ds.isNullable;
      }
    }

    // HIDX filename
    let hidxFile = null;
    const ahsId = attrHierMap.get(colId);
    if (ahsId != null) {
      const sfId = attrHierStorageMap.get(ahsId);
      if (sfId != null) hidxFile = storageFiles.get(sfId);
    }

    if (!result.has(tableName)) {
      result.set(tableName, { columns: [] });
    }

    result.get(tableName).columns.push({
      name: colName,
      idf: idfFile,
      dictionary: dictFile,
      hidx: hidxFile,
      dataType: dataType,
      baseId: baseId,
      magnitude: magnitude,
      isNullable: isNullable,
      cardinality: cs.cardinality
    });
  }

  return result;
}

// ============================================================
// IDF Metadata Parser
// Reads the binary .idfmeta file to extract:
//   - min_data_id, count_bit_packed, bit_width
// ============================================================

function readIdfMeta(buf) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  let pos = 0;

  // CP tag: "<1:CP\0" (6 bytes)
  pos += 6; // skip tag
  // version_one: u64le
  pos += 8;

  // CS0 element
  // CS tag: "<1:CS\0" (6 bytes)
  pos += 6;
  // records: u64le
  pos += 8;
  // one: u64le
  pos += 8;
  // a_b_a_5_a: u32le
  const aba5a = dv.getUint32(pos, true); pos += 4;
  // iterator: u32le
  const iterator = dv.getUint32(pos, true); pos += 4;
  // bookmark_bits: u64le
  pos += 8;
  // storage_alloc_size: u64le
  pos += 8;
  // storage_used_size: u64le
  pos += 8;
  // segment_needs_resizing: u8
  pos += 1;
  // compression_info: u32le
  pos += 4;

  // SS element
  // SS tag: "<1:SS\0" (6 bytes)
  pos += 6;
  // distinct_states: u64le
  pos += 8;
  // min_data_id: u32le
  const minDataId = dv.getUint32(pos, true); pos += 4;
  // max_data_id: u32le
  pos += 4;
  // original_min_segment_data_id: u32le
  pos += 4;
  // rle_sort_order: s64le
  pos += 8;
  // row_count: u64le
  const rowCount = Number(dv.getBigUint64(pos, true)); pos += 8;
  // has_nulls: u8
  pos += 1;
  // rle_runs: u64le
  pos += 8;
  // others_rle_runs: u64le
  pos += 8;
  // SS end tag (6 bytes)
  pos += 6;

  // has_bit_packed_sub_seg: u8
  pos += 1;

  // CS1 element
  // CS tag (6 bytes)
  pos += 6;
  // count_bit_packed: u64le
  const countBitPacked = Number(dv.getBigUint64(pos, true));

  const bitWidth = (36 - aba5a) + iterator;

  return { minDataId, countBitPacked, bitWidth, rowCount };
}

// ============================================================
// IDF Data Parser — RLE + bit-packed hybrid
// ============================================================

function readIdf(buf) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  let pos = 0;

  // Read first segment only (sufficient for single-segment columns)
  // primary_segment_size: u64le
  const primarySize = Number(dv.getBigUint64(pos, true)); pos += 8;

  // primary_segment entries: [data_value:u32, repeat_value:u32]
  const primarySegment = [];
  for (let i = 0; i < primarySize; i++) {
    const dataValue = dv.getUint32(pos, true); pos += 4;
    const repeatValue = dv.getUint32(pos, true); pos += 4;
    primarySegment.push({ dataValue, repeatValue });
  }

  // sub_segment_size: u64le
  const subSegSize = Number(dv.getBigUint64(pos, true)); pos += 8;

  // sub_segment: array of u64le values
  const subSegment = [];
  for (let i = 0; i < subSegSize; i++) {
    subSegment.push(dv.getBigUint64(pos, true)); pos += 8;
  }

  return { primarySegment, subSegment };
}

function decodeRleBitPackedHybrid(idfData, meta) {
  const { primarySegment, subSegment } = idfData;
  const { minDataId, countBitPacked, bitWidth } = meta;

  // Decode bit-packed values from sub_segment
  let bitpackedValues = [];
  if (countBitPacked > 0 && subSegment.length > 0) {
    // Check for single-value case (empty strings column)
    if (subSegment.length === 1 && subSegment[0] === 0n) {
      bitpackedValues = new Array(countBitPacked).fill(minDataId);
    } else {
      const mask = BigInt((1 << bitWidth) - 1);
      const minId = BigInt(minDataId);
      const bw = BigInt(bitWidth);
      for (const u64 of subSegment) {
        let val = u64;
        const count = 64 / bitWidth;
        for (let j = 0; j < count; j++) {
          bitpackedValues.push(Number(minId + (val & mask)));
          val >>= bw;
        }
      }
    }
  }

  // Decode primary segment: RLE + bit-pack markers
  const vector = [];
  let bpOffset = 0;

  for (const entry of primarySegment) {
    if ((entry.dataValue + bpOffset) === 0xFFFFFFFF) {
      // Bit-pack marker
      const count = entry.repeatValue;
      for (let i = 0; i < count && bpOffset + i < bitpackedValues.length; i++) {
        vector.push(bitpackedValues[bpOffset + i]);
      }
      bpOffset += count;
    } else {
      // RLE: repeat data_value
      for (let i = 0; i < entry.repeatValue; i++) {
        vector.push(entry.dataValue);
      }
    }
  }

  return vector;
}

// ============================================================
// Huffman Decoder (for compressed string dictionaries)
// Ported from pbixray/huffman.py
// ============================================================

function decompressEncodeArray(compressed) {
  // Expand 128-byte encode_array to 256 codeword lengths
  const full = new Array(256).fill(0);
  for (let i = 0; i < 128; i++) {
    full[2 * i] = compressed[i] & 0x0F;
    full[2 * i + 1] = (compressed[i] >> 4) & 0x0F;
  }
  return full;
}

function buildHuffmanTree(encodeArray) {
  // Generate canonical Huffman codes from codeword lengths
  const sorted = [];
  for (let i = 0; i < 256; i++) {
    if (encodeArray[i] !== 0) sorted.push([encodeArray[i], i]);
  }
  sorted.sort((a, b) => a[0] - b[0] || a[1] - b[1]);

  // Build tree
  const root = { left: null, right: null, c: 0 };
  let code = 0, lastLen = 0;
  for (const [len, ch] of sorted) {
    if (lastLen !== len) {
      code <<= (len - lastLen);
      lastLen = len;
    }
    // Insert into tree
    let node = root;
    for (let bit = len - 1; bit >= 0; bit--) {
      if (code & (1 << bit)) {
        if (!node.right) node.right = { left: null, right: null, c: 0 };
        node = node.right;
      } else {
        if (!node.left) node.left = { left: null, right: null, c: 0 };
        node = node.left;
      }
    }
    node.c = ch;
    code++;
  }
  return root;
}

function iso88591ToUtf8(code) {
  if (code >= 0x80) {
    return String.fromCharCode(code);
  }
  return String.fromCharCode(code);
}

function decodeHuffmanString(bitstream, tree, startBit, endBit) {
  let result = '';
  let node = tree;
  const totalBits = endBit - startBit;

  for (let i = 0; i < totalBits; i++) {
    let bitPos = startBit + i;
    let bytePos = bitPos >> 3;
    let bitOffset = bitPos & 7;
    // Byte-swap within 16-bit words (same as pbixray)
    bytePos = (bytePos & ~1) + (1 - (bytePos & 1));

    if (!node.left && !node.right) {
      result += iso88591ToUtf8(node.c);
      node = tree;
    }

    if (bitstream[bytePos] & (1 << (7 - bitOffset))) {
      node = node.right;
    } else {
      node = node.left;
    }
  }

  if (!node.left && !node.right) {
    result += iso88591ToUtf8(node.c);
  }

  return result;
}

// ============================================================
// Dictionary Reader
// ============================================================

function readDictionary(buf, minDataId) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  let pos = 0;

  // dictionary_type: s32le (0=long, 1=real, 2=string)
  const dictType = dv.getInt32(pos, true); pos += 4;

  // hash_information: 6 × s32le
  pos += 24;

  if (dictType === 2) {
    // String dictionary
    return readStringDictionary(buf, pos, minDataId);
  } else if (dictType === 0 || dictType === 1) {
    // Numeric dictionary (long or real)
    return readNumericDictionary(buf, pos, minDataId, dictType);
  }

  return new Map();
}

function readStringDictionary(buf, pos, minDataId) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const dict = new Map();

  // PageLayout
  // store_string_count: s64le
  pos += 8;
  // f_store_compressed: s8
  pos += 1;
  // store_longest_string: s64le
  pos += 8;
  // store_page_count: s64le
  const pageCount = Number(dv.getBigInt64(pos, true)); pos += 8;

  // Read dictionary pages
  const pages = [];
  for (let p = 0; p < pageCount; p++) {
    const page = {};
    // page_mask: u64le
    pos += 8;
    // page_contains_nulls: u8
    pos += 1;
    // page_start_index: u64le
    pos += 8;
    // page_string_count: u64le
    page.stringCount = Number(dv.getBigUint64(pos, true)); pos += 8;
    // page_compressed: u8
    page.compressed = buf[pos]; pos += 1;
    // string_store_begin_mark: 0xDDCCBBAA
    pos += 4;

    if (page.compressed) {
      // CompressedStrings
      page.storeTotalBits = dv.getUint32(pos, true); pos += 4;
      // character_set_type_identifier: u32le
      pos += 4;
      // allocation_size: u64le
      const allocSize = Number(dv.getBigUint64(pos, true)); pos += 8;
      // character_set_used: u8
      pos += 1;
      // ui_decode_bits: u32le
      pos += 4;
      // encode_array: 128 bytes
      page.encodeArray = new Uint8Array(buf.buffer, buf.byteOffset + pos, 128);
      pos += 128;
      // ui64_buffer_size: u64le
      pos += 8;
      // compressed_string_buffer: allocation_size bytes
      page.compressedBuffer = new Uint8Array(buf.buffer, buf.byteOffset + pos, allocSize);
      pos += allocSize;
    } else {
      // UncompressedStrings
      // remaining_store_available: u64le
      pos += 8;
      // buffer_used_characters: u64le
      pos += 8;
      // allocation_size: u64le
      const allocSize = Number(dv.getBigUint64(pos, true)); pos += 8;
      // uncompressed_character_buffer: UTF-16LE
      const textBytes = new Uint8Array(buf.buffer, buf.byteOffset + pos, allocSize);
      page.text = new TextDecoder('utf-16le').decode(textBytes);
      pos += allocSize;
    }

    // string_store_end_mark: 0xCDABCDAB
    pos += 4;
    pages.push(page);
  }

  // DictionaryRecordHandlesVector
  // element_count: u64le
  const handleCount = Number(dv.getBigUint64(pos, true)); pos += 8;
  // element_size: u32le (should be 8)
  pos += 4;

  // Read handles: [{bitOrByteOffset: u32, pageId: u32}]
  const handles = [];
  for (let i = 0; i < handleCount; i++) {
    const offset = dv.getUint32(pos, true); pos += 4;
    const pageId = dv.getUint32(pos, true); pos += 4;
    handles.push({ offset, pageId });
  }

  // Group handles by pageId
  const handlesByPage = new Map();
  for (const h of handles) {
    if (!handlesByPage.has(h.pageId)) handlesByPage.set(h.pageId, []);
    handlesByPage.get(h.pageId).push(h.offset);
  }

  // Decode strings
  let index = minDataId;
  for (let pageId = 0; pageId < pages.length; pageId++) {
    const page = pages[pageId];

    if (page.compressed) {
      const fullEncode = decompressEncodeArray(page.encodeArray);
      const tree = buildHuffmanTree(fullEncode);
      const offsets = handlesByPage.get(pageId) || [];

      for (let i = 0; i < offsets.length; i++) {
        const startBit = offsets[i];
        const endBit = (i + 1 < offsets.length) ? offsets[i + 1] : page.storeTotalBits;
        const decoded = decodeHuffmanString(page.compressedBuffer, tree, startBit, endBit);
        dict.set(index, decoded);
        index++;
      }
    } else {
      // Split by null terminators
      const strings = page.text.split('\0');
      // Remove trailing empty string
      if (strings.length > 0 && strings[strings.length - 1] === '') strings.pop();
      for (const s of strings) {
        dict.set(index, s);
        index++;
      }
    }
  }

  return dict;
}

function readNumericDictionary(buf, pos, minDataId, dictType) {
  const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
  const dict = new Map();

  // VectorOfVectors
  // element_count: u64le
  const count = Number(dv.getBigUint64(pos, true)); pos += 8;
  // element_size: u32le
  const elemSize = dv.getUint32(pos, true); pos += 4;

  for (let i = 0; i < count; i++) {
    let val;
    if (elemSize === 4) {
      val = dv.getInt32(pos, true); pos += 4;
    } else if (elemSize === 8 && dictType === 0) {
      // int64 — read as BigInt then convert (may lose precision for very large values)
      val = Number(dv.getBigInt64(pos, true)); pos += 8;
    } else {
      // float64
      val = dv.getFloat64(pos, true); pos += 8;
    }
    dict.set(minDataId + i, val);
  }

  return dict;
}

// ============================================================
// Data Type Mapping (from pbixray AMO_PANDAS_TYPE_MAPPING)
// ============================================================

const AMO_TYPE_MAP = {
  2: 'string',
  6: 'integer',
  8: 'float',
  9: 'datetime',
  10: 'decimal',
  11: 'boolean',
  17: 'binary'
};

function convertColumnValue(value, dataType) {
  if (value == null) return null;
  switch (dataType) {
    case 9: // datetime: days since 1899-12-30
      return new Date((value - 25569) * 86400000); // Excel epoch → JS epoch
    case 10: // decimal: scaled by 10000
      return value / 10000;
    default:
      return value;
  }
}

// ============================================================
// Main: Extract Table Data
// ============================================================

/**
 * Pre-extract all file slices needed by the schema from the ABF,
 * returning a compact Map<filename, Uint8Array>. After this,
 * the large decompressed ABF buffer can be released.
 */
function _buildFileCache(schema, abf) {
  const cache = new Map();
  const _get = (name) => {
    if (cache.has(name)) return;
    try { cache.set(name, getDataSlice(abf, name)); } catch (e) { /* skip missing */ }
  };
  for (const [, tableInfo] of schema) {
    for (const col of tableInfo.columns) {
      _get(col.idf);
      _get(col.idf + 'meta');
      if (col.dictionary) _get(col.dictionary);
    }
  }
  return cache;
}

/**
 * Extract a single column's decoded values from the file cache.
 * @param {Map} fileCache - Map<filename, Uint8Array>
 * @returns {any[]|null} Decoded values, or null on failure.
 */
function _extractColumn(col, fileCache) {
  let meta;
  try {
    const metaBuf = fileCache.get(col.idf + 'meta');
    if (!metaBuf) return null;
    meta = readIdfMeta(metaBuf);
  } catch (e) { return null; }

  const idfBuf = fileCache.get(col.idf);
  if (!idfBuf) return null;

  const indices = decodeRleBitPackedHybrid(readIdf(idfBuf), meta);

  if (col.dictionary) {
    try {
      const dictBuf = fileCache.get(col.dictionary);
      if (!dictBuf) return indices;
      const dict = readDictionary(dictBuf, meta.minDataId);
      return indices.map(idx => {
        const v = dict.get(idx);
        return v !== undefined ? convertColumnValue(v, col.dataType) : null;
      });
    } catch (e) { return indices; }
  } else if (col.hidx) {
    return indices.map(idx => convertColumnValue((idx + col.baseId) / col.magnitude, col.dataType));
  }
  return indices;
}

/**
 * Extract table data synchronously — all columns at once.
 * Returns columnar format (no row transposition) for memory efficiency.
 *
 * @returns {{ columns: string[], columnData: any[][], rowCount: number }}
 */
function extractTableData(tableName, schema, fileCache) {
  const tableSchema = schema.get(tableName);
  if (!tableSchema) throw new Error('Table not found in schema: ' + tableName);

  const columns = [];
  const columnData = [];

  for (const col of tableSchema.columns) {
    const values = _extractColumn(col, fileCache);
    if (values === null) continue;
    columns.push(col.name);
    columnData.push(values);
  }

  const rowCount = columnData.reduce((max, c) => Math.max(max, c.length), 0);
  return { columns, columnData, rowCount };
}

/**
 * Extract table data with streaming — decodes one column at a time,
 * yielding to the event loop between columns so the UI stays responsive.
 *
 * @param {Function} onProgress - (colIndex, totalCols, colName) => void
 * @returns {Promise<{ columns: string[], columnData: any[][], rowCount: number }>}
 */
async function extractTableDataStreaming(tableName, schema, fileCache, onProgress) {
  const tableSchema = schema.get(tableName);
  if (!tableSchema) throw new Error('Table not found in schema: ' + tableName);

  const columns = [];
  const columnData = [];
  const totalCols = tableSchema.columns.length;

  for (let i = 0; i < totalCols; i++) {
    const col = tableSchema.columns[i];
    if (onProgress) onProgress(i, totalCols, col.name);
    // Yield to event loop between columns
    await new Promise(r => setTimeout(r, 0));

    const values = _extractColumn(col, fileCache);
    if (values === null) continue;
    columns.push(col.name);
    columnData.push(values);
  }

  const rowCount = columnData.reduce((max, c) => Math.max(max, c.length), 0);
  return { columns, columnData, rowCount };
}

/**
 * Get a slice of rows from columnar data (on-demand transposition).
 * @returns {any[][]}
 */
function getRowSlice(tableData, start, count) {
  const { columnData, rowCount } = tableData;
  const end = Math.min(start + count, rowCount);
  const rows = [];
  for (let r = start; r < end; r++) {
    const row = [];
    for (let c = 0; c < columnData.length; c++) {
      row.push(r < columnData[c].length ? columnData[c][r] : null);
    }
    rows.push(row);
  }
  return rows;
}

// ============================================================
// Public API: Full .pbix data extraction pipeline
// ============================================================

/**
 * Decompress and parse a .pbix DataModel blob.
 *
 * After building the schema, pre-extracts only the needed file slices
 * (IDF, dictionaries) into a compact cache and releases the large
 * decompressed ABF buffer so it can be garbage-collected.
 *
 * @param {ArrayBuffer} dataModelBuf - Raw DataModel from .pbix ZIP
 * @returns {Promise<{ tableNames, schema, getTable, getTableStreaming }>}
 */
async function parsePbixDataModel(dataModelBuf) {
  const decompressed = await decompressXpress9(dataModelBuf);
  const abf = parseABF(decompressed);
  const sqliteBuf = getDataSlice(abf, 'metadata.sqlitedb');
  const db = readSQLiteTables(sqliteBuf);
  const schema = buildSchemaFromSQLite(db);

  // Pre-extract needed file slices, then release the large decompressed buffer
  const fileCache = _buildFileCache(schema, abf);
  abf.data = null; // allow GC of the decompressed DataModel

  const tableNames = Array.from(schema.keys()).sort();

  return {
    tableNames,
    schema,
    /** Synchronous extraction — blocks until complete. */
    getTable(tableName) {
      return extractTableData(tableName, schema, fileCache);
    },
    /** Streaming extraction — yields between columns for UI responsiveness. */
    getTableStreaming(tableName, onProgress) {
      return extractTableDataStreaming(tableName, schema, fileCache, onProgress);
    }
  };
}
