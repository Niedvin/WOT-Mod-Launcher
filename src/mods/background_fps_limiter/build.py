from __future__ import print_function
import hashlib
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scratch/background_fps'
CONFIGS = ROOT / 'mods/configs/background_fps_limiter'
PY27 = ROOT / 'py27_dist/python.exe'
VERSION = '1.0.7'
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


def build(install=True):
    if install and b'worldoftanks.exe' in subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH']).lower():
        raise RuntimeError('Live installation waits for game exit')
    script = SOURCE / 'mod_background_fps_limiter.py'
    with tempfile.TemporaryDirectory() as temporary_dir:
        compiled = Path(temporary_dir) / 'mod_background_fps_limiter.pyc'
        subprocess.check_call([str(PY27), '-c', 'import py_compile, sys; py_compile.compile(*sys.argv[1:], doraise=True)',
                               str(script), str(compiled), str(CONFIGS / script.name)])
        pyc = compiled.read_bytes()
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
    output = ROOT / 'build/mods' / ver / MOD_NAME
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, output)
    if install:
        live = ROOT / 'mods' / ver / MOD_NAME
        live.parent.mkdir(parents=True, exist_ok=True)
        CONFIGS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(script, CONFIGS / script.name)
        (CONFIGS / 'mod_background_fps_limiter.pyc').write_bytes(pyc)
        for vendor_name in VENDOR_FILES:
            vendor = SOURCE / 'vendor' / vendor_name
            installed = CONFIGS / vendor_name
            if not installed.is_file() or installed.read_bytes() != vendor.read_bytes():
                shutil.copy2(vendor, installed)
        pending = live.with_suffix('.tmp')
        shutil.copy2(target, pending)
        previous_packages = [live.with_name('ua.background_fps_limiter_%s.wotmod' % version) for version in ('1.0.5', '1.0.6')]
        previous_packages = [package for package in previous_packages if package.is_file()]
        backups = []
        try:
            if previous_packages:
                backup_dir = ROOT / '.backups' / datetime.now().strftime('background-fps-%Y%m%d-%H%M%S-%f')
                backup_dir.mkdir(parents=True)
                for previous in previous_packages:
                    backup = backup_dir / previous.name
                    os.replace(previous, backup)
                    backups.append((backup, previous))
            os.replace(pending, live)
        except OSError:
            for backup, previous in reversed(backups):
                os.replace(backup, previous)
            raise
    print('PACKAGE', target)
    print('SHA256', hashlib.sha256(target.read_bytes()).hexdigest())


if __name__ == '__main__':
    build()
