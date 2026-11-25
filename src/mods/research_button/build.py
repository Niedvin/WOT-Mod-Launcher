import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile
from mono_build import build as build_mono, game_version, MEMBER, ROOT

WORK = Path(__file__).resolve().parent
VERSION = '1.2.7'
MOD_ID = 'ua.research_button'
MOD_NAME = '%s_%s.wotmod' % (MOD_ID, VERSION)
ENTRY = 'res/scripts/client/gui/mods/mod_research_button.pyc'
STAGING = ROOT / 'staging_modpack/Mods/09_Research_Button'


def main(install=False):
    if install:
        processes = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH'])
        if b'worldoftanks.exe' in processes.lower():
            raise RuntimeError('Close-game boundary: live installation deferred')
    bundle = build_mono()
    source = WORK / 'mod_research_button.py'
    subprocess.check_call([str(ROOT / 'py27_dist/python.exe'), '-m', 'py_compile', str(source)])
    pyc = source.with_suffix('.pyc').read_bytes()
    assert struct.unpack('<H', pyc[:2])[0] == 62211
    temporary = WORK / (MOD_NAME + '.tmp')
    meta = '<root><id>%s</id><version>%s</version><name>Quick Research</name><description>Immediate Gameface carousel shortcut to vehicle modules.</description></root>' % (MOD_ID, VERSION)
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('meta.xml', meta)
        archive.writestr(ENTRY, pyc)
        archive.writestr('res/ua_mod_payloads/research_button/bundle.js', bundle.read_bytes())
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None and archive.read(ENTRY) == pyc
    package = WORK / MOD_NAME
    os.replace(temporary, package)
    version = game_version()
    destinations = [ROOT / 'build/mods' / version / MOD_NAME, STAGING / 'game_files/mods/_VERSION_' / MOD_NAME]
    if install:
        destinations.append(ROOT / 'mods' / version / MOD_NAME)
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(package, destination)
    for base in [ROOT / 'build/res_mods' / version, STAGING / 'game_files/res_mods/_VERSION_'] + ([ROOT / 'res_mods' / version] if install else []):
        destination = base / MEMBER
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundle, destination)
    live_config = ROOT / 'mods/configs/research_button/config.json'
    config_data = live_config.read_bytes() if live_config.is_file() else b'{"enabled": true}\n'
    for directory in [STAGING / 'game_files/mods/configs/research_button'] + ([live_config.parent] if install else []):
        directory.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, directory / source.name)
        shutil.copy2(source.with_suffix('.pyc'), directory / source.with_suffix('.pyc').name)
        config = directory / 'config.json'
        if config != live_config or not config.exists():
            config.write_bytes(config_data)
    info_path = STAGING / 'info.json'
    metadata = json.loads((WORK / 'mod.json').read_text(encoding='utf-8'))
    info = json.loads(info_path.read_text(encoding='utf-8-sig')) if info_path.is_file() else {}
    for field in ('id', 'title', 'version', 'author', 'description', 'changes', 'default_checked',
                  'manifest_ids', 'clean_patterns', 'clean_res_mods'):
        info[field] = metadata[field]
    info['size_bytes'] = sum(path.stat().st_size for path in (STAGING / 'game_files').rglob('*') if path.is_file())
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    print('PACKAGE', package, 'SHA256', hashlib.sha256(package.read_bytes()).hexdigest())


if __name__ == '__main__':
    main('--install' in sys.argv)
