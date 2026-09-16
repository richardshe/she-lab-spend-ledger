"""Inline data.js into the dashboard to produce one self-contained HTML file.

The two-file version is what gets published as an Artifact; this single-file
build is the one to hand to a colleague - it opens by double-clicking, with no
server and no second file to keep alongside it.
"""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, '..', 'dashboard')

html = open(os.path.join(DASH, 'ledger.html')).read()
data = open(os.path.join(DASH, 'data.js')).read()

if '<script src="data.js"></script>' not in html:
    raise SystemExit('expected <script src="data.js"></script> in ledger.html')

# A standalone file needs the document scaffolding the Artifact runtime supplies.
head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="robots" content="noindex, nofollow, noarchive">\n'
        '<style>:root{color-scheme:light}body{margin:0}'
        'img{max-width:100%}[hidden]{display:none!important}</style>\n')
body = html.replace('<script src="data.js"></script>',
                    '<script>\n' + data + '\n</script>')
# the <title> and <style> block belong in the head; the rest is the body
m = re.match(r'(\s*<title>.*?</title>\s*)', body, re.S)
title = m.group(1) if m else '<title>She Lab Spend Ledger</title>'
if m:
    body = body[m.end():]
out = head + title + '</head>\n<body>\n' + body + '\n</body>\n</html>\n'

for path in (os.path.join(DASH, 'she-lab-spend-ledger.html'),
             os.path.join(HERE, '..', 'index.html')):   # index.html = GitHub Pages entry
    open(path, 'w').write(out)
    print(f'{os.path.normpath(path)}: {os.path.getsize(path)/1024:.0f} KB (self-contained)')
