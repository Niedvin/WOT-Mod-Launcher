import os
import re
import shutil
import subprocess
import zipfile

py27 = 'py27_dist/python.exe'
if b'worldoftanks.exe' in subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq WorldOfTanks.exe', '/FO', 'CSV', '/NH']).lower():
    raise RuntimeError('Live installation waits for game exit')

def get_game_version():
    if os.path.exists('version.xml'):
        with open('version.xml', 'r') as f:
            m = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', f.read())
            if m:
                return m.group(1)
    return '2.4.1.0'

ver = get_game_version()

py_targets = [
    'mods/configs/server_online/mod_server_online_autoconnect.py',
    'mods/configs/platoon_autostart/mod_platoon_autostart.py',
    'mods/configs/armor_flashlight/mod_armor_flashlight_brightness.py',
    'mods/configs/background_fps_limiter/mod_background_fps_limiter.py',
    'scratch/spectator_hud/mod_spectator_teammate_hud.py'
]

for pf in py_targets:
    subprocess.check_call([py27, '-m', 'py_compile', pf])
print('Compiled all Python 2.7 scripts.')

def create_or_update_wotmod(src_wotmod, dst_wotmod, update_map):
    temp_path = dst_wotmod + '.tmp'
    os.makedirs(os.path.dirname(dst_wotmod), exist_ok=True)
    if os.path.exists(src_wotmod):
        with zipfile.ZipFile(src_wotmod, 'r') as zin:
            with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_STORED) as zout:
                for item in zin.infolist():
                    data = update_map.get(item.filename, zin.read(item.filename))
                    zinfo = zipfile.ZipInfo(item.filename)
                    zinfo.compress_type = zipfile.ZIP_STORED
                    zinfo.date_time = item.date_time
                    zinfo.external_attr = item.external_attr
                    zout.writestr(zinfo, data)
                for fname, data in update_map.items():
                    if fname not in [i.filename for i in zin.infolist()]:
                        zinfo = zipfile.ZipInfo(fname)
                        zinfo.compress_type = zipfile.ZIP_STORED
                        zout.writestr(zinfo, data)
    else:
        with zipfile.ZipFile(temp_path, 'w', compression=zipfile.ZIP_STORED) as zout:
            for fname, data in update_map.items():
                zinfo = zipfile.ZipInfo(fname)
                zinfo.compress_type = zipfile.ZIP_STORED
                zout.writestr(zinfo, data)
    if os.path.exists(dst_wotmod):
        os.remove(dst_wotmod)
    os.rename(temp_path, dst_wotmod)

build_dir = f'build/mods/{ver}'
os.makedirs(build_dir, exist_ok=True)

def find_src_or_base(primary_name, fallback_name):
    for p in [f'{build_dir}/{primary_name}', f'mods/{ver}/{primary_name}', f'{build_dir}/{fallback_name}', f'mods/{ver}/{fallback_name}']:
        if os.path.exists(p):
            return p
    return f'mods/{ver}/{fallback_name}'

src_srv = find_src_or_base('ua.server_online_autoconnect_1.1.1.wotmod', 'ua.server_online_autoconnect_1.1.0.wotmod')
dst_srv = f'{build_dir}/ua.server_online_autoconnect_1.1.1.wotmod'
with open('mods/configs/server_online/mod_server_online_autoconnect.pyc', 'rb') as f:
    srv_pyc = f.read()
srv_meta = """<root>
    <id>ua.server_online_autoconnect</id>
    <version>1.1.1</version>
    <name>Server Online &amp; AutoConnect</name>
    <description>Automatically connects to highest population server, expands dropdown width, formats server names, and auto-reconnects post-battle when population is 1.5x higher.</description>
</root>"""
create_or_update_wotmod(src_srv, dst_srv, {
    'meta.xml': srv_meta,
    'res/scripts/client/gui/mods/mod_server_online_autoconnect.pyc': srv_pyc
})

src_plt = find_src_or_base('ua.platoon_autostart_1.0.1.wotmod', 'ua.platoon_autostart_1.0.0.wotmod')
dst_plt = f'{build_dir}/ua.platoon_autostart_1.0.1.wotmod'
with open('mods/configs/platoon_autostart/mod_platoon_autostart.pyc', 'rb') as f:
    plt_pyc = f.read()
plt_meta = """<root>
    <id>ua.platoon_autostart</id>
    <version>1.0.1</version>
    <name>Platoon Auto-Start &amp; Battle Button Mod</name>
    <description>Auto-starts battle when platoon is ready, duplicates Battle button in platoon window, and fixes ready cooldown delay.</description>
</root>"""
plt_map = {
    'meta.xml': plt_meta,
    'res/scripts/client/gui/mods/mod_platoon_autostart.pyc': plt_pyc
}
if os.path.exists('scratch/platoon_ui_edit/MembersWindow.js'):
    with open('scratch/platoon_ui_edit/MembersWindow.js', 'rb') as f:
        plt_map['res/gui/gameface/_dist/production/lobby/platoon/MembersWindow/MembersWindow.js'] = f.read()
if os.path.exists('scratch/platoon_ui_edit/MembersWindow.css'):
    with open('scratch/platoon_ui_edit/MembersWindow.css', 'rb') as f:
        plt_map['res/gui/gameface/_dist/production/lobby/platoon/MembersWindow/MembersWindow.css'] = f.read()
create_or_update_wotmod(src_plt, dst_plt, plt_map)

src_arm = find_src_or_base('ua.armor_flashlight_brightness_1.0.1.wotmod', 'ua.armor_flashlight_brightness_1.0.0.wotmod')
dst_arm = f'{build_dir}/ua.armor_flashlight_brightness_1.0.1.wotmod'
with open('mods/configs/armor_flashlight/mod_armor_flashlight_brightness.pyc', 'rb') as f:
    arm_pyc = f.read()
arm_meta = """<root>
    <id>ua.armor_flashlight_brightness</id>
    <version>1.0.1</version>
    <name>Armor Flashlight Brightness</name>
    <description>Boosts penetration indicator brightness localized on aimed armor.</description>
</root>"""
create_or_update_wotmod(src_arm, dst_arm, {
    'meta.xml': arm_meta,
    'res/scripts/client/gui/mods/mod_armor_flashlight_brightness.pyc': arm_pyc
})

src_fps = find_src_or_base('ua.background_fps_limiter_1.0.3.wotmod', 'ua.background_fps_limiter_1.0.0.wotmod')
dst_fps = f'{build_dir}/ua.background_fps_limiter_1.0.3.wotmod'
with open('mods/configs/background_fps_limiter/mod_background_fps_limiter.pyc', 'rb') as f:
    fps_pyc = f.read()
fps_meta = """<root>
    <id>ua.background_fps_limiter</id>
    <version>1.0.3</version>
    <name>Background FPS Limiter</name>
    <description>Limits client frame rate while the window is not focused to cut idle GPU and CPU load.</description>
</root>"""
create_or_update_wotmod(src_fps, dst_fps, {
    'meta.xml': fps_meta,
    'res/scripts/client/gui/mods/mod_background_fps_limiter.pyc': fps_pyc
})

subprocess.check_call(['python', 'scratch/background_fps/build.py'])
subprocess.check_call(['python', 'scratch/research_btn/build.py', '--install'])
subprocess.check_call(['python', 'scratch/spectator_hud/build.py'])
dst_hud = f'{build_dir}/ua.spectator_teammate_hud_1.0.6.wotmod'

for mod_file in [dst_srv, dst_plt, dst_arm, dst_fps, dst_hud]:
    live_target = os.path.join(f'mods/{ver}', os.path.basename(mod_file))
    try:
        shutil.copy2(mod_file, live_target)
    except OSError:
        pass

old_mods = [
    'ua.server_online_autoconnect_1.1.0.wotmod',
    'ua.platoon_autostart_1.0.0.wotmod',
    'ua.armor_flashlight_brightness_1.0.0.wotmod',
    'ua.background_fps_limiter_1.0.0.wotmod',
    'ua.spectator_teammate_hud_1.0.0.wotmod',
    'ua.spectator_teammate_hud_1.0.1.wotmod',
    'ua.spectator_teammate_hud_1.0.2.wotmod',
    'ua.spectator_teammate_hud_1.0.3.wotmod',
    'ua.spectator_teammate_hud_1.0.4.wotmod',
    'ua.spectator_teammate_hud_1.0.5.wotmod',
    'ua.background_fps_limiter_1.0.1.wotmod',
    'ua.background_fps_limiter_1.0.2.wotmod'
]
for om in old_mods:
    for base in [build_dir, f'mods/{ver}']:
        target = os.path.join(base, om)
        if os.path.exists(target):
            try:
                os.remove(target)
                print('Removed obsolete wotmod:', target)
            except OSError:
                pass

all_wotmods = [dst_srv, dst_plt, dst_arm, dst_fps, dst_hud]
for wm in all_wotmods:
    with zipfile.ZipFile(wm, 'r') as z:
        for item in z.infolist():
            assert item.compress_type == zipfile.ZIP_STORED, f'{wm}: {item.filename} not ZIP_STORED'
print('Verified: all wotmod packages have compress_type == 0.')

if '--run-tests' in __import__('sys').argv:
    subprocess.check_call([py27, 'scratch/test_hangar_detection.py'])
    subprocess.check_call([py27, 'scratch/spectator_hud/test_mod_integration.py'])
print('MOD BUILD FINISHED: sources compiled, wotmods packaged, live mods folder updated.')
