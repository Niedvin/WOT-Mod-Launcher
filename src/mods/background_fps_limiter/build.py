from __future__ import print_function
import hashlib
import os
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scratch/background_fps'
CONFIGS = ROOT / 'mods/configs/background_fps_limiter'
PY27 = ROOT / 'py27_dist/python.exe'
VERSION = '1.0.3'
MOD_NAME = 'ua.background_fps_limiter_%s.wotmod' % VERSION


VENDOR_FILES = ('_ua_window_focus.pyd',)
ENTRY = 'res/scripts/client/gui/mods/mod_background_fps_limiter.pyc'
META = ('<root><id>ua.background_fps_limiter</id><version>%s</version><name>Background FPS Limiter</name>'
        '<description>Limits client frame rate while the window is not focused to cut idle GPU and CPU load.</description></root>') % VERSION


def get_game_version():
    vxml = ROOT / 'version.xml'
    if vxml.exists():
        m = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', vxml.read_text(encoding='utf-8'))
        if m:
            return m.group(1)
    return '2.4.1.0'


def build():
    if b'worldoftanks.exe' in subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH']).lower():
        raise RuntimeError('Live installation waits for game exit')
    CONFIGS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE / 'mod_background_fps_limiter.py', CONFIGS / 'mod_background_fps_limiter.py')
    for vendor_name in VENDOR_FILES:
        shutil.copy2(SOURCE / 'vendor' / vendor_name, CONFIGS / vendor_name)
    subprocess.check_call([str(PY27), '-m', 'py_compile', str(CONFIGS / 'mod_background_fps_limiter.py')])
    pyc = (CONFIGS / 'mod_background_fps_limiter.pyc').read_bytes()
    assert struct.unpack('<H', pyc[:2])[0] == 62211
    temporary = SOURCE / (MOD_NAME + '.tmp')
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('meta.xml', META)
        archive.writestr(ENTRY, pyc)
        archive.write(SOURCE / 'vendor/_ua_window_focus.pyd', 'res/ua_mod_payloads/background_fps_limiter/_ua_window_focus.pyd')
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        assert archive.read(ENTRY) == pyc
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
    target = SOURCE / MOD_NAME
    os.replace(temporary, target)
    ver = get_game_version()
    destinations = [ROOT / 'build/mods' / ver / MOD_NAME, ROOT / 'mods' / ver / MOD_NAME]
    for path in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, path)
    print('PACKAGE', target)
    print('SHA256', hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
