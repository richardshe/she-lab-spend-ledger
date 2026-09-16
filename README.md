# She Lab spend analytics

A pipeline that turns the Ariba purchase-order PDFs in this folder into a
machine-readable spend ledger, plus a dashboard over it.

**Dashboard:** https://richardshe.github.io/she-lab-spend-ledger/
(also published privately as a Claude Artifact: https://claude.ai/artifact/62u5qTriNC5hYcm5iiMYQs)

The published page is `index.html` — a single self-contained file with the data
inlined, so it also works by double-clicking a local copy. It carries a `noindex`
meta tag and the repo serves a `robots.txt` disallowing crawlers, so it is
reachable by link but should not turn up in search results.

**Coverage:** 175 POs / 333 line items, 19 Sep 2025 – 15 Sep 2026.
**Total committed:** S$147,332 gross (incl. 9% GST) · S$138,418 net, at 1.30 USD/SGD.

---

## Layout

```
analytics/                  the backend — plain CSV
  po_line_items.csv         one row per PO line item (333)   <- the main table
  po_orders.csv             one row per PO (175)
  quotes.csv                one row per supplier quote (89)
  denied_requisitions.csv   PRs that never became POs (21)
pipeline/                   the extraction code
  run_all.sh                rebuild everything from the PDFs
index.html                  the published page (self-contained, GitHub Pages entry)
dashboard/                  front-end source
  ledger.html + data.js     two-file version (what the Artifact publishes)
  she-lab-spend-ledger.html single-file build, same as index.html
po_raw.json, quotes_raw.json, payload.json   intermediates
```

## Rebuilding

```bash
pip install -r pipeline/requirements.txt && ./pipeline/run_all.sh
```

`run_all.sh` refreshes the CSVs and `dashboard/data.js`; then
`python3 pipeline/build_standalone.py` rebuilds `index.html`. Commit and push to
update the GitHub Pages site; republish `dashboard/ledger.html` to update the
Artifact.

### A note on personal data

`build_dataset.py` strips the mobile numbers that Ariba embeds in each PO's
`RECEIVER NAME / CONTACT NO` field — the repo is public, and they carry no
analytical value. The source PDFs (gitignored) still contain them, along with
supplier contact details. Keep them out of the repo.

---

## How the PDFs are read

The PO PDFs are text-based, not scanned, and share a stable layout, so
`parse_po.py` extracts words **with their coordinates** and rebuilds the
`LINE ITEM DETAILS` table: words are clustered into visual rows by their `top`
coordinate, then assigned to columns using the x-positions of the table's own
header words. This survives the wrapped, multi-line cells that defeat plain text
extraction (where `KOD One(TM) PCR Master Mix` interleaves with the part number
column).

Three layout variants needed special handling:

| Variant | Count | Handling |
|---|---|---|
| Line item straddling a page break | 6 POs | Header rows and data rows are matched across a document-wide row stream, skipping the repeated fund/grant sidebar that falls between them |
| Narrow table with no price columns printed | 1 PO | Net amount recovered from the line's GST block (`net = tax ÷ rate`) |
| Ariba order-detail screen print instead of a PO | 1 PO (9100316298) | Separate parser; this PO carries no accounting block, so its WBS is blank |

**Every PO reconciles.** The extractor asserts that each PO's parsed line count
matches its declared `(N LINE ITEMS)` and that the line amounts sum to the
printed `TOTAL AMOUNT`. All 175 pass; nothing is estimated away.

Dates are rendered in three different locales across the set — `19-Sep-2025`,
`Wednesday, June 18, 2026`, and the Chinese long form (`星期二, 十月 28, 2025`) —
and are all normalised to ISO.

## Categorisation

`categorize.py` holds an ordered keyword ruleset producing a two-level taxonomy
(10 categories, ~30 subcategories). Every row records the rule that fired
(`category_rule`) and a `category_confidence`:

- **high** — matched the item's own description (326 lines)
- **manual** — resolved by hand from the attached quote, in the `OVERRIDES` table (1)
- **low** — the PO text is only a vendor nickname (`biobasic`, `Kyberlife`, `nest`),
  so the category comes from the supplier (6 lines, S$13.5k)

Item text is matched *before* the requisition title, so an order titled
"BamH1 and Esp3I" doesn't mislabel its freight line as a restriction enzyme.

To correct a classification: edit the rules, or add a `(po_number, line_no)` entry
to `OVERRIDES` in `pipeline/categorize.py`, then re-run.

---

## Caveats worth knowing

**Currency.** 17 POs (US$23,265) are denominated in USD — Plasmidsaurus, Twist,
Addgene, Jackson Laboratory, NEST, Boston BioProducts, MedChemExpress. The PDFs do
not record the rate NTU actually settled at, so the CSV carries the native amount,
the assumed rate (`fx_rate_to_sgd`, default 1.30) and the converted figure in
separate columns. The dashboard has a live rate input — change it there rather than
re-running the pipeline.

**Discounts are not on the POs.** Every `DISCOUNT` cell in every PO is blank, so
`discount_on_po` is 0 throughout. Real discount terms live in the supplier quotes
and are extracted separately into `quotes.csv`: a standing 10% NTU discount from NEB,
a 25% tiered discount on mTeSR from STEMCELL, 20% from Vazyme, 10% from Zymo, and a
Bio-Rad quote with an explicit S$46.00 total discount. These are *narrative* terms
on the quote, not line-level deltas — they tell you the rate obtained, not the
counterfactual list price.

**One PO has no accounting block** (9100316298, S$1,046 IDT Cas9) because it was
saved as a screen print rather than a PO PDF. It shows as *(not stated)* in the WBS
and GL breakdowns. If you know which WBS it hit, it's a one-line fix.

**Two quote PDFs are scanned images** with no text layer and were not parsed:
`9100287823_quote_Quote_SHelf.pdf` and `9100298992_quote_50020558.pdf`. Both POs
themselves parsed fine, so no spend data is missing — only the quote detail.
OCR would need `tesseract`, which isn't installed here.

**One estimated date.** 20 POs print the issue date in a long locale format
(English or Chinese) rather than `19-Sep-2025`; these are parsed exactly. Only the
screen-print PO carries no date at all, and is dated by interpolating between its
numeric neighbours, since Ariba issues PO numbers chronologically. That single row
carries `issue_date_estimated = True` and is tagged `est` in the dashboard.

**Denied requisitions are excluded from every total.** 21 PRs were denied and never
became POs; 8 have quotes attached totalling roughly S$8,517 + US$8,315 of intended
spend. They sit in their own register and their own dashboard panel.

## `po_line_items.csv` schema

| Column | Notes |
|---|---|
| `po_number`, `line_no` | composite key |
| `issue_date`, `fy_month`, `fy_quarter`, `issue_date_estimated` | ISO dates |
| `requisition`, `pr_title` | Ariba PR and its title |
| `supplier`, `vendor` | legal entity on the PO, and its grouped trading name |
| `category`, `subcategory`, `category_rule`, `category_confidence` | the taxonomy |
| `item`, `item_full_description`, `part_number` | product identity |
| `qty`, `uom`, `unit_price` | |
| `currency`, `net_amount`, `tax_amount`, `gross_amount` | as printed, native currency |
| `fx_rate_to_sgd`, `net_amount_sgd`, `gross_amount_sgd` | converted |
| `discount_on_po` | always 0 — see caveats |
| `wbs`, `wbs_suffix`, `wbs_description` | e.g. `03INS002449C220OOE02`, suffix `OOE02` |
| `gl_account`, `gl_name`, `fund`, `funds_center`, `grant` | SAP coding |
| `requester`, `receiver`, `need_by_date`, `po_status` | |
| `quote_files`, `quote_discount_pct`, `quote_discount_amount`, `quote_discount_note` | from the attached quotes |
| `amount_source` | `po_table` (330), `derived_from_gst` (1), `derived_residual` (1), `ariba_screen_print` (1) |
| `po_total`, `source_pdf` | provenance |

### Grant lines in the set

| WBS | POs | What it is |
|---|---|---|
| `03INS002449C220OOE02` | 162 | main other-operating-expenses line |
| `03INS002449C220EQT01` | 5 | equipment |
| `03INS002449C220OOE04` | 3 | |
| `03INS002449C220OOE05` | 2 | |
| `03INS002450C220OOE02` | 2 | second project (…2450) |
| *(not stated)* | 1 | the screen-print PO |
