"""Fallback parser for POs saved as an Ariba order-detail screen print.

These lack the standard PO layout (and the accounting block entirely), but carry
the order id, supplier, requisition and a single line-item row.
"""
import re
import pymupdf


def parse_screenprint(path):
    raw = "\n".join(p.get_text() for p in pymupdf.open(path))
    flat = re.sub(r'\s+', ' ', raw)
    hdr = {'source_pdf': path.split('/')[-1], 'layout': 'ariba_screen_print'}

    def grab(pat, group=1, src=flat):
        m = re.search(pat, src)
        return m.group(group).strip() if m else None

    hdr['po_number'] = grab(r'Order ID:\s*(\d+)')
    hdr['supplier'] = grab(r'Supplier:\s*(.*?)\s*Contact:')
    hdr['title'] = grab(r'Title:\s*(.*?)\s*Purchasing Unit:')
    hdr['functional_area'] = grab(r'Purchasing Unit:\s*(\S+)')
    hdr['requisition'] = grab(r'(PR\d{6})')
    hdr['currency'] = 'SGD'
    hdr['created_by'] = grab(r'DOA Approver:\s*(\S+)')

    # Money figures in the single line-item row, in printed order:
    # price, net amount, taxes, amount
    amts = [float(x.replace(',', ''))
            for x in re.findall(r'\$([\d,]+\.\d{2}) SGD', flat)]
    qty = grab(r'PR\d+(\d+)\s*each')
    desc = grab(r'PR\d+\d+\s*each\s*(.*?)\s*\d{6,}\s*\$')
    part = grab(r'PR\d+\d+\s*each\s*.*?\s(\d{6,})\s*\$')
    item = {
        'line_no': 1,
        'description': desc,
        'product_name': desc,
        'full_description': hdr.get('title'),
        'part_number': part,
        'qty': float(qty) if qty else None,
        'uom': 'each',
        'need_by': None,
        'unit_price': amts[0] if len(amts) > 0 else None,
        'discount': None,
        'net_amount': amts[1] if len(amts) > 1 else None,
        'charges': None,
        'taxes': amts[2] if len(amts) > 2 else None,
        'amount': amts[3] if len(amts) > 3 else None,
        'status': grab(r'Order Confirmation Status:\s*(\w+)'),
        'amount_source': 'ariba_screen_print',
    }
    hdr['po_total'] = item['amount']
    hdr['declared_line_count'] = 1
    m = re.search(r'(\d+)\s*Line Item', flat)
    if m:
        hdr['declared_line_count'] = int(m.group(1))
    return hdr, [item]


if __name__ == '__main__':
    import sys, json
    h, i = parse_screenprint(sys.argv[1])
    print(json.dumps(h, indent=1)); print(json.dumps(i, indent=1))
