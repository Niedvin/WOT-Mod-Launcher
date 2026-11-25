import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


RELEASES = 'https://github.com/Niedvin/WOT-Mod-Launcher/releases'
RETIRED = {'izeberg.modssettingsapi', 'me.poliroid.modslistapi', 'ua.mod_manager'}
DOWNLOAD = 'Niedvin_WoT_Modpack.zip'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metadata(path):
    with zipfile.ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read('meta.xml'))
    return root.findtext('id'), root.findtext('version')


def game_version(game_root):
    root = ElementTree.parse(game_root / 'version.xml').getroot()
    match = re.search(r'\bv\.(\d+(?:\.\d+){3})(?=\s|$)', root.findtext('version', ''))
    if not match:
        raise ValueError('Invalid game version in version.xml')
    return match.group(1)


def locate_package(root, record):
    name = record['file']
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+\.wotmod', name):
        raise ValueError('Invalid package filename: ' + name)
    for filename in (name, name + '.manager-off'):
        for path in root.rglob(filename):
            if sha(path) == record['sha256']:
                return path
    raise FileNotFoundError('Verified package missing: ' + name)


def replacement_packages(records, packages, game):
    families = {}
    for record in records:
        suffix = f"_{record['version']}.wotmod"
        if record['file'].endswith(suffix):
            families[record['file'].removesuffix(suffix)] = record['id']

    updates = {}
    for path in packages:
        mod_id, version = metadata(path)
        if not version or not re.fullmatch(r'\d+(?:\.\d+)+', version):
            raise ValueError('Invalid replacement version: ' + path.name)
        suffix = f'_{version}.wotmod'
        family = path.name.removesuffix(suffix)
        record_id = families.get(family)
        if not path.name.endswith(suffix) or record_id is None or mod_id not in (family, record_id):
            raise ValueError('Unexpected replacement package: ' + path.name)
        if record_id in updates:
            raise ValueError('Duplicate replacement: ' + record_id)
        updates[record_id] = (path, dict(
            version=version, file=path.name, sha256=sha(path), size=path.stat().st_size,
            changes=f'Сумісність із World of Tanks EU {game}.',
        ))
    return updates


def prepare(previous_manifest, game_root, manager, pack_version, output, packages=(), launcher=None,
            launcher_version=None):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', pack_version):
        raise ValueError('Invalid pack version')
    with previous_manifest.open(encoding='utf-8-sig') as handle:
        previous = json.load(handle)
    version = game_version(game_root)
    active = game_root / 'mods' / version
    base = RELEASES + '/download/pack-' + pack_version
    mod_id, mod_version = metadata(manager)
    if mod_id != 'ua.mod_manager' or manager.name != f'{mod_id}_{mod_version}.wotmod':
        raise ValueError('Unexpected mod manager identity')
    manifest = dict(schema=1, pack_version=pack_version, game_version=version, mods=[])
    attachments = {}
    if launcher or launcher_version:
        if not launcher or not launcher_version or not re.fullmatch(r'\d+(?:\.\d+){3}', launcher_version):
            raise ValueError('Set both launcher path and valid launcher version')
        launcher_name = 'WotModLauncher.exe'
        manifest['launcher'] = dict(version=launcher_version, url=base + '/' + launcher_name, sha256=sha(launcher))
        attachments[launcher_name] = launcher
    elif previous.get('launcher'):
        manifest['launcher'] = previous['launcher']
    records = [record for record in previous['mods'] if record['id'] not in RETIRED]
    updates = replacement_packages(records, packages, version)
    for record in records:
        if record['id'] in updates:
            path, fields = updates[record['id']]
            record = dict(record, **fields)
        else:
            path = locate_package(active, record)
        subdir = record.get('subdir', '').replace('\\', '/')
        if subdir and any(not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*', part)
                          for part in subdir.split('/')):
            raise ValueError('Invalid package subfolder: ' + subdir)
        name = record['file']
        manifest['mods'].append(dict(record, subdir=subdir, url=base + '/' + name))
        attachments[name] = path
    prior_manager = next((record for record in previous['mods'] if record['id'] == mod_id), {})
    manager_changes = prior_manager.get('changes', '') if prior_manager.get('version') == mod_version else (
        f'Сумісність із World of Tanks EU {version}.'
    )
    manifest['mods'].insert(0, dict(
        id=mod_id, title='Niedvin Mod Manager', version=mod_version, file=manager.name,
        subdir='', url=base + '/' + manager.name, sha256=sha(manager), size=manager.stat().st_size,
        default_checked=True, possible_cheat=False, possible_cheat_note='',
        changes=manager_changes,
    ))
    attachments[manager.name] = manager
    output.mkdir(parents=True)
    for name, source in attachments.items():
        shutil.copyfile(source, output / name)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with zipfile.ZipFile(output / DOWNLOAD, 'w', zipfile.ZIP_DEFLATED, compresslevel=5) as archive:
        for record in manifest['mods']:
            if record['default_checked']:
                target = PurePosixPath('mods', version, record['subdir'], record['file'])
                archive.write(output / record['file'], str(target))
        archive.writestr('Install.txt', (
            f'Close World of Tanks EU {version}. Extract the mods folder into the game folder beside version.xml.\n'
            'Start the game from Wargaming Game Center and open the Mods button in the hangar footer.\n'
            'Individual optional packages and their folders are listed in manifest.json on the release page.\n'
        ))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous-manifest', type=Path, required=True)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--manager', type=Path, required=True)
    parser.add_argument('--pack-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--package', type=Path, action='append', default=[])
    parser.add_argument('--launcher', type=Path)
    parser.add_argument('--launcher-version')
    options = parser.parse_args()
    manifest = prepare(options.previous_manifest, options.game_root, options.manager, options.pack_version,
                       options.output, options.package, options.launcher, options.launcher_version)
    print('Prepared %s packages at %s' % (len(manifest['mods']), options.output))


if __name__ == '__main__':
    main()
