# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import math
import os

from gui.ua_mod_manager.manager import read_json, write_json


PATH = os.path.join('mods', 'configs', 'bui_customizer', 'layout.json')
TEAMS = ('allies', 'enemies')
ELEMENTS = {
    'allies': 'Список союзників',
    'enemies': 'Список противників',
    'panelSwitch': 'Кнопки списків танків',
    'minimap': 'Мінімапа',
    'damagePanel': 'Стан машини',
    'consumablesPanel': 'Снаряди та спорядження',
    'battleMessenger': 'Бойовий чат',
    'battleTimer': 'Таймер бою',
    'prebattleTimer': 'Відлік до бою',
    'fragCorrelationBar': 'Рахунок і смуги команд',
    'teamBasesPanel': 'Захоплення баз',
    'debugPanel': 'FPS і пінг',
    'battleDamageLogPanel': 'Журнал шкоди',
    'damageInfoPanel': 'Індикатори шкоди',
    'ribbonsPanel': 'Бойові відзнаки',
    'timersPanel': 'Бойові таймери',
    'sixthSense': 'Шосте чуття',
    'battleEndWarningPanel': 'Попередження про кінець бою',
    'battleHintPanel': 'Бойові підказки',
    'situationIndicators': 'Індикатори стану',
    'calloutPanel': 'Команди зв’язку',
    'battleNotifier': 'Сповіщення',
    'dualGunPanel': 'Індикатор двох гармат',
    'widgetPanel': 'Індикатори механік машини',
    'siegeModeIndicator': 'Облоговий режим',
    'postmortemPanel': 'Панель спостереження',
    'spectatorView': 'Панель союзника',
    'battleHint': 'Підказка клавіш',
    'newbieHint': 'Підказка для новачка',
    'mapInfoTip': 'Інформація про мапу',
    'decorativeCrosshairPanel': 'Індикатори біля прицілу',
}
ALWAYS_VISIBLE = frozenset((
    'allies', 'enemies', 'panelSwitch', 'minimap', 'damagePanel', 'consumablesPanel',
    'battleMessenger', 'battleTimer', 'fragCorrelationBar', 'debugPanel',
))
MIN_EDGE = 24
HIT_EDGE = 12
POSTMORTEM_LIMIT = (0.65, 0.42)


def valid_rect(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4
            and all(isinstance(number, (int, float)) and not isinstance(number, bool)
                    and -2 <= number <= 3 and not math.isnan(number) for number in value)
            and value[2] > 0 and value[3] > 0)


def valid_preset(key, value):
    return valid_rect(value) and (key != 'postmortemPanel' or
                                  all(size <= limit for size, limit in zip(value[2:], POSTMORTEM_LIMIT)))


def load(path=PATH):
    value = read_json(path)
    elements = value.get('elements', {})
    if not isinstance(elements, dict):
        elements = {}
    return {
        'elements': {
            key: {mode: list(rect) for mode, rect in saved.items()
                  if mode in ('normal', 'top') and valid_preset(key, rect)}
            for key, saved in elements.items()
            if isinstance(saved, dict)
        },
        'top': [key for key in TEAMS if key in value.get('top', [])]
        if isinstance(value.get('top'), list) else [],
    }


def reset(key, path=PATH):
    state = load(path)
    if key == '*':
        state = {'elements': {}, 'top': []}
    elif key in state['elements'] or key in TEAMS:
        state['elements'].pop(key, None)
        state['top'] = [team for team in state['top'] if team != key]
    else:
        raise ValueError('Налаштування цього елемента вже скинуто.')
    write_json(path, state)


def actions(path=PATH):
    state = load(path)
    changed = set(state['top']) | {key for key, saved in state['elements'].items() if saved}
    fields = [dict(key='*', label='Усі елементи', kind='reset', disabled=not changed)]
    for ids, title in ((ALWAYS_VISIBLE, 'Постійно на екрані'),
                       ((set(ELEMENTS) | changed) - ALWAYS_VISIBLE, 'З’являються за потреби')):
        fields.append(dict(kind='section', label=title))
        fields.extend(dict(key=key, label=ELEMENTS.get(key, key), kind='reset', disabled=key not in changed)
                      for key in sorted(ids, key=lambda key: (key not in changed, ELEMENTS.get(key, key))))
    return fields


def inside(rect, x, y, padding=0):
    left, top, width, height = rect
    return left - padding <= x <= left + width + padding and top - padding <= y <= top + height + padding


def edges(rect, x, y):
    left, top, width, height = rect
    pad_x, pad_y = min(HIT_EDGE, width / 3.0), min(HIT_EDGE, height / 3.0)
    dx, dy = x - left, y - top
    return ((-1 if dx <= pad_x else 1 if dx >= width - pad_x else 0),
            (-1 if dy <= pad_y else 1 if dy >= height - pad_y else 0))


def clip_rect(rect, screen, minimum=MIN_EDGE):
    u, v, width, height = rect
    sw, sh = screen
    width, height = min(sw, max(minimum, width)), min(sh, max(minimum, height))
    return max(0, min(u, sw - width)), max(0, min(v, sh - height)), width, height


def adjust(rect, grip, dx, dy, screen, minimum, maximum=None):
    x, y, width, height = rect
    horizontal, vertical = grip
    if grip == (0, 0):
        return clip_rect((x + dx, y + dy, width, height), screen, 1)
    right, bottom = x + width, y + height
    sw, sh = screen
    max_width, max_height = maximum or screen
    if horizontal == -1:
        x = max(0, right - max_width, min(right - min(minimum, width), x + dx))
    elif horizontal == 1:
        right = min(sw, x + max_width, max(x + min(minimum, width), right + dx))
    if vertical == -1:
        y = max(0, bottom - max_height, min(bottom - min(minimum, height), y + dy))
    elif vertical == 1:
        bottom = min(sh, y + max_height, max(y + min(minimum, height), bottom + dy))
    return x, y, right - x, bottom - y


def normalize(rect, screen):
    return [round(float(value) / axis, 7) for value, axis in zip(rect, screen * 2)]


def denormalize(rect, screen):
    return clip_rect(tuple(value * axis for value, axis in zip(rect, screen * 2)), screen, 1)
