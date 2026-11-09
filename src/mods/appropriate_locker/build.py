from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
PY27 = ROOT / 'py27_dist/python.exe'
SOURCE = WORK / 'mod_appropriate_locker.py'
ENTRY = 'res/scripts/client/gui/mods/mod_appropriate_locker.pyc'
VERSION = '1.2.2'
PACKAGE = WORK / ('ua.appropriate_locker_%s.wotmod' % VERSION)
BACKUP_DIR = ROOT / '.backups' / 'appropriate_locker'


def run(*arguments):
    result = subprocess.run([str(PY27), '-B'] + list(arguments), cwd=ROOT,
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def backup_file(target, prefix=''):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = BACKUP_DIR / ('%s%s.%s.bak' % (prefix, target.name, stamp))
    backup.write_bytes(target.read_bytes())
    assert backup.exists() and backup.stat().st_size > 0


def main():
    run_tests = '--run-tests' in sys.argv[1:]
    install = '--install' in sys.argv[1:]
    logs = []
    source_count = None
    packaged_count = None
    if run_tests:
        source_log = run(str(WORK / 'test_appropriate_locker.py'))
        logs.append(source_log)
        source_count = int(re.search(r'Ran (\d+) tests', source_log).group(1))
    compiled = WORK / '_mod_appropriate_locker_build.pyc'
    temporary = PACKAGE.with_suffix('.wotmod.tmp')
    try:
        run('-c', 'import py_compile,sys; py_compile.compile(sys.argv[1],sys.argv[2],sys.argv[3],True)',
            str(SOURCE), str(compiled), ENTRY[:-1])
        bytecode = compiled.read_bytes()
        assert len(bytecode) > 8
        assert struct.unpack('<H', bytecode[:2])[0] == 62211
        metadata = (
            '<root>\n'
            '    <id>ua.appropriate_locker</id>\n'
            '    <version>%s</version>\n'
            '    <name>Appropriate Locker</name>\n'
            '    <description>Follow the selected vehicle surface while camera tracking is active.</description>\n'
            '</root>\n'
        ) % VERSION
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(zipfile.ZipInfo('meta.xml'), metadata.encode('utf-8'))
            archive.writestr(zipfile.ZipInfo(ENTRY), bytecode)
        assert temporary.exists() and temporary.stat().st_size > 0
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == {'meta.xml', ENTRY}
            assert archive.read(ENTRY) == bytecode
            assert all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
            meta_root = ET.fromstring(archive.read('meta.xml'))
            assert meta_root.findtext('id') == 'ua.appropriate_locker'
            assert meta_root.findtext('name') == 'Appropriate Locker'
            assert meta_root.findtext('version') == VERSION
        if run_tests:
            packaged_log = run(str(WORK / 'test_appropriate_locker.py'), '--package', str(temporary))
            logs.append(packaged_log)
            packaged_count = int(re.search(r'Ran (\d+) tests', packaged_log).group(1))
        native_log = run(str(WORK / 'check_native.py'), '--package', str(temporary))
        logs.append(native_log)
        if PACKAGE.exists() and PACKAGE.read_bytes() != temporary.read_bytes():
            backup_file(PACKAGE)
        os.replace(temporary, PACKAGE)
    finally:
        if compiled.exists():
            compiled.unlink()
        if temporary.exists():
            temporary.unlink()
    version_raw = re.search(
        r'<version>\s*(.*?)\s*</version>',
        (ROOT / 'version.xml').read_text(encoding='utf-8')).group(1)
    mods_version = re.search(r'v\.([0-9.]+)', version_raw).group(1)
    installed_path = None
    if install:
        mods_dir = ROOT / 'mods' / mods_version
        mods_dir.mkdir(parents=True, exist_ok=True)
        installed_target = mods_dir / PACKAGE.name
        install_tmp = installed_target.with_suffix('.wotmod.tmp')
        try:
            payload = PACKAGE.read_bytes()
            install_tmp.write_bytes(payload)
            assert install_tmp.exists() and install_tmp.stat().st_size == len(payload)
            with zipfile.ZipFile(install_tmp) as archive:
                assert archive.testzip() is None
            if installed_target.exists() and installed_target.read_bytes() != payload:
                backup_file(installed_target, prefix='installed_')
            os.replace(install_tmp, installed_target)
            installed_path = str(installed_target)
        finally:
            if install_tmp.exists():
                install_tmp.unlink()
    native = json.loads((WORK / 'native-validation.json').read_text(encoding='utf-8'))
    report = {
        'created': datetime.now().astimezone().isoformat(),
        'game_version': version_raw,
        'mods_version': mods_version,
        'id': 'ua.appropriate_locker',
        'name': 'Appropriate Locker',
        'version': VERSION,
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'package_sha256': hashlib.sha256(PACKAGE.read_bytes()).hexdigest(),
        'package': str(PACKAGE),
        'package_entries': ['meta.xml', ENTRY],
        'bytecode_magic': bytecode[:4].hex(),
        'archive_integrity': 'passed',
        'compression': 'ZIP_STORED',
        'source_tests_passed': source_count,
        'packaged_tests_passed': packaged_count,
        'native_tracking_runs_passed': len(native['runs']),
        'installed': bool(install),
        'installed_path': installed_path,
        'live_game_verified': False,
        'native_validation': native,
    }
    (WORK / 'validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (WORK / 'validation.log').write_text('\n'.join(logs), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
