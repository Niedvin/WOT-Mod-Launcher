import json
import math
import re
import struct
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree


SOURCE = Path(__file__).resolve().parent
FILES = {
    '__init__.py': 'ua_bui/__init__.py',
    'layout.py': 'ua_bui/layout.py',
    'modes.py': 'ua_bui/modes.py',
    'overlay.py': 'ua_bui/overlay.py',
    'rating.py': 'ua_bui/rating.py',
    'battle.py': 'ua_bui/battle.py',
    'entry.py': 'mods/mod_bui_customizer.py',
}
PALETTE = {
    'card': (18, 22, 23, 235),
    'allies': (58, 109, 37, 245),
    'enemies': (130, 44, 38, 245),
    'focus': (109, 193, 255, 250),
}
MENU_TEXTURES = ('menu_side.png', 'menu_top.png', 'menu_reset.png')
RATING_VIEW = 'gui/gameface/_dist/production/battle/postmortem_panel/PostmortemPanelView/PostmortemPanelView.html'
RATING_SCRIPT = 'gui/gameface/mods/niedvin/bui/rating.js'
RESIZE_ICONS = {
    'horizontal': (1, 0),
    'vertical': (0, 1),
    'diagonal_down': (1, 1),
    'diagonal_up': (1, -1),
}


def png_chunk(kind, data):
    content = kind + data
    return struct.pack('>I', len(data)) + content + struct.pack('>I', zlib.crc32(content))


def color_texture(rgba):
    return png_texture(2, [bytes(rgba) * 2] * 2)


def png_texture(size, rows):
    return (b'\x89PNG\r\n\x1a\n'
            + png_chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
            + png_chunk(b'IDAT', zlib.compress(b''.join(b'\x00' + row for row in rows)))
            + png_chunk(b'IEND', b''))


def resize_texture(dx, dy):
    radius = 12
    axis_length = math.hypot(dx, dy)
    arrow = set()
    for y in range(-radius, radius + 1):
        for x in range(-radius, radius + 1):
            along = abs(x * dx + y * dy) / axis_length
            across = abs(y * dx - x * dy) / axis_length
            if along <= 10 and (across <= 1.1 or (along >= 5 and across <= 10.8 - along)):
                arrow.add((x, y))
    outline = {(x + u, y + v) for x, y in arrow for u in (-1, 0, 1) for v in (-1, 0, 1)}
    rows = []
    for y in range(-radius, radius + 1):
        row = bytearray()
        for x in range(-radius, radius + 1):
            pixel = (x, y)
            if pixel in arrow:
                row.extend((255, 255, 255, 255))
            elif pixel in outline:
                row.extend((15, 20, 25, 255))
            else:
                row.extend((0, 0, 0, 0))
        rows.append(row)
    return png_texture(2 * radius + 1, rows)


def build(root):
    metadata = json.loads((SOURCE / 'mod.json').read_text(encoding='utf-8'))
    version = re.search(r'v\.(\d+(?:\.\d+){3})', (root / 'version.xml').read_text()).group(1)
    folder = root / 'build' / 'mods' / version
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('{id}_{version}.wotmod'.format(**metadata))
    meta = ElementTree.Element('root')
    for tag, field in (('id', 'id'), ('version', 'version'), ('name', 'title'), ('description', 'description')):
        ElementTree.SubElement(meta, tag).text = metadata[field]
    with tempfile.TemporaryDirectory(dir=folder) as work:
        work = Path(work)
        staged = work / target.name
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('meta.xml', ElementTree.tostring(meta, encoding='utf-8'))
            for name, color in PALETTE.items():
                archive.writestr('res/gui/maps/bui_customizer/' + name + '.png', color_texture(color))
            for name in MENU_TEXTURES:
                archive.write(SOURCE / 'assets' / name, 'res/gui/maps/bui_customizer/' + name)
            for name, direction in RESIZE_ICONS.items():
                archive.writestr('res/gui/maps/bui_customizer/resize_' + name + '.png', resize_texture(*direction))
            with zipfile.ZipFile(root / 'res' / 'packages' / 'gui-part1.pkg') as native:
                rating_html = native.read(RATING_VIEW).decode('utf-8')
            if rating_html.count('</head>') != 1:
                raise ValueError('Unexpected postmortem view markup')
            bridge = '<script defer crossorigin src="coui://' + RATING_SCRIPT + '"></script>'
            archive.writestr('res/' + RATING_VIEW, rating_html.replace('</head>', bridge + '</head>'))
            archive.write(SOURCE / 'rating.js', 'res/' + RATING_SCRIPT)
            for name, destination in FILES.items():
                output = work / (name + 'c')
                resource = 'scripts/client/gui/' + destination
                subprocess.run([
                    str(root / 'py27_dist' / 'python.exe'), '-c',
                    'import py_compile,sys; py_compile.compile(sys.argv[1],sys.argv[2],sys.argv[3],doraise=True)',
                    str(SOURCE / name), str(output), resource,
                ], check=True)
                data = output.read_bytes()
                if data[:4] != b'\x03\xf3\x0d\x0a':
                    raise ValueError('Unexpected game bytecode for ' + name)
                archive.writestr('res/' + resource + 'c', data)
        with zipfile.ZipFile(staged) as archive:
            expected_count = len(FILES) + len(PALETTE) + len(MENU_TEXTURES) + len(RESIZE_ICONS) + 3
            if archive.testzip() is not None or len(archive.namelist()) != expected_count:
                raise ValueError('Corrupt BUI Customizer package')
        staged.replace(target)
    print(target)
    return target


if __name__ == '__main__':
    build(Path.cwd())
