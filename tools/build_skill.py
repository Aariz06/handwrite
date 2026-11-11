#!/usr/bin/env python3
"""Assemble handwrite/SKILL.md from src/SKILL.template.md and the two scripts in src/.

  python3 tools/build_skill.py           write handwrite/SKILL.md
  python3 tools/build_skill.py --check   exit 1 if handwrite/SKILL.md is out of date
  python3 tools/build_skill.py --zip     also write dist/handwrite-skill-v<VERSION>.zip

Edit the files in src/, never handwrite/SKILL.md directly.
"""
import os, re, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')
OUT = os.path.join(ROOT, 'handwrite', 'SKILL.md')


def read(name):
    with open(os.path.join(SRC, name), encoding='utf-8') as f:
        return f.read().rstrip('\n')


def build():
    md = read('SKILL.template.md')
    for token, name in (('@@FONT@@', 'hw_font.py'), ('@@DOC@@', 'hw_doc.py')):
        assert md.count(token) == 1, f'{token} must appear exactly once in SKILL.template.md'
        md = md.replace(token, read(name))
    md += '\n'
    # the skill extracts its scripts with this regex: make sure it returns them unchanged
    found = dict(re.findall(r'<!-- file: (\S+) -->\n```python\n(.*?)\n```', md, re.S))
    for name in ('hw_font.py', 'hw_doc.py'):
        assert found.get(name) == read(name), f'{name} does not round-trip through SKILL.md'
    return md


def main():
    md = build()
    if '--check' in sys.argv:
        current = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
        if current != md:
            sys.exit('handwrite/SKILL.md is out of date: run python3 tools/build_skill.py')
        print('handwrite/SKILL.md is up to date')
        return
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(md)
    print('wrote', os.path.relpath(OUT, ROOT))
    if '--zip' in sys.argv:
        version = open(os.path.join(ROOT, 'VERSION')).read().strip()
        os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
        z = os.path.join(ROOT, 'dist', f'handwrite-skill-v{version}.zip')
        with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(OUT, 'handwrite/SKILL.md')
        print('wrote', os.path.relpath(z, ROOT))


if __name__ == '__main__':
    main()
