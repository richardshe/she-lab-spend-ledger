"""Parse NTU Ariba Purchase Order PDFs into structured line-item records.

The POs are text-based (not scanned) and share a stable layout, so we extract
words with coordinates and reconstruct the LINE ITEM DETAILS table by clustering
words into rows (shared `top`) and assigning them to columns via the x-positions
of the table header words. Header metadata (WBS, GL account, fund) comes from a
two-column label/value grid on page 1.
"""
import re, sys, json
from collections import defaultdict
import pdfplumber

MONEY = re.compile(r'-?\$?\s*([\d,]+\.\d{2})')

# Orders placed with overseas suppliers are rendered in the requester's locale,
# so issue dates appear as "19-Sep-2025", "Wednesday, June 18, 2026" or the
# Chinese long form. Normalise all three to ISO.
CN_MONTHS = {'一月': 1, '二月': 2, '三月': 3, '四月': 4, '五月': 5, '六月': 6,
             '七月': 7, '八月': 8, '九月': 9, '十月': 10, '十一月': 11, '十二月': 12}
EN_MONTHS = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
DATE_PAT = (r'(\d{1,2}-[A-Za-z]{3}-\d{4}'
            r'|[A-Za-z\u4e00-\u9fff]+,\s*[A-Za-z\u4e00-\u9fff]+\s+\d{1,2},\s*\d{4})')


def norm_date(txt):
    """Return ISO yyyy-mm-dd for any of the three rendered date formats."""
    if not txt:
        return None
    txt = txt.strip()
    m = re.match(r'(\d{1,2})-([A-Za-z]{3})-(\d{4})', txt)
    if m:
        d, mon, y = m.groups()
        return f'{int(y):04d}-{EN_MONTHS[mon.lower()]:02d}-{int(d):02d}'
    m = re.match(r'[^,]+,\s*(\S+)\s+(\d{1,2}),\s*(\d{4})', txt)
    if m:
        mon, d, y = m.groups()
        num = CN_MONTHS.get(mon) or EN_MONTHS.get(mon[:3].lower())
        if num:
            return f'{int(y):04d}-{num:02d}-{int(d):02d}'
    return None
LABEL_X = 41.0   # x0 of top-level field labels in the header grid
SUB_X = 63.0     # x0 of indented sub-field keys
XTOL = 3.0

def rows_of(page, tol=3.0):
    """Cluster page words into visual rows keyed by top coordinate."""
    buckets = defaultdict(list)
    for w in page.extract_words(use_text_flow=False, keep_blank_chars=False):
        key = None
        for k in buckets:
            if abs(k - w['top']) <= tol:
                key = k
                break
        buckets[key if key is not None else w['top']].append(w)
    return [(top, sorted(ws, key=lambda w: w['x0']))
            for top, ws in sorted(buckets.items())]


def parse_header(page, doc_text=''):
    """Read the label/value grid on page 1 (GL account, WBS, fund, etc.)."""
    out = {}
    rws = rows_of(page)
    flat = [(top, ' '.join(w['text'] for w in ws), ws) for top, ws in rws]
    text = '\n'.join(t for _, t, _ in flat) + '\n' + doc_text

    m = re.search(r'ORDER NO\.\s*(\d+)', text)
    out['po_number'] = m.group(1) if m else None
    m = re.search(r'Issued on\s+' + DATE_PAT, text)
    out['issued_date'] = norm_date(m.group(1)) if m else None
    m = re.search(r'Created on\s+' + DATE_PAT + r'\s*\w*\s*by\s+(.+)', text)
    if m:
        out['created_date'] = norm_date(m.group(1))
        out['created_by'] = m.group(2).strip()
    m = re.search(r'Requisition ID:\s*(PR\d+)', text)
    out['requisition'] = m.group(1) if m else None
    m = re.search(r'TOTAL AMOUNT\s*\$?([\d,]+\.\d{2})\s*([A-Z]{3})', text)
    if not m:
        m = re.search(r'TOTAL AMOUNT\s*\n\s*\$?([\d,]+\.\d{2})\s*([A-Z]{3})', text)
    if m:
        out['po_total'] = float(m.group(1).replace(',', ''))
        out['currency'] = m.group(2)

    # The page has two address columns side by side, so page-level text merges
    # them ("SUPPLIER: TOTAL AMOUNT"). Read the left column on its own.
    left = [' '.join(w['text'] for w in ws if w['x0'] < 235)
            for _, ws in rws]
    left = [l.strip() for l in left]

    def block_after(start_pred, stop_pred):
        try:
            i = next(k for k, t in enumerate(left) if start_pred(t))
        except StopIteration:
            return []
        acc = []
        for t in left[i + 1:]:
            if not t or stop_pred(t):
                break
            acc.append(t)
        return acc

    sup = block_after(lambda t: t == 'SUPPLIER:',
                      lambda t: t.startswith('SHIPTO') or t.startswith('BILL TO'))
    out['supplier'] = sup[0] if sup else None
    out['supplier_address'] = ' | '.join(sup[1:]) or None
    rec = block_after(lambda t: t.startswith('RECEIVER NAME'),
                      lambda t: t.endswith(':'))
    out['receiver'] = rec[0] if rec else None

    # Two-column field grid: labels at x~41 open a section; x~63 rows are its
    # key/value pairs. Everything below the "GL Account:" label belongs here.
    section, fields = None, defaultdict(dict)
    started = False
    for top, ws in rws:
        first = ws[0]
        txt = ' '.join(w['text'] for w in ws)
        if abs(first['x0'] - LABEL_X) < XTOL and txt.rstrip().endswith(':'):
            section = txt.rstrip(':').strip()
            started = started or section == 'GL Account'
            continue
        if started and section and abs(first['x0'] - SUB_X) < XTOL and ':' in txt:
            k, _, v = txt.partition(':')
            v = v.strip()
            if v and k.strip() not in fields[section]:
                fields[section][k.strip()] = v
    # The label/value grid is not always aligned the same way, so fall back to
    # matching the SAP identifiers directly - their formats are unambiguous.
    def pat(rx, src=text):
        m = re.search(rx, src)
        return m.group(1) if m else None

    out['wbs'] = fields.get('Project/WBS', {}).get('ID')
    out['wbs_description'] = fields.get('Project/WBS', {}).get('Description')
    out['gl_account'] = fields.get('GL Account', {}).get('ID')
    out['gl_name'] = fields.get('GL Account', {}).get('General Ledger Name')
    out['cost_center'] = fields.get('Cost Center', {}).get('ID')
    out['fund'] = fields.get('Fund', {}).get('ID')
    out['funds_center'] = fields.get('Funds Center', {}).get('ID')
    out['functional_area'] = fields.get('Functional Area', {}).get('ID')
    out['grant'] = fields.get('Grant', {}).get('ID')
    out['wbs'] = out['wbs'] or pat(r'ID:\s*(03[A-Z0-9]{12,})')
    out['gl_account'] = out['gl_account'] or pat(r'ID:\s*(00\d{8})')
    out['gl_name'] = out['gl_name'] or pat(r'General Ledger Name:\s*(.+)')
    out['wbs_description'] = out['wbs_description'] or pat(r'Description:\s*(Richard She-\S+)')
    out['fund'] = out['fund'] or pat(r'ID:\s*(G_[A-Z]+)')
    out['funds_center'] = out['funds_center'] or pat(r'ID:\s*(C\d{9})')
    out['functional_area'] = out['functional_area'] or pat(r'ID:\s*(C\d{3})(?!\d)')
    out['grant'] = out['grant'] or pat(r'ID:\s*(NON_GRANT)')
    return out


COLS = [('no', 'NO.'), ('description', 'DESCRIPTION'), ('part_number', 'PART'),
        ('qty', 'QTY'), ('need_by', 'NEED-'), ('unit_price', 'UNIT'),
        ('discount', 'DISCOUNT'), ('net_amount', 'NET'), ('charges', 'CHARGES'),
        ('taxes', 'TAXES'), ('amount', 'AMOUNT'), ('status', 'ORDER')]


# Repeated page furniture (running totals and the fund/grant sidebar) can fall
# between a table header and its data rows when an item straddles a page break.
FURNITURE = re.compile(
    r'^(TOTAL AMOUNT|ID:|Name:|Valid (From|To):|Description:|FM Area:|'
    r'Fiscal Year:|Funds Center:|Functional Area:|Grant:|Grant Type|Sponsor:|'
    r'Award Type|Fund:|General Ledger Name:|Claude is active)')
MONEY_ONLY = re.compile(r'^\$[\d,]+\.\d{2}\s+[A-Z]{3}$')


def find_tables(doc_rows):
    """Yield (anchors, data_rows) for each LINE ITEM header in the row stream."""
    rws = doc_rows
    for idx, (top, ws) in enumerate(rws):
        texts = [w['text'] for w in ws]
        if 'NO.' not in texts or 'DESCRIPTION' not in texts:
            continue
        anchors = {}
        for key, hdr in COLS:
            for w in ws:
                if w['text'] == hdr:
                    anchors[key] = (w['x0'], w['x1'])
                    break
        # A few POs render a narrow table with only NO./DESCRIPTION/PART NUMBER;
        # their amounts are recovered later from the per-line GST block.
        if not {'no', 'description', 'part_number'} <= set(anchors):
            continue
        # Widen each anchor to cover wrapped header words below it (NUMBER, BY,
        # DATE, PRICE, AMOUNT, CONFIRMATION, STATUS) so boundaries land in the gaps.
        for top2, ws2 in rws[idx + 1:idx + 4]:
            names = set(w['text'] for w in ws2)
            if not names <= {'NUMBER', 'BY', 'DATE', 'PRICE', 'AMOUNT',
                             'CONFIRMATION', 'STATUS'}:
                break
            for w in ws2:
                best = min(anchors, key=lambda k: abs(anchors[k][0] - w['x0']))
                if abs(anchors[best][0] - w['x0']) < 6:
                    anchors[best] = (anchors[best][0], max(anchors[best][1], w['x1']))
        # Data rows run until "Full Description:" (or the next header/section).
        data, prev_total = [], False
        for top2, ws2 in rws[idx + 1:]:
            line = ' '.join(w['text'] for w in ws2)
            if (line.startswith('Full Description:') or line.startswith('TAX CODE')
                    or line.startswith('TERMS ') or line.startswith('Req. Line No.')):
                break
            # skip the wrapped header continuation lines
            if set(w['text'] for w in ws2) <= {'NUMBER', 'BY', 'DATE', 'PRICE',
                                               'AMOUNT', 'CONFIRMATION', 'STATUS'}:
                continue
            if FURNITURE.match(line):
                prev_total = line.startswith('TOTAL AMOUNT')
                continue
            if prev_total and MONEY_ONLY.match(line):
                prev_total = False
                continue
            prev_total = False
            data.append(ws2)
        yield anchors, data


def assign_columns(anchors, data_rows):
    """Bucket words into columns using midpoints between header x-anchors."""
    keys = [k for k, _ in COLS if k in anchors]
    xs = [anchors[k] for k in keys]
    cuts = [(xs[i][1] + xs[i + 1][0]) / 2 for i in range(len(xs) - 1)]
    bounds = [(-1e9 if i == 0 else cuts[i - 1],
               1e9 if i == len(xs) - 1 else cuts[i])
              for i in range(len(xs))]
    cells = defaultdict(list)
    for ws in data_rows:
        for w in ws:
            cx = (w['x0'] + w['x1']) / 2
            for k, (lo, hi) in zip(keys, bounds):
                if lo <= cx < hi:
                    cells[k].append(w['text'])
                    break
    return {k: ' '.join(v) for k, v in cells.items()}


def money(s):
    if not s:
        return None
    m = MONEY.search(s)
    return float(m.group(1).replace(',', '')) if m else None


def parse_po(path):
    with pdfplumber.open(path) as pdf:
        raw = '\n'.join((p.extract_text() or '') for p in pdf.pages)
        hdr = parse_header(pdf.pages[0], raw)
        doc_rows = []
        for page in pdf.pages:
            doc_rows.extend(rows_of(page))
        items = []
        for anchors, data in find_tables(doc_rows):
                if not data:
                    continue
                c = assign_columns(anchors, data)
                no = (c.get('no') or '').strip()
                if not no.isdigit():
                    continue
                qty_txt = (c.get('qty') or '').strip()
                qm = re.match(r'([\d,.]+)\s*', qty_txt)
                UOM = (r'\b(each|EA|pack|PAC|box|BX|unit|set|lot|case|kit|AU|'
                       r'hour|day|litre|kg|g|mL|L)\b')
                um = re.search(UOM, qty_txt, re.I)
                spill = re.sub(r'([\d,.]+)|' + UOM, '', qty_txt, flags=re.I).strip()
                if spill:  # date text that bled in from the NEED-BY column
                    c['need_by'] = (spill + ' ' + (c.get('need_by') or '')).strip()
                items.append({
                    'line_no': int(no),
                    'description': re.sub(r'\s+', ' ', c.get('description', '')).strip(),
                    'part_number': re.sub(r'\s+', '', c.get('part_number', '')).strip(),
                    'qty': float(qm.group(1).replace(',', '')) if qm else None,
                    'uom': um.group(1) if um else None,
                    'need_by': norm_date(re.sub(r'-\s+', '-',
                                        re.sub(r'\s+', ' ', c.get('need_by', '')))
                                         .replace('SGT', '').strip()),
                    'unit_price': money(c.get('unit_price')),
                    'discount': money(c.get('discount')),
                    'net_amount': money(c.get('net_amount')),
                    'charges': money(c.get('charges')),
                    'taxes': money(c.get('taxes')),
                    'amount': money(c.get('amount')),
                    'status': re.sub(r'\s+', ' ', c.get('status', '')).strip(),
                })
    # attach Full Description text per line number
    fulls, prods = {}, {}
    STOP = re.compile(r'^\s*$|^NO\.\s|^TERMS |^ATTACHMENT|^Full Description:|'
                      r'^TOTAL AMOUNT|^ID: |^Req\. Line No\.|^TAX CODE|^Valid |^Name: |^Grant')
    lines_raw = raw.split('\n')
    for i, ln in enumerate(lines_raw):
        if ln.startswith('Full Description:'):
            acc = [ln[len('Full Description:'):]]
            for nxt in lines_raw[i + 1:]:
                if STOP.match(nxt):
                    break
                acc.append(nxt)
            pending_full = re.sub(r'\s+', ' ', ' '.join(acc)).strip()
            # the matching Req. Line No. is the next one below this block
            for nxt in lines_raw[i + 1:]:
                m = re.match(r'Req\. Line No\.:\s*(\d+)', nxt)
                if m:
                    fulls[int(m.group(1))] = pending_full
                    break
        m = re.match(r'Product Name:\s*(.*)', ln)
        if m:
            acc = [m.group(1)]
            for nxt in lines_raw[i + 1:]:
                if STOP.match(nxt):
                    break
                acc.append(nxt)
            for prev in reversed(lines_raw[:i]):
                mm = re.match(r'Req\. Line No\.:\s*(\d+)', prev)
                if mm:
                    prods[int(mm.group(1))] = re.sub(r'\s+', ' ', ' '.join(acc)).strip()
                    break
    for it in items:
        it['full_description'] = fulls.get(it['line_no'])
        it['product_name'] = prods.get(it['line_no'])
        it['amount_source'] = 'po_table'
    # dedupe by line_no (headers can repeat across page breaks)
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: x['line_no']):
        if it['line_no'] in seen:
            continue
        seen.add(it['line_no'])
        uniq.append(it)
    # Some POs render a narrow table with no price columns at all; recover the
    # amounts from each line's GST block (tax = rate x net).
    taxes = {}
    for m in re.finditer(r'Req\. Line No\.:\s*(\d+)', raw):
        pass
    blocks = re.split(r'(?=Full Description:)', raw)
    for b in blocks:
        mn = re.search(r'Req\. Line No\.:\s*(\d+)', b)
        mr = re.search(r'([\d.]+)%', b)
        ma = re.findall(r'\$([\d,]+\.\d{2})\s*SGD', b)
        if mn and mr and ma:
            taxes[int(mn.group(1))] = (float(mr.group(1)) / 100.0,
                                       float(ma[0].replace(',', '')))
    for it in uniq:
        if it['amount'] is None and it['line_no'] in taxes:
            rate, tax = taxes[it['line_no']]
            if rate > 0:
                net = round(tax / rate, 2)
                it['net_amount'] = net
                it['taxes'] = tax
                it['amount'] = round(net + tax, 2)
                it['unit_price'] = net / it['qty'] if it.get('qty') else None
                it['amount_source'] = 'derived_from_gst'

    # Last resort: if a single line is still missing its amount, it is the
    # residual between the PO total and the lines we did read.
    blank = [i for i in uniq if i['amount'] is None]
    if len(blank) == 1 and hdr.get('po_total') is not None:
        known = sum(i['amount'] for i in uniq if i['amount'] is not None)
        resid = round(hdr['po_total'] - known, 2)
        if resid > 0:
            it = blank[0]
            it['amount'] = resid
            it['taxes'] = it['taxes'] if it['taxes'] is not None else None
            it['net_amount'] = it['net_amount'] if it['net_amount'] is not None else None
            it['amount_source'] = 'derived_residual'

    m = re.search(r'LINE ITEM DETAILS\s*\((\d+)\s*LINE ITEMS?\s*\)', raw)
    hdr['declared_line_count'] = int(m.group(1)) if m else None
    return hdr, uniq


if __name__ == '__main__':
    h, its = parse_po(sys.argv[1])
    print(json.dumps(h, indent=1))
    for it in its:
        print(it)
