"""Join parsed POs, quotes and the Ariba manifest into the analysis CSVs."""
import csv, json, os, sys, re, collections, datetime
sys.path.insert(0, os.path.dirname(__file__))
from categorize import categorize, vendor_group

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = "/Users/richardshe/Documents/Codex Projects/Ariba POs"
OUT = os.path.join(SRC, 'analytics')
os.makedirs(OUT, exist_ok=True)

# Nominal rate used to state mixed-currency spend on one axis. The PO PDFs do not
# carry the rate NTU actually settled at, so this is an assumption, surfaced as
# its own column and adjustable in the dashboard.
USD_SGD = 1.30

pos = json.load(open(os.path.join(HERE, '..', 'po_raw.json')))
quotes = json.load(open(os.path.join(HERE, '..', 'quotes_raw.json')))

manifest = {}
with open(os.path.join(SRC, 'manifest.csv'), encoding='utf-8-sig') as fh:
    for row in csv.DictReader(fh):
        if row.get('po_number'):
            manifest[row['po_number']] = row

q_by_po = collections.defaultdict(list)
for q in quotes:
    if q.get('linked_po'):
        q_by_po[q['linked_po']].append(q)

FY_START = datetime.date(2025, 9, 1)   # first PO in the set is 19-Sep-2025

rows = []
for rec in pos:
    h, man = rec['header'], manifest.get(rec['header'].get('po_number'), {})
    cur = h.get('currency') or 'SGD'
    fx = USD_SGD if cur == 'USD' else 1.0
    qs = q_by_po.get(h.get('po_number'), [])
    disc_pct = max([q['discount_pct_max'] for q in qs
                    if q.get('discount_pct_max')], default=None)
    disc_amt = sum(q['discount_amount'] for q in qs if q.get('discount_amount')) or None
    disc_note = ' // '.join(q['discount_notes'] for q in qs if q.get('discount_notes')) or None
    d = h.get('issued_date')
    dt = datetime.date.fromisoformat(d) if d else None

    for it in rec['items']:
        cat, sub, rule = categorize(it, h.get('supplier'), man.get('title', ''),
                                    h.get('gl_account') or '', h.get('po_number'))
        conf = ('high' if rule.startswith('kw:') else
                'manual' if rule.startswith('manual') else
                'medium' if rule.startswith('title:') else 'low')
        amt = it.get('amount') or 0.0
        net = it.get('net_amount')
        tax = it.get('taxes')
        rows.append({
            'po_number': h.get('po_number'),
            'line_no': it['line_no'],
            'issue_date': d,
            'issue_date_estimated': bool(h.get('issued_date_estimated')),
            'fy_month': dt.strftime('%Y-%m') if dt else None,
            'fy_quarter': f'{dt.year}-Q{(dt.month - 1) // 3 + 1}' if dt else None,
            'requisition': h.get('requisition'),
            'pr_title': man.get('title') or '',
            'supplier': h.get('supplier'),
            'vendor': vendor_group(h.get('supplier')),
            'category': cat,
            'subcategory': sub,
            'category_rule': rule,
            'category_confidence': conf,
            'item': (it.get('product_name') or it.get('description') or '').strip(),
            'item_full_description': (it.get('full_description') or '').strip()[:500],
            'part_number': it.get('part_number') or '',
            'qty': it.get('qty'),
            'uom': it.get('uom') or '',
            'currency': cur,
            'unit_price': it.get('unit_price'),
            'net_amount': net,
            'discount_on_po': it.get('discount') or 0.0,
            'tax_amount': tax,
            'gross_amount': amt,
            'fx_rate_to_sgd': fx,
            'net_amount_sgd': round(net * fx, 2) if net is not None else None,
            'gross_amount_sgd': round(amt * fx, 2),
            'wbs': h.get('wbs') or '',
            'wbs_suffix': (h.get('wbs') or '')[-5:],
            'wbs_description': h.get('wbs_description') or '',
            'gl_account': h.get('gl_account') or '',
            'gl_name': h.get('gl_name') or '',
            'fund': h.get('fund') or '',
            'funds_center': h.get('funds_center') or '',
            'grant': h.get('grant') or '',
            'requester': h.get('created_by') or '',
            'receiver': h.get('receiver') or '',
            'need_by_date': it.get('need_by') or '',
            'po_status': man.get('po_status') or '',
            'quote_files': ' | '.join(q['quote_file'] for q in qs),
            'quote_discount_pct': disc_pct,
            'quote_discount_amount': disc_amt,
            'quote_discount_note': (disc_note or '')[:300],
            'amount_source': it.get('amount_source') or 'po_table',
            'po_total': h.get('po_total'),
            'source_pdf': h.get('source_pdf'),
        })

rows.sort(key=lambda r: (r['issue_date'] or '', r['po_number'], r['line_no']))
path = os.path.join(OUT, 'po_line_items.csv')
with open(path, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f'wrote {path}: {len(rows)} rows')

# Order-level roll-up
orders, seen = [], set()
for rec in pos:
    h = rec['header']
    if h['po_number'] in seen:
        continue
    seen.add(h['po_number'])
    man = manifest.get(h['po_number'], {})
    cur = h.get('currency') or 'SGD'
    fx = USD_SGD if cur == 'USD' else 1.0
    lines = [r for r in rows if r['po_number'] == h['po_number']]
    cats = collections.Counter(r['category'] for r in lines)
    orders.append({
        'po_number': h['po_number'], 'issue_date': h.get('issued_date'),
        'requisition': h.get('requisition'), 'pr_title': man.get('title') or '',
        'supplier': h.get('supplier'), 'vendor': vendor_group(h.get('supplier')),
        'n_lines': len(lines), 'currency': cur,
        'po_total': h.get('po_total'),
        'po_total_sgd': round((h.get('po_total') or 0) * fx, 2),
        'dominant_category': cats.most_common(1)[0][0] if cats else '',
        'wbs': h.get('wbs') or '', 'gl_name': h.get('gl_name') or '',
        'requester': h.get('created_by') or '',
        'po_status': man.get('po_status') or '', 'source_pdf': h.get('source_pdf'),
    })
orders.sort(key=lambda r: (r['issue_date'] or '', r['po_number']))
path = os.path.join(OUT, 'po_orders.csv')
with open(path, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(orders[0].keys()))
    w.writeheader(); w.writerows(orders)
print(f'wrote {path}: {len(orders)} rows')

# Quote register
path = os.path.join(OUT, 'quotes.csv')
cols = ['quote_file', 'linked_po', 'linked_pr', 'quote_ref', 'status',
        'quote_date_text', 'quote_currency', 'quote_max_amount',
        'discount_pct_max', 'discount_amount', 'discount_notes']
with open(path, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
    w.writeheader()
    for q in quotes:
        q = dict(q); q.pop('discount_pcts', None)
        w.writerow(q)
print(f'wrote {path}: {len(quotes)} rows')

# Denied requisitions never became POs, so they carry no spend. Keep them in a
# separate register - several have quotes, so the intended value is recoverable.
denied = []
with open(os.path.join(SRC, '_no_po_requisitions.csv'), encoding='utf-8-sig') as fh:
    for row in csv.DictReader(fh):
        pr = row['requisition']
        qs = [q for q in quotes if q.get('linked_pr') == pr]
        denied.append({
            'requisition': pr,
            'note': row.get('note', ''),
            'quote_files': ' | '.join(q['quote_file'] for q in qs),
            'quoted_amount': max([q['quote_max_amount'] for q in qs
                                  if q.get('quote_max_amount')], default=None),
            'quote_currency': next((q.get('quote_currency') for q in qs
                                    if q.get('quote_currency')), None),
        })
path = os.path.join(OUT, 'denied_requisitions.csv')
with open(path, 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(denied[0].keys()))
    w.writeheader(); w.writerows(denied)
print(f'wrote {path}: {len(denied)} rows')

# --- summary ---
tot_sgd = sum(r['gross_amount_sgd'] for r in rows)
print(f'\nTotal committed spend: S${tot_sgd:,.2f} '
      f'({len(orders)} POs, {len(rows)} lines, {USD_SGD} USD->SGD)')
by = collections.Counter()
for r in rows:
    by[r['category']] += r['gross_amount_sgd']
for k, v in by.most_common():
    print(f'  {v:11,.2f}  {v/tot_sgd*100:5.1f}%  {k}')
unc = [r for r in rows if r['category'] == 'Uncategorised']
print(f'\nUncategorised: {len(unc)} lines, S${sum(r["gross_amount_sgd"] for r in unc):,.2f}')
for r in unc:
    print(f'   {r["gross_amount_sgd"]:9,.2f} {r["vendor"][:28]:28} | {r["item"][:60]}')
