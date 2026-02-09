#!/usr/bin/env python3
"""Extract the monolithic HTML into modular source files for the build system."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(ROOT, 'semantic-model-explorer.html')

with open(HTML_PATH, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# --- Extract CSS (lines 9-215, 1-indexed) ---
css_lines = lines[8:215]  # 0-indexed: 8 to 214 inclusive
css = ''.join(css_lines)
with open(os.path.join(ROOT, 'src', 'styles.css'), 'w', encoding='utf-8') as f:
    f.write(css)
print(f"Extracted styles.css ({len(css)} bytes)")

# --- Extract main app JS (lines 336-2261, 1-indexed) ---
js_lines = lines[335:2261]  # 0-indexed: 335 to 2260 inclusive
app_js = ''.join(js_lines)
with open(os.path.join(ROOT, 'src', 'app.js'), 'w', encoding='utf-8') as f:
    f.write(app_js)
print(f"Extracted app.js ({len(app_js)} bytes)")

# --- Extract HTML body (lines 218-334, 1-indexed) ---
body_lines = lines[217:334]  # 0-indexed: 217 to 333 inclusive
body_html = ''.join(body_lines)

# --- Extract JSZip (lines 2269-2284, 1-indexed) ---
# Line 2269 is "<!-- JSZip v3.10.1 - bundled inline -->"
# Line 2270 is "<script>"
# Lines 2271-2283 are the JSZip source
# Line 2284 is "</script>"
jszip_lines = lines[2270:2283]  # 0-indexed: content lines
jszip = ''.join(jszip_lines)
with open(os.path.join(ROOT, 'lib', 'jszip.min.js'), 'w', encoding='utf-8') as f:
    f.write(jszip)
print(f"Extracted jszip.min.js ({len(jszip)} bytes)")

# --- Extract Cytoscape (lines 2286-2321, 1-indexed) ---
# Line 2286 is "<!-- Cytoscape v3.30.4 - bundled inline -->"
# Line 2287 is "<script>"
# Lines 2288-2320 are the Cytoscape source
# Line 2321 is "</script>"
cyto_lines = lines[2287:2320]  # 0-indexed: content lines
cyto = ''.join(cyto_lines)
with open(os.path.join(ROOT, 'lib', 'cytoscape.min.js'), 'w', encoding='utf-8') as f:
    f.write(cyto)
print(f"Extracted cytoscape.min.js ({len(cyto)} bytes)")

# --- Create template.html ---
template = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; img-src data: blob:;">
<title>Semantic Model Explorer</title>
<style>
{{STYLES}}
</style>
</head>
''' + body_html + '''
<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- XPress9 Emscripten WASM Module -->
<script>
{{XPRESS9_GLUE}}
</script>

<!-- Main Application -->
<script>
'use strict';
{{APP_JS}}
</script>

<!-- VertiPaq Decoder: XPress9 + ABF + VertiPaq column extraction -->
<script>
'use strict';
{{VERTIPAQ_JS}}
</script>

<!-- Data Export: CSV + Parquet -->
<script>
'use strict';
{{EXPORT_JS}}
</script>

<!-- JSZip v3.10.1 -->
<script>
{{JSZIP}}
</script>

<!-- Cytoscape v3.30.4 -->
<script>
{{CYTOSCAPE}}
</script>

<!-- hyparquet-writer (Parquet file writer) -->
<script>
{{HYPARQUET_WRITER}}
</script>

</body>
</html>
'''

with open(os.path.join(ROOT, 'src', 'template.html'), 'w', encoding='utf-8') as f:
    f.write(template)
print(f"Created template.html ({len(template)} bytes)")

print("\nDone! Source files extracted to src/ and lib/")
