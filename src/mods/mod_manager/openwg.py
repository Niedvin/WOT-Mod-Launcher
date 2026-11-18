# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import sys

from .catalog import flag, number


COMMON = 'net.openwg.common'
UPSCALER = 'net.openwg.gpu.upscaler'
SETTINGS = {COMMON: 'openwg_gpu.settings', UPSCALER: 'openwg_gpu_upscaler.settings'}
FPS = (
    ('battleFps', 'FPS у бою', 60, 300),
    ('hangarFps', 'FPS в ангарі', 30, 300),
    ('inactiveWindowFps', 'FPS у фоні', 1, 120),
)
NEURAL = (
    ('preset', 'Профіль', 1, 3, 1),
    ('style', 'Стиль', 0, 2, 1),
    ('passes', 'Кількість проходів', 1, 10, 1),
    ('intensity', 'Сила ефекту', 0, 200, 100),
    ('local_tone', 'Локальний тон', 0, 200, 100),
    ('local_structure', 'Локальна деталізація', 0, 200, 100),
    ('skin_structure', 'Деталізація поверхні', 0, 200, 100),
)


def controller_for(identifier):
    package = sys.modules.get(SETTINGS[identifier])
    return package.get_controller() if package else None


def choice(item, label, disabled=False):
    options = [dict(value=option['data'], label=option['label']) for option in item['options'] if option['data']]
    return dict(key=item['key'], label=label, kind='choice', value=item['value'],
                options=options, disabled=disabled or len(options) < 2)


def fields_for(identifier, controller):
    controls = controller.get_ui_settings()
    if identifier == COMMON:
        fields = []
        for key, label, minimum, maximum in FPS:
            item = controls[key]
            field = number(item['key'], label, item['value'], minimum, maximum, 1, 'FPS')
            fields.append(dict(field, value=item['value'], zero=True))
        latency = controls['latencyTechnology']
        if latency:
            fields.append(dict(flag(latency['key'], latency['label']), value=latency['value']))
        return fields
    neural = controls['neuralRendering']
    blocked = bool(controls['graphicsJournal']['blocked'] and controls['graphicsJournal']['error'])
    fields = [
        choice(controls['upscalerTechnology'], 'Технологія масштабування', disabled=blocked),
        choice(controls['upscalerQuality'], 'Якість масштабування', disabled=blocked),
        dict(flag(neural['key'], 'DLSS Neural Rendering'), value=neural['value'],
             disabled=not neural['supported'] or blocked),
    ]
    if neural['supported']:
        values = controller.get_neural_controls()['values']
        for key, label, minimum, maximum, scale in NEURAL:
            value = values[key]
            field = number('neural:' + key, label, value, minimum, maximum, 1 if scale == 1 else 5,
                           '%' if scale == 100 else '', scale)
            fields.append(dict(field, value=int(round(value * scale)), disabled=blocked))
        fields.append(dict(flag('neural:auto_mask', 'Автоматична маска'), value=values['auto_mask'], disabled=blocked))
    return fields
