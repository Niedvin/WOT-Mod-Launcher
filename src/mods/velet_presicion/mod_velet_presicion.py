# -*- coding: utf-8 -*-
import errno
import json
import math
import os
from functools import wraps

import BattleReplay
import BigWorld
import GUI
import Keys
import Math
from game import convertKeyEvent
from aih_constants import GUN_MARKER_TYPE
from constants import AIMING_MODE, ARENA_PERIOD, SERVER_TICK_LENGTH
from debug_utils import LOG_NOTE, LOG_WARNING

try:
    from gui.ua_mod_manager.bindings import binding_for
except ImportError:
    def binding_for(identifier, default):
        return default


_CONFIG_PATH = os.path.join('mods', 'configs', 'velet_presicion', 'config.json')
_LOCAL_TICK = 1.0 / 120.0
_MIN_TICK = 1.0 / 240.0
_MAX_TICK = 0.25
_SCHEDULE_LEAD = 0.0005
_MIN_TIME_GAP = 0.0005
_MIN_ANIMATION = 0.002
_MARKER_SEGMENTS = 8
_MAX_SPEED_RATIO = 3.0
_FINE_MOUSE_PIXELS = 0.65
_STOCK_MOUSE_COUNTS = 10.0
_CTRL_MODES = ('arcade', 'sniper')
_ARTY_MODES = ('strategic', 'arty')
_DEFAULTS = {'enabled': True, 'artillery': True, 'target_lock': True, 'fine_mouse': False, 'toggle_key': 'F11'}
_DISPLAY_BLEND = 0.045
_DISPLAY_DEPTH = 50.0
_ROTATION_TICK = '_VehicleGunRotator__ROTATION_TICK_LENGTH'
_MIN_TIME_DIFF = '_VehicleGunRotator__INSUFFICIENT_TIME_DIFF'
_ON_TICK = '_VehicleGunRotator__onTick'
_UPDATE_SERVER = '_VehicleGunRotator__updateShotPointOnServer'
_TICK_TIME = '_velet_tick_time'
_SPAN_STATE = '_velet_span'
_MISSING = object()
_hooks = []
_display_markers = {}
_spg_marker_class = None
_spg_regular_update = None
_state = {'animation': None}
_config = dict(_DEFAULTS)


def _read_config():
    config = dict(_DEFAULTS)
    try:
        with open(_CONFIG_PATH, 'r') as config_file:
            data = json.load(config_file)
    except IOError as error:
        if error.errno != errno.ENOENT:
            LOG_WARNING('[Velet Presicion] Invalid configuration, using defaults')
        return config
    except ValueError:
        LOG_WARNING('[Velet Presicion] Invalid configuration, using defaults')
        return config
    if isinstance(data, dict):
        for key in ('enabled', 'artillery', 'target_lock', 'fine_mouse'):
            value = data.get(key)
            if isinstance(value, bool):
                config[key] = value
        key = data.get('toggle_key')
        if isinstance(key, basestring) and (not key or _bind_code(key) is not None):
            config['toggle_key'] = key
    return config


def _bind_code(name):
    return getattr(Keys, 'KEY_' + name, None) if name else None


def _wrap_key_event(original):
    @wraps(original)
    def handle(handler, event):
        name = binding_for('ua.velet_presicion', _config['toggle_key'])
        key_code = _bind_code(name)
        if key_code is None or BattleReplay.g_replayCtrl.isPlaying:
            return original(handler, event)
        down, key, modifiers, repeat = convertKeyEvent(event)
        key_modifier = {'ALT': 4, 'SHIFT': 1, 'CONTROL': 2}.get(name[1:], 0)
        if key != key_code or modifiers & ~key_modifier:
            return original(handler, event)
        avatar = BigWorld.player()
        rotator = getattr(avatar, 'gunRotator', None)
        if (rotator is None or not rotator.clientMode or avatar.inputHandler is not handler
                or not avatar.isOnArena or avatar.arena.period != ARENA_PERIOD.BATTLE
                or not avatar.isVehicleAlive or avatar.isObserver()
                or not handler.isStarted or handler.isDetached or handler.isObserverFPV
                or handler.ctrlModeName not in _CTRL_MODES + _ARTY_MODES):
            return original(handler, event)
        if down and not repeat:
            rotator.showServerMarker = not rotator.showServerMarker
        return True

    return handle


def _use_local_tick(rotator):
    if not _hooks or BattleReplay.g_replayCtrl.isPlaying or not rotator.clientMode or rotator.showServerMarker:
        return False
    avatar = rotator._avatar
    handler = avatar.inputHandler
    descriptor = avatar.vehicleTypeDescriptor
    if handler is None or descriptor is None:
        return False
    mode = handler.ctrlModeName
    if mode not in _CTRL_MODES and not (_config['artillery'] and mode in _ARTY_MODES):
        return False
    return (
        not handler.isObserverFPV
        and not avatar.isObserver()
        and not descriptor.isHullAimingAvailable
        and rotator._VehicleGunRotator__fixedShotAngles is None
        and (_config['target_lock'] or not handler.getAimingMode(AIMING_MODE.TARGET_LOCK))
    )


def _restore_override(instance, name, value):
    if value is _MISSING:
        delattr(instance, name)
    else:
        setattr(instance, name, value)


def _tick_length(rotator):
    now = BigWorld.time()
    previous = getattr(rotator, _TICK_TIME, None)
    setattr(rotator, _TICK_TIME, now)
    if previous is not None:
        elapsed = now - previous
        if 0.0 < elapsed <= _MAX_TICK:
            return max(elapsed, _MIN_TIME_GAP)
    return _LOCAL_TICK


def _wrap_local_tick(original):
    @wraps(original)
    def tick(rotator):
        if not _use_local_tick(rotator):
            return original(rotator)
        length = _tick_length(rotator)
        old_tick = vars(rotator).get(_ROTATION_TICK, _MISSING)
        old_minimum = vars(rotator).get(_MIN_TIME_DIFF, _MISSING)
        setattr(rotator, _ROTATION_TICK, max(length * 0.5, _MIN_TICK - _SCHEDULE_LEAD))
        setattr(rotator, _MIN_TIME_DIFF, min(_MIN_TIME_GAP, length * 0.25))
        _state['animation'] = length
        try:
            return original(rotator)
        finally:
            _state['animation'] = None
            _restore_override(rotator, _MIN_TIME_DIFF, old_minimum)
            _restore_override(rotator, _ROTATION_TICK, old_tick)

    return tick


def _wrap_server_update(original):
    @wraps(original)
    def update(rotator, shotPoint):
        if not _hooks or BattleReplay.g_replayCtrl.isPlaying or rotator.showServerMarker:
            return original(rotator, shotPoint)
        now = BigWorld.time()
        if now + 1e-6 >= getattr(rotator, '_velet_next_server_tick', 0.0):
            rotator._velet_next_server_tick = now + SERVER_TICK_LENGTH
            return original(rotator, shotPoint)

    return update


def _screen_span(start, target, view):
    delta = target.translation - start.translation
    along = delta.dot(view.direction)
    perpendicular = max(delta.dot(delta) - along * along, 0.0)
    depth = ((start.translation + target.translation) * 0.5 - view.position).dot(view.direction)
    if depth <= 0.0:
        return 0.0
    return math.sqrt(perpendicular) / depth


def _speed_ratio(marker, span, duration):
    previous = getattr(marker, _SPAN_STATE, None)
    setattr(marker, _SPAN_STATE, (span, duration))
    if previous is None or span <= 1e-6:
        return 1.0
    previous_span, previous_duration = previous
    ratio = previous_span * duration / (previous_duration * span)
    return min(max(ratio, 0.0), _MAX_SPEED_RATIO)


def _ease(progress, start_speed):
    return progress * (start_speed + progress * (2.0 - 2.0 * start_speed + progress * (start_speed - 1.0)))


def _projected_keyframes(start, target, duration, view, marker):
    origin = view.position
    forward = view.direction
    start_depth = (start.translation - origin).dot(forward)
    target_depth = (target.translation - origin).dot(forward)
    if min(start_depth, target_depth) <= 0.0:
        return None

    offset = target.translation - start.translation
    speed = _speed_ratio(marker, _screen_span(start, target, view), duration)
    frames = [(0.0, start)]
    for index in xrange(1, _MARKER_SEGMENTS):
        progress = float(index) / _MARKER_SEGMENTS
        eased = _ease(progress, speed)
        weight = eased * start_depth / ((1.0 - eased) * target_depth + eased * start_depth)
        frame = Math.Matrix(target)
        frame.translation = start.translation + offset * weight
        frames.append((duration * progress, frame))
    frames.append((duration, target))
    return tuple(frames)


def _wrap_marker_animation(original):
    @wraps(original)
    def animate(marker, positionMatrix, relaxTime=0.0):
        duration = _state['animation'] or relaxTime
        if (_hooks and isinstance(marker, _spg_marker_class) and duration >= _MIN_ANIMATION
                and marker._gunMarkerType == GUN_MARKER_TYPE.CLIENT
                and not getattr(marker._gunRotator, 'showServerMarker', False)):
            view = BigWorld.camera()
            if view is not None:
                animation = marker._dataProvider.positionMatrixProvider
                frames = _projected_keyframes(Math.Matrix(animation), positionMatrix, duration, view, marker)
                if frames is not None:
                    animation.keyframes = frames
                    animation.time = 0.0
                    return
        setattr(marker, _SPAN_STATE, None)
        result = original(marker, positionMatrix, relaxTime)
        display = _display_markers.get(marker._gunMarkerType)
        if display is not None and display.source is marker._dataProvider:
            display.move(positionMatrix, relaxTime)
        return result

    return animate


class _MarkerDisplay(object):
    def __init__(self, source):
        self.source = source
        self.provider = GUI.WGGunMarkerDataProvider()
        self.animation = Math.MatrixAnimation()
        self.position = Math.MatrixProduct()
        self.position.a = self.animation
        self.position.b = BigWorld.InvViewMatrix()
        self.target = None
        self.size = None
        self.provider.positionMatrixProvider = source.positionMatrixProvider
        self.provider.sizeConstraint = source.sizeConstraint
        self.provider.setStartSizes(source.sizeConstraint[0], 0.0)
        self.move(Math.Matrix(source.positionMatrixProvider), 0.0)

    def move(self, world, relax_time):
        camera = BigWorld.camera()
        if camera is None:
            return
        point = Math.Matrix(camera.matrix).applyPoint(world.translation)
        if point.z <= 0.0:
            self.target = None
            self.provider.positionMatrixProvider = self.source.positionMatrixProvider
            return
        x, y = point.x / point.z, point.y / point.z
        target = (x, y)
        if relax_time > 0.0 and target == self.target:
            return
        end = Math.Matrix()
        end.translation = Math.Vector3(x * _DISPLAY_DEPTH, y * _DISPLAY_DEPTH, _DISPLAY_DEPTH)
        if relax_time > 0.0 and self.target is not None:
            self.animation.keyframes = ((0.0, Math.Matrix(self.animation)), (_DISPLAY_BLEND, end))
        else:
            self.animation.keyframes = ((0.0, end),)
        self.animation.time = 0.0
        if self.target is None:
            self.provider.positionMatrixProvider = self.position
        self.target = target


def _wrap_display_provider(original):
    @wraps(original)
    def setup(component):
        source = component._dataProvider
        kind = component._markerType
        if (_hooks and source is not None and not BattleReplay.g_replayCtrl.isPlaying
                and kind in (GUN_MARKER_TYPE.CLIENT, GUN_MARKER_TYPE.DUAL_ACC)):
            display = _display_markers.get(kind)
            if display is None or display.source is not source:
                try:
                    display = _MarkerDisplay(source)
                except (AttributeError, TypeError, ValueError):
                    LOG_WARNING('[Velet Presicion] Display provider unavailable, using the stock marker')
                    return original(component)
                _display_markers[kind] = display
            return component._view.setDataProvider(display.provider)
        return original(component)

    return setup


def _wrap_default_marker_update(original):
    @wraps(original)
    def update(marker, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime):
        inertness = marker._DefaultGunMarkerController__offsetInertness
        result = original(marker, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime)
        display = _display_markers.get(markerType)
        if display is not None and display.source is marker._dataProvider:
            size, offset = marker.getSizes()
            display.provider.sizeConstraint = display.source.sizeConstraint
            if display.size is None or relaxTime <= 0.001:
                display.provider.setStartSizes(size, offset)
            elif (size, offset) != display.size:
                display.provider.updateSizes(size, offset, max(relaxTime, _DISPLAY_BLEND), inertness)
            display.size = (size, offset)
        return result

    return update


def _wrap_spg_update(original):
    @wraps(original)
    def update(marker, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime):
        global _spg_regular_update
        previous = _spg_regular_update
        _spg_regular_update = marker if relaxTime > 0.001 else None
        try:
            return original(marker, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime)
        finally:
            _spg_regular_update = previous

    return update


def _wrap_spg_geometry(original):
    @wraps(original)
    def update(marker):
        if (type(marker) is not _spg_marker_class or marker._gunMarkerType != GUN_MARKER_TYPE.CLIENT
                or marker._gunRotator is None or not _use_local_tick(marker._gunRotator)):
            return original(marker)
        now = BigWorld.time()
        previous = getattr(marker, '_velet_spg_geometry_time', None)
        # Native update rewinds dot queue; nominal budget = 37 dots per 100 ms — 2026-11-15
        if marker is _spg_regular_update and previous is not None and 0 <= now - previous < SERVER_TICK_LENGTH - 1e-9:
            return
        result = original(marker)
        marker._velet_spg_geometry_time = now
        return result

    return update


def _fine_mouse_gain(dx, dy, radians_per_count):
    counts = max(abs(dx), abs(dy))
    if not 0 < counts < _STOCK_MOUSE_COUNTS or radians_per_count <= 0.0:
        return 1.0
    fov = BigWorld.projection().fov
    height = GUI.screenResolution()[1]
    if not 0.0 < fov < math.pi or height <= 0:
        return 1.0
    radians_per_pixel = 2.0 * math.tan(fov / 2.0) / height
    fine_gain = min(1.0, _FINE_MOUSE_PIXELS * radians_per_pixel / radians_per_count)
    transition = max(0.0, counts - 1.0) / (_STOCK_MOUSE_COUNTS - 1.0)
    return fine_gain + (1.0 - fine_gain) * transition * transition


def _manual_camera_active(mode):
    if not _hooks or not _config['fine_mouse'] or BattleReplay.g_replayCtrl.isPlaying:
        return False
    avatar = BigWorld.player()
    handler = getattr(avatar, 'inputHandler', None)
    rotator = getattr(avatar, 'gunRotator', None)
    return (handler is not None and handler.ctrlModeName == mode and not avatar.isObserver()
            and not getattr(rotator, 'showServerMarker', False))


def _wrap_sniper_mouse(original):
    @wraps(original)
    def update(camera, dx, dy, dz, updatedByKeyboard=False):
        if not updatedByKeyboard and (dx or dy) and _manual_camera_active('sniper'):
            sensitivity = camera._cfg['sensitivity'] / float(camera._SniperCamera__zoom)
            gain = _fine_mouse_gain(dx, dy, sensitivity)
            if gain < 1.0:
                dx *= gain
                dy *= gain
        return original(camera, dx, dy, dz, updatedByKeyboard)

    return update


def _wrap_arcade_mouse(original):
    @wraps(original)
    def update(camera, dx, dy, dz, rotateMode=True, zoomMode=True, updatedByKeyboard=False):
        if rotateMode and not updatedByKeyboard and (dx or dy) and _manual_camera_active('arcade'):
            sensitivity = camera._ArcadeCamera__sensitivity
            if sensitivity:
                sensitivity *= camera._userCfg['sensitivity']
            else:
                sensitivity = camera._cfg['sensitivity']
            gain = _fine_mouse_gain(dx, dy, sensitivity)
            if gain < 1.0:
                dx *= gain
                dy *= gain
        return original(camera, dx, dy, dz, rotateMode, zoomMode, updatedByKeyboard)

    return update


def init():
    global _config, _spg_marker_class
    if _hooks:
        return
    _config = _read_config()
    if not _config['enabled']:
        return
    from AvatarInputHandler import AvatarInputHandler
    from AvatarInputHandler.DynamicCameras.ArcadeCamera import ArcadeCamera
    from AvatarInputHandler.DynamicCameras.SniperCamera import SniperCamera
    from AvatarInputHandler.gun_marker_ctrl import _DefaultGunMarkerController, _GunMarkerController, _SPGGunMarkerController
    from gui.Scaleform.daapi.view.battle.shared.crosshair.gm_components import DefaultGunMarkerComponent
    from VehicleGunRotator import VehicleGunRotator

    _spg_marker_class = _SPGGunMarkerController
    targets = (
        (AvatarInputHandler, 'handleKeyEvent', _wrap_key_event),
        (VehicleGunRotator, _UPDATE_SERVER, _wrap_server_update),
        (VehicleGunRotator, _ON_TICK, _wrap_local_tick),
        (_GunMarkerController, '_updateMatrixProvider', _wrap_marker_animation),
        (_DefaultGunMarkerController, 'update', _wrap_default_marker_update),
        (DefaultGunMarkerComponent, '_setupDataProvider', _wrap_display_provider),
        (_SPGGunMarkerController, 'update', _wrap_spg_update),
        (_SPGGunMarkerController, '_update', _wrap_spg_geometry),
        (ArcadeCamera, 'update', _wrap_arcade_mouse),
        (SniperCamera, 'update', _wrap_sniper_mouse),
    )
    for owner, name, wrap in targets:
        if not hasattr(owner, name):
            continue
        original = getattr(owner, name).im_func
        _hooks.append((owner, name, owner.__dict__.get(name, _MISSING), wrap(original)))
    for owner, name, original, wrapper in _hooks:
        setattr(owner, name, wrapper)
    LOG_NOTE('[Velet Presicion] 1.0.8 marker display active')


def fini():
    _state['animation'] = None
    _display_markers.clear()
    while _hooks:
        owner, name, original, wrapper = _hooks.pop()
        if getattr(owner, name).im_func is wrapper:
            _restore_override(owner, name, original)
