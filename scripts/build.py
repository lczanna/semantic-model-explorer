#!/usr/bin/env python3
"""
Build script for Semantic Model Explorer.

Assembles modular source files into a single self-contained HTML file.
All JavaScript libraries, CSS, and WASM binaries are inlined.

Usage:
    python scripts/build.py              # Build to semantic-model-explorer.html
    python scripts/build.py --output X   # Build to custom path

Source structure:
    src/template.html       HTML skeleton with {{PLACEHOLDER}} markers
    src/styles.css          Application CSS
    src/app.js              Main application (parsers, UI, events)
    src/vertipaq.js         VertiPaq decoder (XPress9, ABF, SQLite, column extraction)
    src/export.js           CSV + Parquet export and Data tab UI

    lib/jszip.min.js        JSZip library (ZIP parsing)
    lib/cytoscape.min.js    Cytoscape.js (ER diagram)
    lib/xpress9-glue.js     Emscripten WASM module for XPress9
    lib/xpress9.wasm.b64    Base64-encoded XPress9 WASM binary
    lib/hyparquet-writer.min.js  Parquet file writer
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_file(rel_path):
    """Read a file relative to project root."""
    path = os.path.join(ROOT, rel_path)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def build(output_path=None):
    if output_path is None:
        output_path = os.path.join(ROOT, 'index.html')

    # Read template
    template = read_file('src/template.html')

    # Read source files
    styles = read_file('src/styles.css')
    app_js = read_file('src/app.js')

    # VertiPaq and export are optional (might not exist yet during initial development)
    try:
        vertipaq_js = read_file('src/vertipaq.js')
    except FileNotFoundError:
        vertipaq_js = '// VertiPaq decoder not yet implemented'
        print('  Warning: src/vertipaq.js not found, using stub')

    try:
        export_js = read_file('src/export.js')
    except FileNotFoundError:
        export_js = '// Export module not yet implemented'
        print('  Warning: src/export.js not found, using stub')

    # Read libraries
    jszip = read_file('lib/jszip.min.js')
    cytoscape = read_file('lib/cytoscape.min.js')
    xpress9_glue = read_file('lib/xpress9-glue.js')
    xpress9_wasm_b64 = read_file('lib/xpress9.wasm.b64').strip()
    hyparquet_writer = read_file('lib/hyparquet-writer.min.js')

    # Inject WASM base64 into vertipaq.js
    vertipaq_js = vertipaq_js.replace('%%XPRESS9_WASM_B64%%', xpress9_wasm_b64)

    # Assemble HTML
    # IMPORTANT: Use string concatenation, NOT template literals / f-strings
    # with library content, because minified JS may contain curly braces.
    html = template
    html = html.replace('{{STYLES}}', styles)
    html = html.replace('{{APP_JS}}', app_js)
    html = html.replace('{{VERTIPAQ_JS}}', vertipaq_js)
    html = html.replace('{{EXPORT_JS}}', export_js)
    html = html.replace('{{JSZIP}}', jszip)
    html = html.replace('{{CYTOSCAPE}}', cytoscape)
    html = html.replace('{{XPRESS9_GLUE}}', xpress9_glue)
    html = html.replace('{{HYPARQUET_WRITER}}', hyparquet_writer)

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    size_kb = os.path.getsize(output_path) / 1024
    print(f'Built {output_path} ({size_kb:.1f} KB)')

    # Verify no unresolved placeholders remain
    import re
    remaining = re.findall(r'\{\{[A-Z_]+\}\}', html)
    if remaining:
        print(f'  WARNING: Unresolved placeholders: {remaining}', file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build Semantic Model Explorer HTML')
    parser.add_argument('--output', '-o', help='Output file path')
    args = parser.parse_args()
    sys.exit(build(args.output))
