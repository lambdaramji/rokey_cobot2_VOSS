"""Export the Archify-produced inline SVG to standalone SVG and PNG.

Run after finalize: python3 renderer-extension/export_assets.py from docs/architecture.
PNG is a Chrome screenshot of the renderer SVG, not a native Viewer download.
"""
from pathlib import Path
import re
from bs4 import BeautifulSoup
import subprocess, tempfile
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
for stem in ('01_system', '02_ros2', '03_erd', '04_flow'):
    doc = BeautifulSoup((ROOT / f'{stem}.html').read_text(), 'html.parser')
    svg = doc.find('svg', attrs={'role': 'img'})
    if svg is None:
        raise RuntimeError(f'{stem}: Archify diagram SVG missing')
    viewbox = svg.get('viewbox') or svg.get('viewBox')
    _, _, w, h = map(float, viewbox.split())
    css = '\n'.join(s.get_text() for s in doc.find_all('style'))
    dark = re.search(r'\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S)
    variables = dict(re.findall(r'(--[\w-]+)\s*:\s*([^;]+);', dark.group(1))) if dark else {}
    def resolve(text):
        return re.sub(r'var\((--[\w-]+)(?:,[^)]*)?\)', lambda m: variables.get(m.group(1), '#94a3b8'), text)
    svg['xmlns'] = 'http://www.w3.org/2000/svg'
    svg['width'] = str(int(w))
    svg['height'] = str(int(h))
    svg['viewBox'] = viewbox
    svg['data-theme'] = 'dark'
    svg.attrs.pop('viewbox', None)
    style = doc.new_tag('style')
    style.string = resolve(css) + "\ntext{font-family:'Noto Sans CJK KR',sans-serif}"
    svg.insert(0, style)
    bg = doc.new_tag('rect', attrs={'width':'100%', 'height':'100%', 'fill':'#020617'})
    svg.insert(1, bg)
    raw = str(svg)
    raw = re.sub(r'<style>(.*?)</style>', lambda m: '<style><![CDATA['+m.group(1)+']]></style>', raw, flags=re.S)
    for a,b in {'viewbox':'viewBox','markerunits':'markerUnits','markerwidth':'markerWidth','markerheight':'markerHeight','refx':'refX','refy':'refY','preserveaspectratio':'preserveAspectRatio','gradientunits':'gradientUnits','patternunits':'patternUnits'}.items():
        raw = re.sub(r'\b'+a+r'=',b+'=',raw)
    for a,b in [('lineargradient','linearGradient'),('radialgradient','radialGradient'),('clippath','clipPath')]:
        raw = re.sub(r'(<\/?)(%s)(\s|>)'%a, r'\1'+b+r'\3', raw)
    raw = resolve(raw)
    (ROOT / f'{stem}.svg').write_text('<?xml version="1.0" encoding="UTF-8"?>\n'+raw)
    path = ROOT / f'{stem}.png'
    with tempfile.TemporaryDirectory() as td:
        shot = Path(td) / 'shot.png'
        cmd = ['google-chrome', '--headless=new', '--no-sandbox', '--disable-gpu',
               '--hide-scrollbars', f'--window-size={int(w)},{int(h)}',
               f'--screenshot={shot}', (ROOT / f'{stem}.svg').as_uri()]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with Image.open(shot) as im:
            im.crop((0, 0, int(w), int(h))).save(path)
    with Image.open(path) as im:
        im.load()
        assert im.size == (int(w), int(h))
    print(stem, int(w), int(h), path.stat().st_size)
