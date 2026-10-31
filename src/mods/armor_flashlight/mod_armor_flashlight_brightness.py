# -*- coding: utf-8 -*-
from __future__ import absolute_import
import json
import os

_CONFIG_DIR = os.path.join('mods', 'configs', 'armor_flashlight')
_CONFIG_PATH = os.path.join(_CONFIG_DIR, 'config.json')

_DEFAULT_CONFIG = {
    'enabled': True,
    'yellow_brightness_multiplier': 1.10,
    'green_brightness_multiplier': 1.50,
    'red_brightness_multiplier': 1.00,
    'radius_multiplier': 1.50,
    'max_distance_multiplier': 1.00
}

_CONFIG = dict(_DEFAULT_CONFIG)
_orig_setSettings = None


def _load_config():
    global _CONFIG
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        if os.path.isfile(_CONFIG_PATH):
            with open(_CONFIG_PATH, 'rb') as fp:
                loaded = json.loads(fp.read())
                if isinstance(loaded, dict):
                    _CONFIG.update(loaded)
        else:
            with open(_CONFIG_PATH, 'wb') as fp:
                fp.write(json.dumps(_DEFAULT_CONFIG, indent=4))
    except Exception:
        try:
            from debug_utils import LOG_CURRENT_EXCEPTION
            LOG_CURRENT_EXCEPTION()
        except Exception:
            pass


def _save_config():
    try:
        if not os.path.isdir(_CONFIG_DIR):
            os.makedirs(_CONFIG_DIR)
        with open(_CONFIG_PATH, 'wb') as fp:
            fp.write(json.dumps(_CONFIG, indent=4))
    except Exception:
        try:
            from debug_utils import LOG_CURRENT_EXCEPTION
            LOG_CURRENT_EXCEPTION()
        except Exception:
            pass


def _init_mods_settings():
    try:
        from gui.modsSettingsApi import g_modsSettingsApi, templates

        def _on_settings_changed(linkage, new_settings):
            if linkage != 'ua.armor_flashlight_brightness':
                return
            if 'enabled' in new_settings:
                _CONFIG['enabled'] = bool(new_settings['enabled'])
            if 'yellow_brightness' in new_settings:
                _CONFIG['yellow_brightness_multiplier'] = float(new_settings['yellow_brightness']) / 100.0
            if 'green_brightness' in new_settings:
                _CONFIG['green_brightness_multiplier'] = float(new_settings['green_brightness']) / 100.0
            if 'red_brightness' in new_settings:
                _CONFIG['red_brightness_multiplier'] = float(new_settings['red_brightness']) / 100.0
            if 'radius_mult' in new_settings:
                _CONFIG['radius_multiplier'] = float(new_settings['radius_mult']) / 100.0
            _save_config()

        template = {
            'modDisplayName': 'Velet Penetration',
            'enabled': bool(_CONFIG.get('enabled', True)),
            'column1': [
                templates.createCheckbox(text='Увімкнути підсвітку ліхтарика', varName='enabled', value=bool(_CONFIG.get('enabled', True))),
                templates.createSlider(text='Яскравість зеленої зони', varName='green_brightness', value=int(float(_CONFIG.get('green_brightness_multiplier', 1.50)) * 100), min=50, max=300, interval=10, format='{{value}}%'),
                templates.createSlider(text='Яскравість жовтої зони', varName='yellow_brightness', value=int(float(_CONFIG.get('yellow_brightness_multiplier', 1.10)) * 100), min=50, max=300, interval=10, format='{{value}}%')
            ],
            'column2': [
                templates.createSlider(text='Яскравість червоної зони', varName='red_brightness', value=int(float(_CONFIG.get('red_brightness_multiplier', 1.00)) * 100), min=50, max=200, interval=10, format='{{value}}%'),
                templates.createSlider(text='Радіус ліхтарика', varName='radius_mult', value=int(float(_CONFIG.get('radius_multiplier', 1.50)) * 100), min=50, max=300, interval=10, format='{{value}}%')
            ]
        }
        saved = g_modsSettingsApi.setModTemplate('ua.armor_flashlight_brightness', template, _on_settings_changed)
        if saved and isinstance(saved, dict):
            _on_settings_changed('ua.armor_flashlight_brightness', saved)
    except Exception:
        pass

    try:
        from gui.modsListApi import g_modsListApi

        def _open_settings():
            try:
                from gui.modsSettingsApi.view import loadView
                from gui.modsSettingsApi import g_modsSettingsApi
                loadView(g_modsSettingsApi)
            except Exception:
                pass

        g_modsListApi.addModification(
            id='ua.armor_flashlight_brightness',
            name='Velet Penetration',
            description='Яскравість ліхтарика пробиття',
            icon='',
            enabled=True,
            login=False,
            lobby=True,
            callback=_open_settings
        )
    except Exception:
        pass


def _scale_brightness(vector_cls, color, mult):
    mult = max(0.0, mult)
    r, g, b = color.x * mult, color.y * mult, color.z * mult
    peak = max(r, g, b)
    if peak > 1.0:
        r, g, b = r / peak, g / peak, b / peak
    return vector_cls(r, g, b, color.w)


def _hooked_setSettings(self):
    _load_config()
    if not _CONFIG.get('enabled', True):
        return _orig_setSettings(self)

    if getattr(self, '_armorFlashlightSingleton', None) is None:
        return _orig_setSettings(self)

    try:
        from Math import Vector4
        from account_helpers.settings_core.settings_constants import ArmorFlashlight, GRAPHICS
        from debug_utils import LOG_NOTE, LOG_CURRENT_EXCEPTION
        from gui.armor_flashlight.config import getConfig

        config = getConfig()
        colorSchemaSetting = self.settingsCore.getSetting(ArmorFlashlight.COLOR_SCHEMA)
        isColorBlind = self.settingsCore.getSetting(GRAPHICS.COLOR_BLIND)
        opacitySetting = self.settingsCore.getSetting(ArmorFlashlight.OPACITY)
        patternSetting = self.settingsCore.getSetting(ArmorFlashlight.FILL)
        resolutionSetting = self.settingsCore.getSetting(ArmorFlashlight.RESOLUTION)

        colors = config.getSchemaColorFloatsByIndex(colorSchemaSetting, isColorBlind)
        notPierced, littlePierced, greatPierced = colors

        y_mult = float(_CONFIG.get('yellow_brightness_multiplier', 1.10))
        g_mult = float(_CONFIG.get('green_brightness_multiplier', 1.50))
        r_mult = float(_CONFIG.get('red_brightness_multiplier', 1.00))

        boosted_not = _scale_brightness(Vector4, notPierced, r_mult)
        boosted_little = _scale_brightness(Vector4, littlePierced, y_mult)
        boosted_great = _scale_brightness(Vector4, greatPierced, g_mult)

        radius_mult = float(_CONFIG.get('radius_multiplier', 1.50))
        dist_mult = float(_CONFIG.get('max_distance_multiplier', 1.00))

        base_radius = config.getDistanceConfigTupleList(config.radiusByDist)
        boosted_radius = [(item[0], item[1] * radius_mult) for item in base_radius]

        base_alpha = config.getDistanceConfigTupleList(config.alphaByDist)
        boosted_alpha = [(item[0] * dist_mult, item[1]) for item in base_alpha]

        self._armorFlashlightSingleton.setSettings(
            opacitySetting,
            (boosted_not, boosted_little, boosted_great),
            config.getPatternByIndex(patternSetting),
            config.textureTilingFactor,
            boosted_alpha,
            boosted_radius,
            config.getDistanceConfigTupleList(config.appearanceDurationByDist),
            config.noiseIntensityMultiplier,
            config.getResolutionDownscaleByIndex(resolutionSetting),
            config.maxSizePercentOfWindow,
            config.borderSmoothness,
            config.aimingCircleAdjustment,
            config.smoothnessInAimingCircleAdjustment
        )
        LOG_NOTE('[ArmorFlashlightBoost] Applied settings: Yellow x%.2f, Green x%.2f, Radius x%.2f' % (
            y_mult, g_mult, radius_mult
        ))
    except Exception:
        try:
            from debug_utils import LOG_CURRENT_EXCEPTION
            LOG_CURRENT_EXCEPTION()
        except Exception:
            pass
        _orig_setSettings(self)


def init():
    global _orig_setSettings
    _load_config()
    try:
        from debug_utils import LOG_NOTE, LOG_CURRENT_EXCEPTION
        from gui.armor_flashlight.battle_controller import ArmorFlashlightBattleController
        _orig_setSettings = ArmorFlashlightBattleController._setSettings
        ArmorFlashlightBattleController._setSettings = _hooked_setSettings
        try:
            import BigWorld
            BigWorld.callback(0.1, _init_mods_settings)
        except Exception:
            _init_mods_settings()
        LOG_NOTE('[ArmorFlashlightBoost] Mod initialized successfully')
    except Exception:
        try:
            from debug_utils import LOG_CURRENT_EXCEPTION
            LOG_CURRENT_EXCEPTION()
        except Exception:
            pass


def fini():
    global _orig_setSettings
    if _orig_setSettings is not None:
        try:
            from gui.armor_flashlight.battle_controller import ArmorFlashlightBattleController
            ArmorFlashlightBattleController._setSettings = _orig_setSettings
            _orig_setSettings = None
        except Exception:
            pass
