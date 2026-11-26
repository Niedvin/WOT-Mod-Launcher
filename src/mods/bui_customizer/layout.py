# -*- coding: utf-8 -*-
from __future__ import division, unicode_literals

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
    'postmortemInfoPage': 'Оцінка бою та кнопки спостереження',
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
MIN_VISIBLE_AREA = 0.15
POSTMORTEM_LIMIT = (0.65, 0.42)
NO_CROP = (0, 0, 0, 0)


def valid_coordinate(number):
    return isinstance(number, (int, float)) and not isinstance(number, bool) and -2 <= number <= 3


def valid_preset(key, value):
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return False
    position, size = tuple(value[:2]), tuple(value[2:])
    if position != (None, None) and not all(map(valid_coordinate, position)):
        return False
    if key == 'consumablesPanel' and size == (None, None):
        return position != (None, None)
    if not all(map(valid_coordinate, size)) or min(size) <= 0:
        return False
    return (key not in ('postmortemPanel', 'postmortemInfoPage') or
            all(length <= limit for length, limit in zip(size, POSTMORTEM_LIMIT)))


def normal_mode(key):
    return 'slots' if key == 'consumablesPanel' else 'normal'


def valid_crop(value):
    return (isinstance(value, (list, tuple)) and len(value) == 4 and
            all(valid_coordinate(cut) and 0 <= cut < 1 for cut in value) and
            value[0] + value[2] < 1 and value[1] + value[3] < 1 and any(value))


def load(path=PATH):
    value = read_json(path)
    elements = value.get('elements', {})
    if not isinstance(elements, dict):
        elements = {}
    return {
        'elements': {
            key: {mode: list(rect) for mode, rect in saved.items()
                  if (mode in (normal_mode(key), 'top') and valid_preset(key, rect) or
                      mode in (normal_mode(key) + 'Crop', 'topCrop') and valid_crop(rect))}
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


def edges(rect, x, y, screen):
    left, top, width, height = rect
    return (edge(left, width, x, screen[0]), edge(top, height, y, screen[1]))


def edge(start, size, pointer, screen_size):
    end = start + size
    overlap = min(end, screen_size) - max(start, 0)
    pad = min(HIT_EDGE, max(0, overlap) / 3.0)
    if start >= 0 and pointer - start <= pad:
        return -1
    if end <= screen_size and end - pointer <= pad:
        return 1
    return 0


def crop_rect(rect, margins):
    x, y, width, height = rect
    left, top, right, bottom = margins
    return x + width * left, y + height * top, width * (1 - left - right), height * (1 - top - bottom)


def adjust_crop(full, start, grip, dx, dy):
    x, y, width, height = full
    left, top, visible_w, visible_h = crop_rect(full, start)
    right, bottom = left + visible_w, top + visible_h
    min_w, min_h = min(MIN_EDGE, visible_w), min(MIN_EDGE, visible_h)
    if grip[0] < 0:
        left = max(x, min(left + dx, right - min_w))
    elif grip[0] > 0:
        right = min(x + width, max(right + dx, left + min_w))
    if grip[1] < 0:
        top = max(y, min(top + dy, bottom - min_h))
    elif grip[1] > 0:
        bottom = min(y + height, max(bottom + dy, top + min_h))
    return tuple(round(cut, 7) for cut in ((left - x) / width, (top - y) / height,
                                           (x + width - right) / width, (y + height - bottom) / height))


def clip_rect(rect, screen, minimum=MIN_EDGE, crop=NO_CROP):
    u, v, width, height = rect
    sw, sh = screen
    width, height = min(sw, max(minimum, width)), min(sh, max(minimum, height))
    left, top, drawn_w, drawn_h = crop_rect((u, v, width, height), crop)
    offset_x = visible_origin(left, drawn_w, sw, top, drawn_h, sh)
    offset_y = visible_origin(top, drawn_h, sh, left, drawn_w, sw)
    return u + offset_x, v + offset_y, width, height


def visible_origin(u, width, sw, v, height, sh):
    visible_x = max(MIN_VISIBLE_AREA, min(1, (u + width) / width, (sw - u) / width))
    visible_y = max(MIN_VISIBLE_AREA, min(1, (v + height) / height, (sh - v) / height))
    scale = math.sqrt(max(1, MIN_VISIBLE_AREA / (visible_x * visible_y)))
    visible_w = min(width, width * visible_x * scale)
    return max(visible_w - width, min(u, sw - visible_w)) - u


def adjust(rect, grip, dx, dy, screen, minimum, maximum=None, proportional=False, crop=NO_CROP):
    x, y, width, height = rect
    horizontal, vertical = grip
    if grip == (0, 0):
        return clip_rect((x + dx, y + dy, width, height), screen, 1, crop)
    max_width, max_height = maximum or screen
    new_width = min(max_width, max(min(minimum, width), width + horizontal * dx))
    new_height = min(max_height, max(min(minimum, height), height + vertical * dy))
    if proportional:
        relative_x, relative_y = new_width / width, new_height / height
        scale = max((relative_x, relative_y), key=lambda factor: abs(factor - 1))
        scale = max(scale, min(1, minimum / min(width, height)))
        scale = min(scale, max_width / width, max_height / height)
        new_width, new_height = width * scale, height * scale
    if horizontal < 0:
        x += width - new_width
    if vertical < 0:
        y += height - new_height
    return clip_rect((x, y, new_width, new_height), screen, 1, crop)


def normalize(rect, screen):
    return [round(float(value) / axis, 7) for value, axis in zip(rect, screen * 2)]


def denormalize(rect, screen, original=None, size_axis=None, align_right=False, crop=NO_CROP):
    width, height = original[2:] if rect[2] is None else (value * axis for value, axis in zip(rect[2:], screen))
    x, y = original[:2] if rect[0] is None else (value * axis for value, axis in zip(rect[:2], screen))
    if size_axis is not None:
        scale = min(height / original[3], screen[0] / original[2], screen[1] / original[3])
        if size_axis == 'fit':
            scale = min(scale, width / original[2])
        new_width, height = original[2] * scale, original[3] * scale
        if align_right:
            x += (original[2] if rect[0] is None else width) - new_width
        width = new_width
    return clip_rect((x, y, width, height), screen, 1, crop)
