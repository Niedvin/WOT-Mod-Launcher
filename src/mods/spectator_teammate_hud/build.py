from __future__ import print_function
import ast
from datetime import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scratch/spectator_hud'
PY27 = ROOT / 'py27_dist/python.exe'
VERSION = '1.0.6'
MOD_NAME = 'ua.spectator_teammate_hud_%s.wotmod' % VERSION
ENTRY = 'res/scripts/client/gui/mods/mod_spectator_teammate_hud.pyc'
STAGING = ROOT / 'staging_modpack/Mods/07_Spectator_Teammate_HUD'


def get_game_version():
    vxml = ROOT / 'version.xml'
    if vxml.exists():
        m = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', vxml.read_text(encoding='utf-8'))
        if m:
            return m.group(1)
    return '2.4.1.0'


def source_consistency():
    main = ast.parse((SOURCE / 'mod_spectator_teammate_hud.py').read_text(encoding='utf-8'))
    classes = {node.name: ast.dump(node, include_attributes=False) for node in main.body if isinstance(node, ast.ClassDef)}
    for filename, name in [('teammate_tracker.py', 'TeammateTracker'), ('hud_adapter.py', 'SpectatorHudAdapter'), ('spectator_aim.py', 'SpectatorAimManager')]:
        module = ast.parse((SOURCE / filename).read_text(encoding='utf-8'))
        node = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name)
        assert classes[name] == ast.dump(node, include_attributes=False), filename + ' differs from installed source'


def build():
    source_consistency()
    if '--run-tests' in sys.argv:
        subprocess.check_call([str(PY27), '-B', '-m', 'unittest', 'discover', '-s', str(SOURCE), '-p', 'test_*.py'], cwd=str(ROOT))
        for name in ['test_tracker.py', 'test_mod_integration.py']:
            subprocess.check_call([str(PY27), str(SOURCE / name)], cwd=str(ROOT))
    subprocess.check_call([str(PY27), '-m', 'py_compile', str(SOURCE / 'mod_spectator_teammate_hud.py')])
    pyc = (SOURCE / 'mod_spectator_teammate_hud.pyc').read_bytes()
    assert struct.unpack('<H', pyc[:2])[0] == 62211
    temporary = SOURCE / (MOD_NAME + '.tmp')
    meta = '<root><id>ua.spectator_teammate_hud</id><version>%s</version><name>Spectator Teammate HUD</name><description>Observed tank aim, penetration for known shells, received reload and equipment countdowns.</description></root>' % VERSION
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('meta.xml', meta)
        archive.writestr(ENTRY, pyc)
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        assert archive.read(ENTRY) == pyc
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
    target = SOURCE / MOD_NAME
    os.replace(temporary, target)
    destinations = [ROOT / 'build/mods' / get_game_version() / MOD_NAME, STAGING / 'game_files/mods/_VERSION_' / MOD_NAME]
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, path)
    info_path = STAGING / 'info.json'
    info = json.loads(info_path.read_text(encoding='utf-8-sig'))
    info['version'] = VERSION
    backup = ROOT / '.backups' / ('spectator-build-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    for label, directory in [('build', destinations[0].parent), ('staging', destinations[1].parent)]:
        for old in directory.glob('ua.spectator_teammate_hud_*.wotmod'):
            if old.name != MOD_NAME:
                saved = backup / label / old.name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old, saved)
                assert saved.read_bytes() == old.read_bytes()
                old.unlink()
    info['size_bytes'] = sum(path.stat().st_size for path in (STAGING / 'game_files').rglob('*') if path.is_file())
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    print('PACKAGE', target)
    print('SHA256', hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
    if '--install' in sys.argv:
        subprocess.check_call([sys.executable, str(SOURCE / 'deploy.py')])
