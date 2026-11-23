# -*- coding: utf-8 -*-
from __future__ import unicode_literals


def flag(key, label, default=True):
    return dict(key=key, label=label, default=default, kind='bool')


def number(key, label, default, minimum, maximum, step, unit='', scale=1):
    return dict(key=key, label=label, default=default, kind='number', min=minimum, max=maximum, step=step, unit=unit, scale=scale)


def profile(title, description, folder=None, module=None, fields=(), power='restart', config='_CONFIG', graphics=False):
    return dict(title=title, description=description, folder=folder, module=module, fields=fields,
                power=power, config=config, graphics=graphics)


PROFILES = {
    'ua.background_fps_limiter': profile(
        'Background FPS Limiter', 'Обмежує частоту кадрів, коли вікно гри у фокусі або у фоні.',
        'background_fps_limiter', 'mod_background_fps_limiter', (
            number('target_fps', 'FPS у фоні', 5, 1, 30, 1, 'FPS'),
            number('focused_fps', 'FPS у фокусі', 240, 30, 240, 10, 'FPS'),
            flag('enable_in_hangar', 'Обмежувати в ангарі'),
            flag('enable_in_battle', 'Обмежувати в бою'),
        ), power='live'),
    'armor_flashlight': profile(
        'Velet Penetration', 'Налаштовує яскравість, радіус і дальність індикатора броні.',
        'armor_flashlight', 'mod_armor_flashlight_brightness', (
            number('green_brightness_multiplier', 'Яскравість зеленої зони', 1.5, 50, 300, 10, '%', 100),
            number('yellow_brightness_multiplier', 'Яскравість жовтої зони', 1.1, 50, 300, 10, '%', 100),
            number('red_brightness_multiplier', 'Яскравість червоної зони', 1, 50, 200, 10, '%', 100),
            number('radius_multiplier', 'Радіус ліхтарика', 1.5, 50, 300, 10, '%', 100),
            number('max_distance_multiplier', 'Дальність ліхтарика', 1, 50, 300, 10, '%', 100),
        ), power='live'),
    'platoon_autostart': profile(
        'Squad+', 'Керує автозапуском, запрошеннями й вікном взводу.',
        'platoon_autostart', 'mod_platoon_autostart', (
            flag('auto_start_enabled', 'Автоматичний старт бою'),
            number('auto_start_delay', 'Затримка автостарту', 0.5, 100, 3000, 100, 'мс', 1000),
            flag('show_system_message', 'Системні сповіщення'),
            flag('cooldown_fix_enabled', 'Скорочувати затримку готовності'),
            number('cooldown_seconds', 'Затримка готовності', 0.5, 0, 5000, 100, 'мс', 1000),
            flag('duplicate_battle_button_enabled', 'Кнопка бою у вікні взводу'),
            flag('keep_window_open', 'Тримати вікно взводу відкритим'),
            flag('fixed_window_pos', 'Закріпити вікно на місці'),
            number('solo_invite_delay_min', 'Мінімальна пауза між запрошеннями', 2, 500, 30000, 500, 'мс', 1000),
            number('solo_invite_delay_max', 'Максимальна пауза між запрошеннями', 5, 500, 30000, 500, 'мс', 1000),
        ), power='squad'),
    'server_online': profile(
        'Smart Server', 'Показує онлайн серверів і використовує його для вибору сервера.',
        'server_online', 'mod_server_online_autoconnect', (
            flag('show_online_in_dropdown', 'Показувати онлайн серверів'),
            flag('auto_connect_max_online', 'Вибирати сервер із найбільшим онлайном'),
            flag('post_battle_relogin_enabled', 'Перепідключатися після бою'),
            number('relogin_ratio_threshold', 'Поріг різниці онлайну', 1.5, 110, 300, 10, '%', 100),
            flag('strip_wot_prefix', 'Прибирати WOT із назв серверів'),
            number('dropdown_menu_width', 'Ширина списку серверів', 250, 150, 600, 10, 'px'),
            flag('fetch_on_start', 'Оновлювати онлайн під час запуску'),
        ), power='live'),
    'ua.bui_customizer': profile(
        'BUI Customizer', 'Утримуйте клавішу редагування в бою. ЛКМ перетягує панель або її край, ПКМ відкриває меню списку танків.',
        'bui_customizer', 'mod_bui_customizer', power='live'),
    'ua.research_button': profile(
        'Quick Research', 'Відкриває дослідження модулів з картки машини.',
        'research_button', 'mod_research_button', power='live'),
    'ua.spectator_teammate_hud': profile(
        'Spectator+', 'Налаштовує приціл і показники машини союзника в режимі спостерігача.',
        'spectator_teammate_hud', 'mod_spectator_teammate_hud', (
            flag('show_teammate_reticle', 'Приціл союзника'),
            flag('show_actual_reload', 'Фактичний час перезаряджання'),
            flag('show_module_damage', 'Пошкоджені модулі'),
            flag('show_consumables_cooldown', 'Перезаряджання спорядження'),
            number('update_rate_fps', 'Частота оновлення прицілу', 0, 0, 240, 5, 'Гц'),
        ), power='live'),
    'ua.velet_presicion': profile(
        'Velet Presicion', 'Налаштовує поведінку прицілу й точність руху миші.',
        'velet_presicion', 'mod_velet_presicion', (
            flag('artillery', 'Артилерійський приціл'),
            flag('target_lock', 'Корекція при захопленій цілі'),
            flag('fine_mouse', 'Точні рухи миші', False),
        ), power='live', config='_config'),
    'ua.appropriate_locker': profile(
        'Appropriate Locker', 'Додає режим захоплення точки прицілювання. Перемикається в бою призначеною клавішею.'),
    'net.openwg.common': profile(
        'OpenWG Common', 'Бібліотека OpenWG. Коли активний Background FPS Limiter, він задає свій ліміт FPS.',
        graphics=True),
    'net.openwg.gameface': profile(
        'OpenWG Gameface', 'Допоміжна бібліотека для інтерфейсів інших модів.'),
    'net.openwg.fix.battleresultscache': profile(
        'Кеш результатів бою', 'Виправляє збереження результатів бою.'),
    'net.openwg.fix.battleresultsreplays': profile(
        'Результати бою в повторах', 'Виправляє відображення результатів бою в повторах.'),
    'net.openwg.gpu.upscaler': profile(
        'OpenWG GPU Upscalers', 'Масштабування зображення й нейронний рендеринг. Доступні опції залежать від відеокарти.',
        graphics=True),
    'net.openwg.gpu.upscaler.xess': profile(
        'Intel XeSS', 'Додає XeSS до OpenWG GPU Upscalers.'),
    'local.zdiag': profile(
        'Діагностика zdiag', 'Записує діагностичні дані в журнал клієнта.'),
}

BINDS = {
    'ua.bui_customizer': ('Утримувати для редагування', 'RALT'),
    'ua.appropriate_locker': ('Перемкнути режим захоплення', 'Q'),
    'ua.velet_presicion': ('Перемкнути точний і серверний приціли', 'F11'),
}

ALIASES = {
    'ua.armor_flashlight_brightness': 'armor_flashlight',
    'ua.platoon_autostart': 'platoon_autostart',
    'ua.server_online_autoconnect': 'server_online',
}

DEPENDENCIES = {
    'net.openwg.gpu.upscaler': 'net.openwg.common',
    'net.openwg.gpu.upscaler.xess': 'net.openwg.gpu.upscaler',
}

LEGACY_MANAGERS = {'izeberg.modssettingsapi', 'me.poliroid.modslistapi'}
HIDDEN = LEGACY_MANAGERS | {'ua.mod_manager'}
