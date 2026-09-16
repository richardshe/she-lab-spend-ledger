"""Extract what is reliably comparable from the heterogeneous quote PDFs.

Quote layouts vary by vendor, so rather than forcing a line-item schema we pull
the facts that survive across formats: the linked PO/PR, quote reference, dates,
the largest money figure (the quote total), and any discount signal - explicit
percentages, an aggregate discount amount, or a narrative remark.
"""
import glob, os, re, json
import pymupdf

SRC = "/Users/richardshe/Documents/Codex Projects/Ariba POs"

PCT = re.compile(r'(\d{1,2}(?:\.\d+)?)\s*%\s*(?:exclusive\s+)?(?:off|discount)'
                 r'|(?:discount|off)\D{0,20}?(\d{1,2}(?:\.\d+)?)\s*%')
TOTAL_DISC = re.compile(r'total\s+discount\s*:?\s*[A-Z]{0,3}\$?\s*([\d,]+\.\d{2})', re.I)
MONEY = re.compile(r'(?:S\$|US\$|\$|SGD|USD|RMB|CNY|EUR|\bGBP)\s*([\d,]+\.\d{2})')
DISC_SENT = re.compile(r'[^.\n]*\bdiscount\b[^.\n]*', re.I)


def parse_quote(path):
    name = os.path.basename(path)
    m = re.match(r'(9100\d+|PR\d+)_quote_(.+)\.(pdf|xls)$', name, re.I)
    rec = {
        'quote_file': name,
        'linked_po': m.group(1) if m and m.group(1).startswith('9100') else None,
        'linked_pr': m.group(1) if m and m.group(1).startswith('PR') else None,
        'quote_ref': m.group(2) if m else None,
    }
    if name.lower().endswith('.xls'):
        rec['status'] = 'spreadsheet attachment - not parsed'
        return rec
    try:
        text = "\n".join(p.get_text() for p in pymupdf.open(path))
    except Exception as e:
        rec['status'] = f'unreadable: {e}'
        return rec
    if len(text.strip()) < 100:
        rec['status'] = 'scanned image - text layer empty (needs OCR)'
        return rec
    rec['status'] = 'parsed'
    flat = re.sub(r'[ \t]+', ' ', text)

    amounts = [float(x.replace(',', '')) for x in MONEY.findall(flat)]
    rec['quote_max_amount'] = max(amounts) if amounts else None
    for cur in ('SGD', 'USD', 'S$', 'US$', 'RMB', 'EUR'):
        if cur in flat:
            rec['quote_currency'] = {'S$': 'SGD', 'US$': 'USD'}.get(cur, cur)
            break

    pcts = [float(a or b) for a, b in PCT.findall(flat)]
    rec['discount_pct_max'] = max(pcts) if pcts else None
    rec['discount_pcts'] = sorted(set(pcts)) or None
    td = TOTAL_DISC.search(flat)
    rec['discount_amount'] = float(td.group(1).replace(',', '')) if td else None
    notes = [re.sub(r'\s+', ' ', s).strip() for s in DISC_SENT.findall(flat)]
    notes = [n for n in notes if len(n) > 25 and 'warrant' not in n.lower()][:3]
    rec['discount_notes'] = ' // '.join(notes) or None
    d = re.search(r'(\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{2,4}|'
                  r'[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})', flat)
    rec['quote_date_text'] = d.group(1) if d else None
    return rec


if __name__ == '__main__':
    files = sorted(glob.glob(os.path.join(SRC, '*_quote_*')))
    recs = [parse_quote(f) for f in files]
    out = os.path.join(os.path.dirname(__file__), '..', 'quotes_raw.json')
    json.dump(recs, open(out, 'w'), indent=1)
    print(f'{len(recs)} quote files')
    import collections
    print(collections.Counter(r['status'] for r in recs))
    print('with discount pct:', sum(1 for r in recs if r.get('discount_pct_max')))
    print('with discount amt:', sum(1 for r in recs if r.get('discount_amount')))
    for r in recs:
        if r.get('discount_pct_max') or r.get('discount_amount'):
            print(f"  {r['linked_po'] or r['linked_pr']:>12} pct={r.get('discount_pct_max')} "
                  f"amt={r.get('discount_amount')} :: {(r.get('discount_notes') or '')[:100]}")
