#!/usr/bin/env bash
# Rebuild the whole dataset from the PDFs in the parent folder.
set -euo pipefail
cd "$(dirname "$0")"
python3 extract_all.py     # PO PDFs      -> ../po_raw.json
python3 parse_quotes.py    # quote PDFs   -> ../quotes_raw.json
python3 build_dataset.py   # join + label -> ../analytics/*.csv
python3 make_payload.py    # dashboard payload -> ../payload.json
python3 - <<'PY'
import json, os
p = json.load(open(os.path.join('..', 'payload.json')))
open(os.path.join('..', 'dashboard', 'data.js'), 'w').write(
    'window.__LEDGER=' + json.dumps(p, separators=(',', ':')) + ';')
print('refreshed dashboard/data.js')
PY
