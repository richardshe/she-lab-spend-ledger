"""Rule-based spend taxonomy for the She lab's lab-supply purchases.

Rules are ordered: the first matching pattern wins, so put specific product
families above generic material words. Every row records which rule fired so a
classification can be audited and corrected.
"""
import re

# (category, subcategory, regex) - matched against supplier + description text.
RULES = [
    # --- Sequencing and external services (match before reagents: vendor-led) ---
    ('Sequencing & External Services', 'Whole-plasmid sequencing',
     r'plasmidsaurus|dinocoin'),
    ('Sequencing & External Services', 'NGS library & sequencing',
     r'self-prepared library|premade library|dnbseq|pe150|novogene|\bbgi\b|'
     r'in lane control|aws delivery|library prep|\bwgs\b|mirxes'),
    ('Sequencing & External Services', 'Sanger & other sequencing',
     r'sanger|sequencing service'),

    # --- Nucleic acids: synthesis ---
    ('Oligos & Synthetic DNA', 'CRISPR RNA & Cas protein',
     r'alt-r|sgrna|crrna|tracrrna|cas9 nuclease|cas nuclease|hdr enhancer'),
    ('Oligos & Synthetic DNA', 'Gene fragments & oligo pools',
     r'gblock|g-block|oligo pool|gene fragment|twist|gene synthesis'),
    ('Oligos & Synthetic DNA', 'Plasmids & vectors',
     r'addgene|plasmid dna\b(?!.*kit)|\bplasmid\b(?!.*(kit|prep|mini|maxi))'),
    ('Oligos & Synthetic DNA', 'Primers & oligos',
     r'name:.*sequence:|dna oligo|primer|\boligo\b|hairpin|ultramer|'
     r'genotyping-[fr]\b|barcode'),

    # --- Enzymes and molecular biology ---
    ('Enzymes & Molecular Biology', 'Nucleic acid purification kits',
     r'miniprep|maxiprep|midiprep|zymopure|e\.?z\.?n\.?a|direct-zol|'
     r'rna miniprep|dna/rna shield|magnetic beads for dna|purification kit|'
     r'gel extraction|pcr clean|monarch|isolation kit|extraction kit|'
     r'cleanup kit|clean-?up kit'),
    ('Enzymes & Molecular Biology', 'Polymerases & master mixes',
     r'master ?mix|toughmix|\bkod\b|q5\b|phusion|taq\b|sybr|repliqa|'
     r'gibson|nebuilder|hifi assembl|reverse transcript|superscript'),
    ('Enzymes & Molecular Biology', 'Restriction enzymes & nucleases',
     r'bamh|ecori|xmai|agei|mlui|sbfi|noti|sfii|bsmbi|bsai|bbsi|bspq|bstxi|'
     r'esp3i|paqci|nb\.|nt\.|exonuclease|protelomerase|teln|dnase|rnase|'
     r'ezdnase|- \d[\d,]* units'),
    ('Enzymes & Molecular Biology', 'Ligases, buffers & cofactors',
     r'ligase|nebuffer|\bbuffer\b|nicotinamide adenine|nad\+|\bdntp'),
    ('Enzymes & Molecular Biology', 'Quantification & assay kits',
     r'qubit|assay kit|bradford|\bbca\b|cytofix|cytoperm|staining buffer|'
     r'staining set'),

    # --- Cell culture ---
    ('Cell Culture', 'Transfection & delivery reagents',
     r'lipofectamine|transit|peipro|\bpei\b|fugene|transfection|electroporation'),
    ('Cell Culture', 'Media & supplements',
     r'mtesr|tesr|neurocult|neurobasal|\bb-?27\b|\bn-?2\b|knockout serum|\bksr\b|'
     r'serum replacement|\bdmem\b|\brpmi\b|medium|media\b|\bsm1\b|cloner|'
     r'\bdpbs\b|\bpbs\b|glutamine|opti-?mem|\bg?mem\b|\bhbss\b|pen-?strep|'
     r'\blaminin\b(?=.*media)'),
    ('Cell Culture', 'Matrices & coating',
     r'matrigel|laminin|\bln\d{3}|vitronectin|poly-l-ornithine|poly-d-lysine|'
     r'geltrex|fibronectin|collagen'),
    ('Cell Culture', 'Dissociation & cryopreservation',
     r'accutase|trypsin|tryple|versene|freezing (medium|box)|cryostor|dmso'),
    ('Cell Culture', 'Cell lines & biologicals',
     r'ipsc|kolf2|cell line|hybridoma'),

    # --- Proteins ---
    ('Proteins & Antibodies', 'Antibodies',
     r'antibod(y|ies)|\bmab\b|\bab\b \(|anti-|alexa fluor|polyclonal|monoclonal|'
     r'\bigg\b|hoechst|\bdapi\b|-pe antibody|\b4g11'),
    ('Proteins & Antibodies', 'Growth factors & cytokines',
     r'\bfgf|\bbdnf\b|\bgdnf\b|\begf\b|\bbmp\b|\bshh\b|\bwnt\b|activin|noggin|'
     r'peprotech|recombinant protein|cytokine'),
    ('Proteins & Antibodies', 'Sera & blocking reagents',
     r'\bserum\b(?!.*replacement)|normal (donkey|goat|horse) serum|blocking'),
    ('Proteins & Antibodies', 'Other recombinant proteins',
     r'albumin|recombinant|\bbsa\b'),

    # --- Chemicals ---
    ('Chemicals & Small Molecules', 'Small molecules & inhibitors',
     r'chir99021|\bdapt\b|forskolin|tamoxifen|4-oh|y-?27632|rock inhibitor|'
     r'mirdametinib|h-89|vx-11e|pd0325901|purmorphamine|retinoic acid|'
     r'g-?418|geneticin|puromycin|blasticidin|doxycycline|\bhy-[a-z]?\d'),
    ('Chemicals & Small Molecules', 'General chemicals & salts',
     r'ascorbic|sodium l-lactate|heparin|\bpeg\s?\d|\bnacl\b|\bhepes\b|'
     r'glycerol|ethanol|\bpbs\b|sulphate|sulfate|\bacid\b|solution\b'),
    ('Chemicals & Small Molecules', 'Stains & dyes',
     r'dna stain|\bsybr safe|gelred|ethidium|barrier pen|trypan'),

    ('Facilities & Maintenance', 'Installation, relocation & servicing',
     r'installation|install\b|relocat|site visit|assessment|servicing|'
     r'maintenance|calibration|replacement of'),

    # --- Consumables ---
    ('Lab Consumables & Plastics', 'Pipette tips',
     r'\btips?\b|filter tip'),
    ('Lab Consumables & Plastics', 'Plates, dishes & flasks',
     r'\bplate\b|\bplates\b|multiwell|\bdish|\bflask|ula\b|low attachment|'
     r'chamber slide|\bslide\b'),
    ('Lab Consumables & Plastics', 'Tubes, cuvettes & vials',
     r'\btube|cuvette|\bvial|centrifuge tube|spin-x|\bcolumn'),
    ('Lab Consumables & Plastics', 'Gels & electrophoresis',
     r'\bgel\b|\bgels\b|\btbe\b|agarose|electrophoresis'),
    ('Lab Consumables & Plastics', 'General consumables',
     r'label|lable|applicator|aspiration pipette|parafilm|glove|wipe|foil|'
     r'seal|consumable'),

    # --- Equipment ---
    ('Equipment & Instruments', 'Benchtop instruments',
     r'thermal cycler|\bs1000\b|water (heating )?bath|orbital shaker|'
     r'vacuum pump|centrifuge\b(?!.*tube)|incubator tray|regulator|'
     r'pipettor hanger|hanger|spanner|socket|lamp|bulb|freezer|microscope'),
    ('Equipment & Instruments', 'Equipment parts & accessories',
     r'adaptor|adapter|tubing|cylinder|connector|shelf'),

    # --- Facilities and services ---
    # --- Fees ---
    ('Shipping & Fees', 'Freight & delivery',
     r'freight|shipping|delivery fee|sea freight|airfreight|transport|crating|'
     r'shipping and handling'),
    ('Shipping & Fees', 'Admin & handling charges',
     r'admin charge|handling|surcharge|service charge'),
]

COMPILED = [(c, s, re.compile(p, re.I)) for c, s, p in RULES]

# Supplier-level defaults for orders whose description is just a vendor nickname
# ("biobasic", "nest", "Kyberlife") and carries no product information.
SUPPLIER_DEFAULT = {
    'INTEGRATED DNA TECHNOLOGIES': ('Oligos & Synthetic DNA', 'Primers & oligos'),
    'Wuxi NEST Biotechnology Co., Ltd.': ('Lab Consumables & Plastics', 'General consumables'),
    'BIO BASIC ASIA PACIFIC PTE. LTD.': ('Enzymes & Molecular Biology', 'General reagent (unspecified)'),
    'Plasmidsaurus Inc.': ('Sequencing & External Services', 'Whole-plasmid sequencing'),
    'STEMCELL TECHNOLOGIES SINGAPORE': ('Cell Culture', 'Media & supplements'),
    'STEM CELL SOCIETY SINGAPORE': ('Cell Culture', 'Media & supplements'),
    'Life Technologies Holdings Pte Ltd': ('Enzymes & Molecular Biology', 'General reagent (unspecified)'),
    'NEW ENGLAND BIOLABS PTE LTD': ('Enzymes & Molecular Biology', 'Restriction enzymes & nucleases'),
    'Twist Bioscience Corporation': ('Oligos & Synthetic DNA', 'Gene fragments & oligo pools'),
    'Addgene Inc.': ('Oligos & Synthetic DNA', 'Plasmids & vectors'),
    'TTM SCIENTIFIC SUPPLY PTE LTD': ('Lab Consumables & Plastics', 'General consumables'),
    'KYBERLIFE PTE LTD': ('Lab Consumables & Plastics', 'General consumables'),
    'SINGLAB TECHNOLOGIES PTE LTD': ('Proteins & Antibodies', 'Antibodies'),
    'PROBIOSCIENCE TECHNOLOGIES': ('Chemicals & Small Molecules', 'Small molecules & inhibitors'),
    'Innovative Cell Technologies, Inc': ('Cell Culture', 'Dissociation & cryopreservation'),
    'The Jackson Laboratory.': ('Cell Culture', 'Cell lines & biologicals'),
    'VAZYME BIOTECHNOLOGY SINGAPORE PTE': ('Enzymes & Molecular Biology',
                                           'General reagent (unspecified)'),
    'GA International INC.': ('Lab Consumables & Plastics', 'General consumables'),
}

# Manual overrides, keyed by (po_number, line_no), for orders whose PO text is
# just a vendor nickname. Resolved by reading the attached quote; edit this table
# to correct any classification without touching the rules.
OVERRIDES = {
    ('9100291470', 1): ('Enzymes & Molecular Biology', 'Nucleic acid purification kits',
                        'manual: quote lists FastPure Gel DNA Extraction + Plasmid Mini kits'),
}


def categorize(item, supplier, po_title='', gl_account='', po_number=None):
    """Return (category, subcategory, rule_used).

    The item's own text is matched first; the requisition title is only consulted
    when the item text matches nothing, since a PR title describes the order as a
    whole and would otherwise mislabel its freight and admin lines.
    """
    if (po_number, item.get('line_no')) in OVERRIDES:
        return OVERRIDES[(po_number, item.get('line_no'))]
    item_text = ' '.join(filter(None, [
        item.get('product_name'), item.get('description'),
        item.get('full_description')]))
    for text, tag in ((item_text, 'kw'), (po_title, 'title')):
        if not text:
            continue
        for cat, sub, rx in COMPILED:
            m = rx.search(text)
            if m:
                return (cat, sub, f'{tag}:{m.group(0).lower()[:28]}')
    if supplier in SUPPLIER_DEFAULT:
        cat, sub = SUPPLIER_DEFAULT[supplier]
        return (cat, sub, 'supplier-default')
    return ('Uncategorised', 'Needs review', 'none')


# Trading names differ from the legal entity on the PO; group them so vendor
# analysis reflects the actual manufacturer/brand.
VENDOR_GROUP = {
    'Life Technologies Holdings Pte Ltd': 'Thermo Fisher Scientific',
    'Sigma-Aldrich Pte Ltd': 'Merck / Sigma-Aldrich',
    'INTEGRATED DNA TECHNOLOGIES': 'IDT',
    'NEW ENGLAND BIOLABS PTE LTD': 'NEB',
    'STEMCELL TECHNOLOGIES SINGAPORE': 'STEMCELL Technologies',
    'STEM CELL SOCIETY SINGAPORE': 'Stem Cell Society Singapore',
    'Wuxi NEST Biotechnology Co., Ltd.': 'NEST Biotechnology',
    'BGI TECH SOLUTIONS (HONG KONG)': 'BGI',
    'Bio-Rad Laboratories (Singapore) Pte Ltd': 'Bio-Rad',
    'The Jackson Laboratory.': 'Jackson Laboratory',
    'Twist Bioscience Corporation': 'Twist Bioscience',
    'Plasmidsaurus Inc.': 'Plasmidsaurus',
    'Addgene Inc.': 'Addgene',
    'ABCAM SINGAPORE PTE. LTD.': 'Abcam',
    'SARTORIUS STEDIM SINGAPORE PTE.': 'Sartorius',
    'ZUELLIG PHARMA PTE. LTD.': 'Zuellig Pharma',
    'DEVELOPMENTAL STUDIES HYBRIDOMA BANK': 'DSHB',
    'Innovative Cell Technologies, Inc': 'Innovative Cell Technologies',
    'BOSTON BIOPRODUCTS, INC': 'Boston BioProducts',
    'HAOYUAN CHEMEXPRESS CO LIMITED': 'MedChemExpress (HaoYuan)',
    'PROBIOSCIENCE TECHNOLOGIES': 'ProBioScience',
    'GA International INC.': 'GA International',
}


def vendor_group(supplier):
    if not supplier:
        return 'Unknown'
    if supplier in VENDOR_GROUP:
        return VENDOR_GROUP[supplier]
    # strip Singapore corporate suffixes for a readable display name
    s = re.sub(r'\s*\b(PTE\.?|LTD\.?|LIMITED|INC\.?|CO\.?|CORPORATION|'
               r'\(S\)|\(SINGAPORE\)|SINGAPORE|HOLDINGS)\b\.?', '', supplier,
               flags=re.I)
    return re.sub(r'[\s,.]+$', '', s).strip() or supplier
