import os
import shutil
import json
import re

def get_game_version():
    if os.path.exists('version.xml'):
        with open('version.xml', 'r') as f:
            m = re.search(r'v\.(\d+\.\d+\.\d+\.\d+)', f.read())
            if m:
                return m.group(1)
    return '2.4.1.0'

ver = get_game_version()

staging = 'staging_modpack'
stale_configs = os.path.join(staging, 'Configs')
if os.path.exists(stale_configs):
    shutil.rmtree(stale_configs)
mods_dir = os.path.join(staging, 'Mods')
os.makedirs(mods_dir, exist_ok=True)

def get_src_wotmod(filename):
    b = os.path.join('build', 'mods', ver, filename)
    if os.path.exists(b):
        return b
    n = os.path.join('mods', ver, filename + '.new')
    if os.path.exists(n):
        return n
    m = os.path.join('mods', ver, filename)
    if os.path.exists(m):
        return m
    s = os.path.join('scratch', 'spectator_hud', filename)
    if os.path.exists(s):
        return s
    return os.path.join('mods', ver, filename)

def src_first(*paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return paths[-1]

mods_def = [
    {
        'folder': '01_Server_Online_Autoconnect',
        'id': 'server_online',
        'title': 'Smart Server',
        'version': '1.1.2',
        'author': 'Niedvin',
        'description': 'Автоматичний вибір сервера з максимальним онлайном, розширене меню вибору сервера з числовим онлайном без обрізання та авто-релоґін після бою при дисбалансі онлайну (>=1.5x).',
        'changes': 'Нова назва: Smart Server. Вибір сервера за онлайном та авто-релоґін без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.server_online_autoconnect*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Автоматичне підключення до сервера з найбільшим активним онлайном.',
            'Кількість гравців у списку серверів без обрізання тексту: EU1 (17 070).',
            'Автоматичний перехід на інший сервер після бою при перекосі онлайну (>= 1.5x).'
        ],
        'files': [
            (get_src_wotmod('ua.server_online_autoconnect_1.1.2.wotmod'), 'game_files/mods/_VERSION_/ua.server_online_autoconnect_1.1.2.wotmod'),
            ('mods/configs/server_online/config.json', 'game_files/mods/configs/server_online/config.json'),
            ('mods/configs/server_online/cache.json', 'game_files/mods/configs/server_online/cache.json'),
            ('mods/configs/server_online/mod_server_online_autoconnect.py', 'game_files/mods/configs/server_online/mod_server_online_autoconnect.py')
        ]
    },
    {
        'folder': '02_Platoon_Autostart',
        'id': 'platoon_autostart',
        'title': 'Squad+',
        'version': '1.0.3',
        'author': 'Niedvin',
        'description': 'Автоматичний старт взводу при готовності всіх бійців, системне сповіщення про старт та модернізований компактний інтерфейс вікна взводу, сумісний з івентовими ангарами.',
        'changes': 'Нова назва: Squad+. Функціонал без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.platoon_autostart*.wotmod'],
        'clean_res_mods': [
            'scripts/client/gui/mods/mod_platoon_autostart.pyc',
            'gui/gameface/_dist/production/lobby/platoon'
        ],
        'readme_features': [
            'Автоматичний вхід у бій взводу при готовності всіх гравців.',
            'Захист від подвійних кліків (кулдаун 0.5с).',
            'Дублювання кнопки "В бій" безпосередньо у вікні взводу.',
            'Оновлений компактний інтерфейс вікна взводу, сумісний з івентовими ангарами.'
        ],
        'files': [
            (get_src_wotmod('ua.platoon_autostart_1.0.3.wotmod'), 'game_files/mods/_VERSION_/ua.platoon_autostart_1.0.3.wotmod'),
            ('mods/configs/platoon_autostart/config.json', 'game_files/mods/configs/platoon_autostart/config.json'),
            ('mods/configs/platoon_autostart/mod_platoon_autostart.py', 'game_files/mods/configs/platoon_autostart/mod_platoon_autostart.py')
        ]
    },
    {
        'folder': '03_Armor_Flashlight_Brightness',
        'id': 'armor_flashlight',
        'title': 'Velet Penetration',
        'version': '1.0.2',
        'author': 'Niedvin',
        'description': 'Налаштування яскравості та радіуса підсвічування коліматора/ліхтарика зон пробиття броні (зелений 1.5x, жовтий 1.1x, збільшений радіус 1.5x).',
        'changes': 'Нова назва: Velet Penetration. Функціонал без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.armor_flashlight_brightness*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Покращене кольорове підсвічування ліхтарика/коліматора бронепробиття.',
            'Налаштування яскравості та збільшений радіус підсвітки зон пробиття (1.5x).'
        ],
        'files': [
            (get_src_wotmod('ua.armor_flashlight_brightness_1.0.2.wotmod'), 'game_files/mods/_VERSION_/ua.armor_flashlight_brightness_1.0.2.wotmod'),
            ('mods/configs/armor_flashlight/config.json', 'game_files/mods/configs/armor_flashlight/config.json'),
            ('mods/configs/armor_flashlight/mod_armor_flashlight_brightness.py', 'game_files/mods/configs/armor_flashlight/mod_armor_flashlight_brightness.py')
        ]
    },
    {
        'folder': '04_ModsSettingsAPI',
        'id': 'modssettingsapi',
        'required': True,
        'title': 'ModsSettings API',
        'version': '1.7.1',
        'author': 'Izeberg',
        'description': 'Системний графічний інтерфейс для налаштування встановлених модифікацій прямо в меню гри.',
        'changes': 'Оновлення сумісності системного інтерфейсу налаштувань модів.',
        'default_checked': True,
        'clean_patterns': ['*modssettingsapi*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Системний API графічного інтерфейсу для налаштування модів у меню гри.'
        ],
        'files': [
            (f'mods/{ver}/izeberg.modssettingsapi_1.7.1.wotmod', 'game_files/mods/_VERSION_/izeberg.modssettingsapi_1.7.1.wotmod')
        ],
        'updates': [{'id': 'izeberg.modssettingsapi', 'kind': 'github', 'repo': 'izeberg/modssettingsapi'}]
    },
    {
        'folder': '05_ModsListAPI',
        'id': 'modslistapi',
        'required': True,
        'title': 'ModsList API',
        'version': '1.8.0',
        'author': 'Poliroid',
        'description': 'Системний API для розміщення кнопки та списку модифікацій у нижньому правому кутку ангару.',
        'changes': 'Оновлення сумісності API списку модів в ангарі.',
        'default_checked': True,
        'clean_patterns': ['*modslistapi*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Системний API для розміщення кнопки та списку модів в ангарі.'
        ],
        'files': [
            (f'mods/{ver}/me.poliroid.modslistapi_1.8.0.wotmod', 'game_files/mods/_VERSION_/me.poliroid.modslistapi_1.8.0.wotmod')
        ],
        'updates': [{'id': 'me.poliroid.modslistapi', 'kind': 'gitlab', 'repo': 'wot-public-mods/mods-list'}]
    },
    {
        'folder': '06_OpenWG_Core',
        'id': 'openwg',
        'required': True,
        'title': 'OpenWG Core & Fixes',
        'version': '1.9.0',
        'author': 'OpenWG Team',
        'description': 'Набір бібліотек OpenWG: виправлення відображення післябойових результатів, реплеїв та підтримка GameFace інтерфейсу.',
        'changes': 'Оновлення виправлень післябойових результатів, реплеїв та GameFace.',
        'default_checked': True,
        'clean_patterns': ['net.openwg/*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Пакет бібліотек OpenWG: виправлення кешу післябойових результатів, реплеїв та підтримка GameFace.'
        ],
        'files': [
                        (f'mods/{ver}/net.openwg/net.openwg.fix.battleresultscache_1.9.0.wotmod', 'game_files/mods/_VERSION_/net.openwg/net.openwg.fix.battleresultscache_1.9.0.wotmod'),
            (f'mods/{ver}/net.openwg/net.openwg.fix.battleresultsreplays_1.1.0.wotmod', 'game_files/mods/_VERSION_/net.openwg/net.openwg.fix.battleresultsreplays_1.1.0.wotmod'),
            (f'mods/{ver}/net.openwg/net.openwg.gameface_1.2.2.wotmod', 'game_files/mods/_VERSION_/net.openwg/net.openwg.gameface_1.2.2.wotmod')
        ],
        'updates': [
            {'id': 'net.openwg.gameface', 'kind': 'gitlab', 'repo': 'openwg/wot.gameface'},
            {'id': 'net.openwg.fix.battleresultscache', 'kind': 'gitlab', 'repo': 'openwg/fixedbattleresultscache'},
            {'id': 'net.openwg.fix.battleresultsreplays', 'kind': 'gitlab', 'repo': 'openwg/wot.fix.battleresultsreplays'}
        ]
    },
    {
        'folder': '07_Spectator_Teammate_HUD',
        'id': 'spectator_teammate_hud',
        'title': 'Spectator+',
        'version': '1.0.9',
        'author': 'Niedvin',
        'description': 'Відображає приціл у реальному часі, таймер перезарядки, стан модулів і екіпажу, а також таймери перезарядки спорядження союзника, за яким ви спостерігаєте після знищення вашого танка.',
        'changes': 'Нова назва: Spectator+. Функціонал без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.spectator_teammate_hud*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Відображення прицілу (коліматора й динамічного кола розкиду в 60 FPS) союзника при спостереженні після смерті.',
            'Актуальний таймер перезарядки гармати з урахуванням часу, що вже минув.',
            'Відображення пошкоджених та знищених модулів і екіпажу на панелі пошкоджень.',
            'Відображення кругового кулдауну та числового зворотного відліку спорядження союзника.',
            'Повна відсутність фонового навантаження на FPS під час живого бою.'
        ],
        'files': [
            (get_src_wotmod('ua.spectator_teammate_hud_1.0.9.wotmod'), 'game_files/mods/_VERSION_/ua.spectator_teammate_hud_1.0.9.wotmod'),
            ('mods/configs/spectator_teammate_hud/config.json', 'game_files/mods/configs/spectator_teammate_hud/config.json')
        ]
    },
    {
        'folder': '08_Background_FPS_Limiter',
        'id': 'background_fps_limiter',
        'title': 'Background FPS Limiter',
        'version': '1.0.4',
        'author': 'Niedvin',
        'description': 'Обмежує частоту кадрів (за замовчуванням 5 FPS), коли вікно гри не в фокусі (alt-tab або згортання), щоб зменшити навантаження на процесор і відеокарту; окремі перемикачі для ангару та бою.',
        'changes': 'Технічне оновлення пакета, функціонал без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.background_fps_limiter*.wotmod'],
        'clean_res_mods': [],
        'readme_features': [
            'Обмежує частоту кадрів гри у фоновому режимі (за замовчуванням 5 FPS).',
            'Окремі перемикачі для ангару та бою.',
            'Працює і при згортанні вікна, і при переході в інше вікно (alt-tab).',
            'Окремий повзунок FPS у фокусі, щоб гра не залипала на 60 кадрах.',
            'Зменшує навантаження на процесор і відеокарту, коли гра неактивна.'
        ],
        'files': [
            (get_src_wotmod('ua.background_fps_limiter_1.0.4.wotmod'), 'game_files/mods/_VERSION_/ua.background_fps_limiter_1.0.4.wotmod'),
            ('mods/configs/background_fps_limiter/config.json', 'game_files/mods/configs/background_fps_limiter/config.json'),
            ('mods/configs/background_fps_limiter/mod_background_fps_limiter.py', 'game_files/mods/configs/background_fps_limiter/mod_background_fps_limiter.py'),
            ('mods/configs/background_fps_limiter/_ua_window_focus.pyd', 'game_files/mods/configs/background_fps_limiter/_ua_window_focus.pyd')
        ]
    },
    {
        'folder': '09_Research_Button',
        'id': 'research_button',
        'title': 'Quick Research',
        'version': '1.2.4',
        'author': 'Niedvin',
        'description': 'Кнопка дослідження на середині лівого краю кожної плитки з танком; одразу відкриває дослідження цього танка.',
        'changes': 'Нова назва: Quick Research. Функціонал без змін.',
        'default_checked': True,
        'clean_patterns': ['ua.research_button*.wotmod'],
        'clean_res_mods': ['gui/flash/TankCarousel.swf', 'gui/maps/icons/buttons/ua_research_btn.png', 'gui/gameface/_dist/production/mono/hangar/main/bundle.js'],
        'readme_features': [
            'Кнопка дослідження на кожній плитці каруселі танків.',
            'Відкриває дерево дослідження саме того танка, на плитці якого натиснуто.',
            'Research tree shortcut at the left edge center of occupied carousel cards.'
        ],
        'files': [
            (get_src_wotmod('ua.research_button_1.2.4.wotmod'), 'game_files/mods/_VERSION_/ua.research_button_1.2.4.wotmod'),
            (src_first(f'build/res_mods/{ver}/gui/gameface/_dist/production/mono/hangar/main/bundle.js', f'res_mods/{ver}/gui/gameface/_dist/production/mono/hangar/main/bundle.js'), 'game_files/res_mods/_VERSION_/gui/gameface/_dist/production/mono/hangar/main/bundle.js'),
            ('mods/configs/research_button/config.json', 'game_files/mods/configs/research_button/config.json'),
            ('mods/configs/research_button/mod_research_button.py', 'game_files/mods/configs/research_button/mod_research_button.py'),
            ('mods/configs/research_button/mod_research_button.pyc', 'game_files/mods/configs/research_button/mod_research_button.pyc')
        ]
    }
]

for m in mods_def:
    target_mod_dir = os.path.join(mods_dir, m['folder'])
    os.makedirs(target_mod_dir, exist_ok=True)
    game_files_dir = os.path.join(target_mod_dir, 'game_files')
    if os.path.exists(game_files_dir):
        shutil.rmtree(game_files_dir)
    for src, dst_rel in m['files']:
        dst = os.path.join(target_mod_dir, dst_rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    total_size = 0
    for root, dirs, files in os.walk(os.path.join(target_mod_dir, 'game_files')):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))
    info = {
        'id': m['id'],
        'title': m['title'],
        'version': m['version'],
        'author': m['author'],
        'description': m['description'],
        'changes': m['changes'],
        'default_checked': m['default_checked'],
        'clean_patterns': m['clean_patterns'],
        'clean_res_mods': m['clean_res_mods'],
        'size_bytes': total_size
    }
    if m.get('required'):
        info['required'] = True
    if m.get('updates'):
        info['updates'] = m['updates']
    with open(os.path.join(target_mod_dir, 'info.json'), 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=4, ensure_ascii=False)
    print(f"Mod prepared: {m['folder']} ({total_size / (1024*1024):.2f} MB)")

readme = '===================================================================\n'
readme += '                WoT Modpack by Niedvin\n'
readme += '===================================================================\n\n'
readme += 'Опис збірки:\n'
readme += 'Даний модпак містить окремі модифікації для World of Tanks (EU):\n\n'
for i, m in enumerate(mods_def, 1):
    readme += f"{i}. {m['title']} (v{m['version']})\n"
    for feat in m['readme_features']:
        readme += f"   - {feat}\n"
readme += '\n-------------------------------------------------------------------\n'
readme += 'Лаунчер автооновлення модів:\n'
readme += '-------------------------------------------------------------------\n'
readme += 'Під час встановлення можна встановити лаунчер WotModLauncher\n'
readme += '(папка %LOCALAPPDATA%\\WotModpack) та окремий ярлик "World of Tanks EU (модпак)":\n'
readme += ' - перед кожним запуском гри лаунчер перевіряє оновлення модів у мережі (до 4 секунд);\n'
readme += ' - якщо оновлень немає або немає інтернету — гра запускається одразу, без зайвих вікон;\n'
readme += ' - якщо оновлення є — відкривається вікно зі списком змін та кнопками\n'
readme += '   "Оновити і грати" / "Грати без оновлення";\n'
readme += ' - за бажанням лаунчер вбудовується у стандартні ярлики гри (робочий стіл та меню\n'
readme += '   "Пуск"); оригінальні ярлики зберігаються і повертаються під час видалення.\n\n'
readme += '-------------------------------------------------------------------\n'
readme += 'Інструкція зі встановлення:\n'
readme += '-------------------------------------------------------------------\n'
readme += '1. Варіант "один файл": завантажте WoT_Modpack_by_Niedvin_Setup.exe і просто запустіть його —\n'
readme += '   розпаковувати нічого не треба.\n'
readme += '2. Варіант "архів": розархівуйте WoT_Modpack_by_Niedvin.zip у будь-яку теку та запустіть "Installer.exe".\n'
readme += '   (якщо з\'явиться SmartScreen Windows: натисніть "Докладніше" -> "Виконати в будь-якому разі")\n'
readme += '3. Інсталятор автоматично знайде шлях до встановленої гри World of Tanks та визначить актуальну версію клієнта.\n'
readme += '4. Оберіть потрібні моди, параметри встановлення (бекап, лаунчер автооновлення) та натисніть "Встановити вибрані моди".\n'
readme += '5. За потреби можна запустити гру одразу через кнопку "Запустити World of Tanks".\n\n'
readme += '-------------------------------------------------------------------\n'
readme += 'Видалення:\n'
readme += '-------------------------------------------------------------------\n'
readme += 'Кнопка "Видалити..." у інсталяторі дозволяє вибірково прибрати будь-який мод,\n'
readme += 'збережені конфіги або лаунчер автооновлення (оригінальні ярлики гри при цьому\n'
readme += 'повертаються автоматично). Перед видаленням створюється резервна копія\n'
readme += 'у теці <гра>\\.backups\\, тож випадково видалене можна повернути вручну.\n\n'
readme += 'Автор збірки: Niedvin (2026)\n'
readme += '===================================================================\n'

with open(os.path.join(staging, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
    f.write(readme)
print('README.txt updated.')

print('All mods staged successfully.')
