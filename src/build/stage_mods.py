import hashlib
import json
import os
import re
import shutil
import sys

import mods_registry

REMOTE_BASE = 'https://github.com/Niedvin/WOT-Mod-Launcher/releases/latest/download'
STAGING = 'staging_modpack'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1048576), b''):
            digest.update(chunk)
    return digest.hexdigest()


def get_game_version():
    if os.path.exists('version.xml'):
        with open('version.xml', 'r') as handle:
            match = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', handle.read())
            if match:
                return match.group(1)
    return '2.4.1.0'


def resolve_source(path, repo, ver):
    path = path.replace('{ver}', ver)
    if path.startswith('src/'):
        return os.path.join(repo, path)
    return path


def main():
    repo = mods_registry.find_repo(os.path.dirname(os.path.abspath(__file__)))
    if repo is None:
        raise SystemExit('Repository with src/mods not found')
    mods = mods_registry.load_mods(repo)
    ver = get_game_version()

    stale_configs = os.path.join(STAGING, 'Configs')
    if os.path.exists(stale_configs):
        shutil.rmtree(stale_configs)
    mods_dir = os.path.join(STAGING, 'Mods')
    os.makedirs(mods_dir, exist_ok=True)

    expected_folders = set()
    for mod in mods:
        folder = mod['folder']
        expected_folders.add(folder)
        target_mod_dir = os.path.join(mods_dir, folder)
        os.makedirs(target_mod_dir, exist_ok=True)
        game_files_dir = os.path.join(target_mod_dir, 'game_files')
        if os.path.exists(game_files_dir):
            shutil.rmtree(game_files_dir)

        remote_entries = []
        total_size = 0
        for item in mods_registry.expand(mod['files'], ver):
            source = resolve_source(item['source'], repo, ver)
            if not os.path.isfile(source):
                raise SystemExit('Missing file for %s: %s' % (mod['id'], source))
            target = os.path.join(target_mod_dir, item['target'])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
            total_size += os.path.getsize(target)

        for item in mods_registry.expand(mod.get('remote', []), ver):
            source = resolve_source(item['source'], repo, ver)
            if not os.path.isfile(source):
                raise SystemExit('Missing remote payload for %s: %s' % (mod['id'], source))
            name = os.path.basename(source)
            remote_entries.append({
                'id': item['id'],
                'file': name,
                'path': item['target'],
                'source': source,
                'size': os.path.getsize(source),
                'sha256': sha256_file(source),
                'url': '%s/%s' % (REMOTE_BASE, name)
            })
            total_size += os.path.getsize(source)

        info = {
            'id': mod['id'],
            'title': mod['title'],
            'version': mod['version'],
            'author': mod.get('author', ''),
            'description': mod.get('description', ''),
            'changes': mod.get('changes', ''),
            'default_checked': bool(mod.get('default_checked', True)),
            'clean_patterns': mod.get('clean_patterns', []),
            'clean_res_mods': mod.get('clean_res_mods', []),
            'size_bytes': total_size
        }
        if remote_entries:
            info['download_bytes'] = sum(entry['size'] for entry in remote_entries)
            info['remote_files'] = remote_entries
        if mod.get('required'):
            info['required'] = True
        if mod.get('updates'):
            info['updates'] = mod['updates']
        with open(os.path.join(target_mod_dir, 'info.json'), 'w', encoding='utf-8') as handle:
            json.dump(info, handle, indent=4, ensure_ascii=False)
        print('Mod prepared: %s (%.2f MB)' % (folder, total_size / (1024 * 1024)))

    # A renamed or dropped mod folder would otherwise still be offered by the installer
    for name in sorted(os.listdir(mods_dir)):
        path = os.path.join(mods_dir, name)
        if name not in expected_folders and os.path.isdir(path):
            shutil.rmtree(path)
            print('Removed stale staged mod:', name)

    readme = '===================================================================\n'
    readme += '                WoT Modpack by Niedvin\n'
    readme += '===================================================================\n\n'
    readme += 'Опис збірки:\n'
    readme += 'Даний модпак містить окремі модифікації для World of Tanks (EU):\n\n'
    for index, mod in enumerate(mods, 1):
        readme += '%d. %s (v%s)\n' % (index, mod['title'], mod['version'])
        for feature in mod.get('readme_features', []):
            readme += '   - %s\n' % feature
    readme += '\n-------------------------------------------------------------------\n'
    readme += 'Завантаження важких пакетів:\n'
    readme += '-------------------------------------------------------------------\n'
    readme += 'Пакети GPU Boost (OpenWG Core, DLSS/FSR та XeSS, ~167 МБ) не входять у дистрибутив.\n'
    readme += 'Інсталятор завантажує їх з GitHub лише тоді, коли позначено мод GPU Boost,\n'
    readme += 'перевіряє SHA-256 і кешує у %LOCALAPPDATA%\\WotModpack\\payload_cache.\n'
    readme += 'Якщо інтернету немає — решта модів встановлюється, GPU Boost пропускається.\n\n'
    readme += '-------------------------------------------------------------------\n'
    readme += 'Лаунчер автооновлення модів:\n'
    readme += '-------------------------------------------------------------------\n'
    readme += 'Під час встановлення можна встановити лаунчер WotModLauncher\n'
    readme += 'для автоматичної перевірки оновлень усіх модів з GitHub.\n'
    with open(os.path.join(STAGING, 'README.txt'), 'w', encoding='utf-8') as handle:
        handle.write(readme)
    print('README.txt updated.')
    print('All mods staged successfully.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('STAGE FAILED: %s' % error)
        sys.exit(1)
