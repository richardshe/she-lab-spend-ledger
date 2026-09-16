"""Run parse_po over every PO PDF and report reconciliation failures."""
import glob, os, re, sys, json, traceback
sys.path.insert(0, os.path.dirname(__file__))
from parse_po import parse_po
from parse_screenprint import parse_screenprint

SRC = "/Users/richardshe/Documents/Codex Projects/Ariba POs"
OUT = os.path.join(os.path.dirname(__file__), '..', 'po_raw.json')

pos = sorted(f for f in glob.glob(os.path.join(SRC, '9100*.pdf'))
             if re.fullmatch(r'9100\d+\.pdf', os.path.basename(f)))
recs, problems = [], []
for f in pos:
    try:
        hdr, items = parse_po(f)
        if hdr.get('po_number') is None:
            # not the standard PO layout - fall back to the Ariba screen print
            hdr, items = parse_screenprint(f)
        hdr.setdefault('layout', 'standard_po')
        hdr['source_pdf'] = os.path.basename(f)
        n, dn = len(items), hdr.get('declared_line_count')
        if dn is not None and n != dn:
            problems.append((os.path.basename(f), f'line count {n} != declared {dn}'))
        tot = sum(i['amount'] for i in items if i['amount'] is not None)
        pt = hdr.get('po_total')
        if pt is not None and abs(tot - pt) > 0.05:
            problems.append((os.path.basename(f), f'sum(lines)={tot:.2f} != po_total={pt:.2f}'))
        missing = [i['line_no'] for i in items if i['amount'] is None]
        if missing:
            problems.append((os.path.basename(f), f'lines missing amount: {missing}'))
        recs.append({'header': hdr, 'items': items})
    except Exception:
        problems.append((os.path.basename(f), 'EXC ' + traceback.format_exc().splitlines()[-1]))

# Ariba issues PO numbers in chronological order, so a PO whose PDF carries no
# issue date can be dated by interpolating between its numeric neighbours.
import datetime
dated = sorted((int(r['header']['po_number']), r['header']['issued_date'])
               for r in recs if r['header'].get('issued_date'))
for r in recs:
    if r['header'].get('issued_date'):
        continue
    n = int(r['header']['po_number'])
    before = [d for k, d in dated if k < n]
    after = [d for k, d in dated if k > n]
    if before and after:
        a = datetime.datetime.strptime(before[-1], '%Y-%m-%d')
        b = datetime.datetime.strptime(after[0], '%Y-%m-%d')
        r['header']['issued_date'] = (a + (b - a) / 2).strftime('%Y-%m-%d')
        r['header']['issued_date_estimated'] = True
        print(f"estimated issue date for {r['header']['po_number']}: "
              f"{r['header']['issued_date']} (between {before[-1]} and {after[0]})")

json.dump(recs, open(OUT, 'w'), indent=1)
print(f'parsed {len(recs)} POs, {sum(len(r["items"]) for r in recs)} line items')
print(f'--- {len(problems)} problems ---')
for f, p in problems:
    print(f'{f}: {p}')
