"""Emit the compact JSON the dashboard embeds (columnar-ish, trimmed fields)."""
import csv, json, os

SRC = "/Users/richardshe/Documents/Codex Projects/Ariba POs/analytics"

def num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None

items = []
for r in csv.DictReader(open(os.path.join(SRC, 'po_line_items.csv'))):
    items.append({
        'po': r['po_number'], 'ln': int(r['line_no']), 'd': r['issue_date'],
        'm': r['fy_month'], 'pr': r['requisition'], 'prt': r['pr_title'],
        'v': r['vendor'], 'sup': r['supplier'],
        'c': r['category'], 's': r['subcategory'], 'cf': r['category_confidence'],
        'i': r['item'], 'sp': r['item_spec'], 'dt': r['item_detail'],
        'pn': r['part_number'],
        'q': num(r['qty']), 'u': r['uom'], 'cur': r['currency'],
        'up': num(r['unit_price']), 'net': num(r['net_amount']),
        'tax': num(r['tax_amount']), 'gr': num(r['gross_amount']),
        'w': r['wbs'], 'ws': r['wbs_suffix'], 'gl': r['gl_name'],
        'rq': r['requester'],
        'dp': num(r['quote_discount_pct']), 'da': num(r['quote_discount_amount']),
        'dn': r['quote_discount_note'], 'qf': r['quote_files'],
        'est': r['issue_date_estimated'] == 'True',
        'src': r['amount_source'],
    })

denied = list(csv.DictReader(open(os.path.join(SRC, 'denied_requisitions.csv'))))
quotes = [q for q in csv.DictReader(open(os.path.join(SRC, 'quotes.csv')))
          if q['discount_pct_max'] or q['discount_amount']
          or q['status'] != 'parsed']

payload = {'items': items, 'denied': denied, 'quotes': quotes,
           'generated': '2026-09-16'}
out = os.path.join(os.path.dirname(__file__), '..', 'payload.json')
json.dump(payload, open(out, 'w'), separators=(',', ':'))
print(f'{out}: {os.path.getsize(out)/1024:.0f} KB, {len(items)} items, '
      f'{len(denied)} denied, {len(quotes)} flagged quotes')
