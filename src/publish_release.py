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


def locate_package(root, record):
    name = record['file']
    if not re.fullmatch(r'[a-zA-Z0-9_.-]+\.wotmod', name):
        raise ValueError('Invalid package filename: ' + name)
    for filename in (name, name + '.manager-off'):
        for path in root.rglob(filename):
            if sha(path) == record['sha256']:
                return path
    raise FileNotFoundError('Verified package missing: ' + name)


def prepare(previous_manifest, game_root, manager, pack_version, output):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', pack_version):
        raise ValueError('Invalid pack version')
    with previous_manifest.open(encoding='utf-8-sig') as handle:
        previous = json.load(handle)
    version = previous['game_version']
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', version):
        raise ValueError('Invalid game version')
    active = game_root / 'mods' / version
    base = RELEASES + '/download/pack-' + pack_version
    mod_id, mod_version = metadata(manager)
    if mod_id != 'ua.mod_manager' or manager.name != f'{mod_id}_{mod_version}.wotmod':
        raise ValueError('Unexpected mod manager identity')
    manifest = dict(schema=1, pack_version=pack_version, game_version=version, mods=[])
    attachments = {}
    for record in previous['mods']:
        if record['id'] in RETIRED:
            continue
        path = locate_package(active, record)
        subdir = record.get('subdir', '').replace('\\', '/')
        if subdir and any(not re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*', part)
                          for part in subdir.split('/')):
            raise ValueError('Invalid package subfolder: ' + subdir)
        name = record['file']
        manifest['mods'].append(dict(record, subdir=subdir, url=base + '/' + name))
        attachments[name] = path
    manifest['mods'].insert(0, dict(
        id=mod_id, title='Niedvin Mod Manager', version=mod_version, file=manager.name,
        subdir='', url=base + '/' + manager.name, sha256=sha(manager), size=manager.stat().st_size,
        default_checked=True, possible_cheat=False, possible_cheat_note='',
        changes='Continuous scrolling, a hangar footer button, one-click restart and automatic migration.',
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
    options = parser.parse_args()
    manifest = prepare(options.previous_manifest, options.game_root, options.manager, options.pack_version, options.output)
    print('Prepared %s packages at %s' % (len(manifest['mods']), options.output))


if __name__ == '__main__':
    main()
