#!/usr/bin/env python3
"""Debug script to inspect SQLite table schemas in a .pbix DataModel."""

import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from playwright.sync_api import sync_playwright

HTML_PATH = os.path.join(ROOT, 'semantic-model-explorer.html')
PBIX_PATH = os.path.join(ROOT, 'data', 'test-files', 'Revenue_Opportunities.pbix')

BROWSER_ARGS = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--single-process"]

with sync_playwright() as p:
    browser = p.chromium.launch(args=BROWSER_ARGS)
    page = browser.new_page()
    page.goto(f'file://{HTML_PATH}')
    page.wait_for_load_state('domcontentloaded')

    with open(PBIX_PATH, 'rb') as f:
        pbix_bytes = f.read()

    result = page.evaluate('''async (bytesArray) => {
        const buf = new Uint8Array(bytesArray).buffer;
        const zip = await JSZip.loadAsync(buf);
        const dmFile = zip.file("DataModel");
        const dmBuf = await dmFile.async("arraybuffer");
        const decompressed = await decompressXpress9(dmBuf);
        const abf = parseABF(decompressed);
        const sqliteBuf = getDataSlice(abf, "metadata.sqlitedb");

        // Read sqlite directly to get CREATE TABLE SQL
        const dbBuf = new Uint8Array(sqliteBuf);
        const dv = new DataView(dbBuf.buffer, dbBuf.byteOffset, dbBuf.byteLength);
        const pageSize = dv.getUint16(16) || 65536;
        const reserved = dbBuf[20];
        const usableSize = pageSize - reserved;

        function getPage(num) { return dbBuf.subarray((num - 1) * pageSize, num * pageSize); }
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
            if (payloadLen <= maxLocal) localSize = payloadLen;
            else {
                localSize = minLocal + ((payloadLen - minLocal) % (usableSize - 4));
                if (localSize > maxLocal) localSize = minLocal;
            }
            const payload = new Uint8Array(payloadLen);
            payload.set(page.subarray(hdrStart, hdrStart + Math.min(localSize, payloadLen)));
            if (localSize < payloadLen) {
                let op = readBE(page, hdrStart + localSize, 4);
                let written = localSize;
                while (op !== 0 && written < payloadLen) {
                    const oPage = getPage(op);
                    op = readBE(oPage, 0, 4);
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
                } else if (st === 7) {
                    const f64 = new DataView(payload.buffer, payload.byteOffset + dPos, 8).getFloat64(0, false);
                    values.push(f64);
                    dPos += 8;
                } else if (st === 8) { values.push(0); }
                else if (st === 9) { values.push(1); }
                else if (st >= 12 && st % 2 === 0) {
                    const len = (st - 12) / 2;
                    values.push("<blob:" + len + ">");
                    dPos += len;
                } else if (st >= 13 && st % 2 === 1) {
                    const len = (st - 13) / 2;
                    values.push(new TextDecoder("utf-8").decode(payload.subarray(dPos, dPos + len)));
                    dPos += len;
                } else { values.push(null); }
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
                        const cellPtr = (page[hdrOff + 8 + i*2] << 8) | page[hdrOff + 8 + i*2 + 1];
                        const { payload, rowid } = readCellPayload(page, cellPtr);
                        try { rows.push({ rowid, values: parseRecord(payload) }); } catch(e) {}
                    }
                } else if (pageType === 0x05) {
                    const numCells = (page[hdrOff + 3] << 8) | page[hdrOff + 4];
                    const rightChild = readBE(page, hdrOff + 8, 4);
                    for (let i = 0; i < numCells; i++) {
                        const cellPtr = (page[hdrOff + 12 + i*2] << 8) | page[hdrOff + 12 + i*2 + 1];
                        traverse(readBE(page, cellPtr, 4));
                    }
                    traverse(rightChild);
                }
            }
            traverse(rootPage);
            return rows;
        }

        // Read sqlite_master
        const masterRows = readTable(1);
        const createSQLs = {};
        for (const row of masterRows) {
            const [type, name, tblName, rootpage, sql] = row.values;
            if (type === "table" && sql) {
                // Just get column names from CREATE TABLE
                createSQLs[name] = sql.substring(0, 500);
            }
        }

        // Get Table row with rowid
        const tableTableRoot = masterRows.find(r => r.values[0] === "table" && r.values[1] === "Table");
        let tableWithRowids = null;
        if (tableTableRoot) {
            const rows = readTable(tableTableRoot.values[3]);
            // Show first 3 rows with rowid
            tableWithRowids = rows.slice(0, 3).map(r => ({
                rowid: r.rowid,
                v0: r.values[0],
                v1: r.values[1],
                v2: typeof r.values[2] === "string" ? r.values[2].substring(0, 40) : r.values[2]
            }));
        }

        return { createSQLs, tableWithRowids };
    }''', list(pbix_bytes))

    print("\nCREATE TABLE SQL statements:")
    for name, sql in result['createSQLs'].items():
        if name in ('Table', 'Column', 'ColumnStorage', 'ColumnPartitionStorage',
                     'DictionaryStorage', 'StorageFile', 'AttributeHierarchy',
                     'AttributeHierarchyStorage'):
            print(f"\n  {name}:")
            print(f"    {sql}")

    print(f"\nTable rows with rowid: {result['tableWithRowids']}")

    browser.close()
