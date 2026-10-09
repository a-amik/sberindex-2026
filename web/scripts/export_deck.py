"""Слайды чистовой презентации — в сервис, без рамки (iframe).

Из папки листа (slides.html, оболочка collaboration, шрифты, картинки) собирает
public/about/live/: deck.html — только экраны, deck.css — их стили для теневого
узла страницы (:root → :host, без режима показа и тёмной темы оболочки),
deck-fonts.css — шрифты (в теневом узле @font-face не работает), assets/ и fonts/.

    python3 web/scripts/export_deck.py ~/Agent-AI/amik-am-2025-sberindex/collaboration/sberindex-2026/fx6n2zvmfmf1ak91
"""
import re
import shutil
import sys
from pathlib import Path

SRC = Path(sys.argv[1]).expanduser()
SHELL = SRC.parent.parent  # collaboration/
OUT = Path(__file__).resolve().parent.parent / 'public' / 'about' / 'live'
URL = '/about/live/'


def blocks(css):
    """Верхний уровень CSS: (заголовок, тело) с учётом вложенных скобок."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find('{', i)
        if j < 0:
            break
        head, depth, k = css[i:j].strip(), 1, j + 1
        while k < n and depth:
            depth += {'{': 1, '}': -1}.get(css[k], 0)
            k += 1
        out.append((head, css[j + 1:k - 1]))
        i = k
    return out


DARK = re.compile(r'data-theme="?dark"?')


def selector(sel):
    s = sel.strip()
    if DARK.search(s) or re.search(r'\bhtml\.(show|printing|reader|turn|idle)', s):
        return None
    s = re.sub(r':root(\[data-theme="?light"?\])?', ':host', s)
    s = re.sub(r'^html\b(\[[^\]]*\])?', ':host', s)
    s = re.sub(r'(^|[\s>,])body\b', r'\1.deck-body', s)
    s = s.replace(':host .deck-body', '.deck-body')
    return s


def rewrite(css, fonts):
    out = []
    for head, body in blocks(css):
        if head.startswith('@font-face'):
            fonts.append('@font-face{' + body.replace('url(fonts/', f'url({URL}fonts/') + '}')
        elif head.startswith('@media') or head.startswith('@supports'):
            if 'prefers-color-scheme: dark' in head or 'print' in head:
                continue
            inner = rewrite(body, fonts)
            if inner.strip():
                out.append(f'{head}{{{inner}}}')
        elif head.startswith('@'):
            out.append(f'{head}{{{body}}}')
        else:
            sels = [x for x in (selector(p) for p in head.split(',')) if x]
            if sels:
                out.append(', '.join(sels) + '{' + body + '}')
    return '\n'.join(out).replace('url(assets/', f'url({URL}assets/').replace('url("assets/', f'url("{URL}assets/')


page = (SRC / 'slides.html').read_text()
fonts = []
css = rewrite((SHELL / 'doc.css').read_text(), fonts) + '\n' + rewrite((SHELL / 'doc-slides.css').read_text(), fonts)
for st in re.findall(r'<style>(.*?)</style>', page, re.S):
    if 'Встроено в сервис' not in st:
        css += '\n' + rewrite(st, fonts)
slides = re.findall(r'<section class="slide.*?</section>', page, re.S)
html = '\n'.join(slides).replace('src="assets/', f'src="{URL}assets/').replace("url('assets/", f"url('{URL}assets/")

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
shutil.copytree(SRC / 'fonts', OUT / 'fonts')
for f in sorted(set(re.findall(r'assets/[A-Za-z0-9_./-]+\.[a-z0-9]+', page))):
    (OUT / f).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC / f, OUT / f)
(OUT / 'deck.css').write_text(css)
(OUT / 'deck.html').write_text(html)
(OUT / 'deck-fonts.css').write_text('\n'.join(dict.fromkeys(fonts)))
print(f'{len(slides)} слайдов, css {len(css) // 1024} КБ, html {len(html) // 1024} КБ → {OUT}')
