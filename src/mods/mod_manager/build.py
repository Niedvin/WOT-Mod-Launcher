import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parent
INTERPRETER = ROOT / 'py27_dist' / 'python.exe'
MAIN_HTML = 'gui/gameface/_dist/production/mono/hangar/main/main.html'
FOOTER_HTML = 'gui/gameface/_dist/production/mono/hangar/footer/footer.html'
UI_PREFIX = 'gui/gameface/mods/niedvin/mod-manager/'
VERSION = '1.1.0'
PACKAGE = f'ua.mod_manager_{VERSION}.wotmod'
OLD_MANAGERS = ('izeberg.modssettingsapi', 'me.poliroid.modslistapi')
SCRIPTS = {
    '__init__.py': 'gui/ua_mod_manager/__init__.pyc',
    'manager.py': 'gui/ua_mod_manager/manager.pyc',
    'openwg.py': 'gui/ua_mod_manager/openwg.pyc',
    'catalog.py': 'gui/ua_mod_manager/catalog.pyc',
    'hangar.py': 'gui/ua_mod_manager/hangar.pyc',
    'restart.py': 'gui/ua_mod_manager/restart.pyc',
    'entry.py': 'gui/mods/mod_ua_mod_manager.pyc',
    'compat.py': 'gui/ua_mod_manager/compat.pyc',
}


def game_version():
    return re.search(r'v\.(\d+(?:\.\d+){3})', (ROOT / 'version.xml').read_text()).group(1)


def extend_html(archive, path, script):
    markup = archive.read(path).decode('utf-8')
    insert = '\n'.join((
        f'    <link rel="stylesheet" crossorigin href="coui://{UI_PREFIX}mod-manager.css">',
        f'    <script defer crossorigin src="coui://{UI_PREFIX}{script}"></script>',
    ))
    if markup.count('</head>') != 1:
        raise ValueError('Unexpected markup: ' + path)
    return markup.replace('</head>', insert + '\n  </head>')


def build():
    stage = ROOT / 'build' / 'mod_manager'
    stage.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ROOT / 'res' / 'packages' / 'gui-part4.pkg') as native:
        markup = extend_html(native, MAIN_HTML, 'mod-manager.js')
        footer = extend_html(native, FOOTER_HTML, 'mod-manager-footer.js')
    with tempfile.TemporaryDirectory(dir=stage) as scratch:
        scratch = Path(scratch)
        scripts = {}
        for source, destination in SCRIPTS.items():
            path = scratch / (source + 'c')
            subprocess.run([
                str(INTERPRETER), '-c',
                'import py_compile,sys; py_compile.compile(sys.argv[1],sys.argv[2],sys.argv[3],doraise=True)',
                str(SOURCE / source), str(path), destination[:-1],
            ], check=True)
            scripts['res/scripts/client/' + destination] = path.read_bytes()
        staged = scratch / PACKAGE
        with zipfile.ZipFile(staged, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('meta.xml', f'<root><id>ua.mod_manager</id><version>{VERSION}</version>'
                             '<name>Niedvin Mod Manager</name><description>Hangar mod manager</description></root>')
            archive.writestr('res/' + MAIN_HTML, markup)
            archive.writestr('res/' + FOOTER_HTML, footer)
            for file in (SOURCE / 'ui').glob('mod-manager*.*'):
                archive.write(file, 'res/' + UI_PREFIX + file.name)
            for destination, data in scripts.items():
                archive.writestr(destination, data)
        with zipfile.ZipFile(staged) as archive:
            if archive.testzip():
                raise ValueError('Corrupt mod package')
            if len(archive.namelist()) != len(SCRIPTS) + 6:
                raise ValueError('Incomplete mod package')
        output = stage / PACKAGE
        os.replace(staged, output)
    print('BUILD', output)
    return output


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_game_closed():
    found = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH'])
    if b'"worldoftanks.exe"' in found.lower():
        raise RuntimeError('World of Tanks is running')


def install(package):
    verify_game_closed()
    version = game_version()
    active = ROOT / 'mods' / version
    backup = ROOT / '.backups' / ('hangar-mod-manager-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    legacy = [path for path in active.rglob('*.wotmod') if path.name.startswith(OLD_MANAGERS)]
    previous = [path for path in active.rglob('*.wotmod') if re.fullmatch(r'ua\.mod_manager_[\d.]+\.wotmod', path.name)]
    current = active / PACKAGE
    views = (MAIN_HTML, FOOTER_HTML)
    for view in views:
        loose_path = ROOT / 'res_mods' / version / view
        if loose_path.exists():
            raise ValueError('Hangar HTML already overridden by ' + str(loose_path))
    for path in active.rglob('*.wotmod'):
        if path not in legacy and path not in previous:
            with zipfile.ZipFile(path) as archive:
                if any('res/' + view in archive.namelist() for view in views):
                    raise ValueError('Hangar HTML already supplied by ' + str(path))
    backup.mkdir(parents=True)
    configs = ROOT / 'mods' / 'configs'
    for path in configs.glob('*/*.json'):
        target = backup / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    moved = []
    deploy_temp = active / (PACKAGE + '.tmp')
    try:
        shutil.copy2(package, deploy_temp)
        if sha(deploy_temp) != sha(package):
            raise ValueError('Prepared package differs from verified build')
        verify_game_closed()
        for path in legacy + previous:
            destination = backup / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            digest = sha(path)
            path.rename(destination)
            moved.append((path, destination))
            if sha(destination) != digest:
                raise RuntimeError('Backup integrity check failed')
        deploy_temp.rename(current)
    except Exception:
        if current.exists() and sha(current) == sha(package):
            current.rename(backup / 'failed-install.wotmod')
        for path, destination in reversed(moved):
            destination.rename(path)
        raise
    finally:
        if deploy_temp.exists():
            deploy_temp.unlink()
    print('BACKUP', backup)
    print('INSTALLED', current, sha(current))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    package = build()
    if args.install:
        install(package)


if __name__ == '__main__':
    main()
