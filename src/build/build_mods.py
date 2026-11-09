import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile

import mods_registry

py27 = 'py27_dist/python.exe'
if b'worldoftanks.exe' in subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH']).lower():
    raise RuntimeError('Live installation waits for game exit')

repo = mods_registry.find_repo(os.path.dirname(os.path.abspath(__file__)))
if repo is None:
    raise SystemExit('Repository with src/mods not found')
mods = mods_registry.load_mods(repo)
run_tests = '--run-tests' in sys.argv


def game_version():
    if os.path.exists('version.xml'):
        with open('version.xml', 'r') as handle:
            match = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', handle.read())
            if match:
                return match.group(1)
    return '2.4.1.0'


ver = game_version()
build_dir = 'build/mods/%s' % ver
os.makedirs(build_dir, exist_ok=True)


def expand(value):
    return mods_registry.expand(value, ver)


def path_for(value):
    value = value.replace('{ver}', ver)
    if value.startswith('src/'):
        return os.path.join(repo, value)
    return value


def meta_xml(mod, cfg):
    return (
        '<root>\n'
        '    <id>%s</id>\n'
        '    <version>%s</version>\n'
        '    <name>%s</name>\n'
        '    <description>%s</description>\n'
        '</root>'
    ) % (mod['id'], mod['version'], cfg.get('name', mod['title']), cfg.get('description', mod.get('description', '')))


def create_or_update_wotmod(src_wotmod, dst_wotmod, update_map):
    temporary = dst_wotmod + '.tmp'
    os.makedirs(os.path.dirname(dst_wotmod), exist_ok=True)
    written = set()
    with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_STORED) as output:
        if os.path.exists(src_wotmod):
            with zipfile.ZipFile(src_wotmod, 'r') as source:
                for item in source.infolist():
                    data = update_map[item.filename] if item.filename in update_map else source.read(item.filename)
                    entry = zipfile.ZipInfo(item.filename)
                    entry.compress_type = zipfile.ZIP_STORED
                    entry.date_time = item.date_time
                    entry.external_attr = item.external_attr
                    output.writestr(entry, data)
                    written.add(item.filename)
        for name, data in update_map.items():
            if name not in written:
                entry = zipfile.ZipInfo(name)
                entry.compress_type = zipfile.ZIP_STORED
                output.writestr(entry, data)
    os.replace(temporary, dst_wotmod)


def run_command(argv):
    resolved = []
    for index, argument in enumerate(argv):
        argument = argument.replace('{ver}', ver)
        if index == 0 and argument == 'python':
            resolved.append(sys.executable)
        elif index == 0 and argument == 'py27':
            resolved.append(py27)
        elif argument.startswith('src/'):
            resolved.append(os.path.join(repo, argument))
        else:
            resolved.append(argument)
    subprocess.check_call(resolved)


def build_pyc(mod):
    cfg = mod['build']
    source = path_for(cfg['source'])
    subprocess.check_call([py27, '-m', 'py_compile', source])
    compiled = os.path.splitext(source)[0] + '.pyc'
    update = {'meta.xml': meta_xml(mod, cfg), cfg['entry']: open(compiled, 'rb').read()}
    for extra in cfg.get('extra', []):
        extra_source = path_for(extra['source'])
        if os.path.exists(extra_source):
            update[extra['entry']] = open(extra_source, 'rb').read()
    output = path_for(cfg['output'])
    create_or_update_wotmod(path_for(cfg['base']), output, update)
    return [output]


def build_script(mod):
    cfg = mod['build']
    commands = expand(cfg.get('commands', []))
    if run_tests and cfg.get('test_args') and commands:
        commands[0] = commands[0] + cfg['test_args']
    for command in commands:
        run_command(command)
    outputs = []
    for item in expand(cfg.get('outputs', [])):
        target = path_for(item['to'])
        if item.get('from'):
            source = path_for(item['from'])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(source, target)
        if not os.path.exists(target):
            raise SystemExit('Build output missing for %s: %s' % (mod['id'], target))
        if target.endswith('.wotmod'):
            outputs.append(target)
    if run_tests:
        for command in expand(cfg.get('test_commands', [])):
            run_command(command)
    return outputs


outputs = []
for mod in mods:
    kind = mod.get('build', {}).get('kind', 'none')
    built = []
    if kind == 'pyc':
        built = build_pyc(mod)
    elif kind == 'script':
        built = build_script(mod)
    elif kind == 'prebuilt':
        built = [path_for(item['source']) for item in mod.get('files', []) if item['source'].endswith('.wotmod')]
    elif kind != 'none':
        raise SystemExit('Unknown build kind %s for %s' % (kind, mod['id']))
    outputs.extend(built)
    for item in mod.get('obsolete', []):
        for base in (build_dir, os.path.join('mods', ver)):
            target = os.path.join(base, item)
            if os.path.exists(target):
                try:
                    os.remove(target)
                    print('Removed obsolete wotmod:', target)
                except OSError:
                    pass
    print('Built: %s' % mod['id'])

for output in outputs:
    if not os.path.exists(output):
        raise SystemExit('Missing package: %s' % output)
    live_target = os.path.join('mods', ver, os.path.basename(output))
    if os.path.abspath(output) != os.path.abspath(live_target):
        try:
            shutil.copy2(output, live_target)
        except OSError:
            pass

for output in outputs:
    with zipfile.ZipFile(output, 'r') as archive:
        for item in archive.infolist():
            assert item.compress_type == zipfile.ZIP_STORED, '%s: %s not ZIP_STORED' % (output, item.filename)
print('Verified: all wotmod packages have compress_type == 0.')
print('MOD BUILD FINISHED: sources compiled, wotmods packaged, live mods folder updated.')
