import errno
import json
import math
import os
from functools import wraps

import BattleReplay
import BigWorld
import Math
from aih_constants import GUN_MARKER_TYPE
from constants import AIMING_MODE, SERVER_TICK_LENGTH
from debug_utils import LOG_NOTE, LOG_WARNING


_CONFIG_PATH = os.path.join('mods', 'configs', 'velet_presicion', 'config.json')
_LOCAL_TICK = 1.0 / 120.0
_MIN_TICK = 1.0 / 240.0
_MAX_TICK = 0.25
_SCHEDULE_LEAD = 0.0005
_MIN_TIME_GAP = 0.0005
_MIN_ANIMATION = 0.002
_MARKER_SEGMENTS = 8
_MAX_SPEED_RATIO = 3.0
_ROTATION_TICK = '_VehicleGunRotator__ROTATION_TICK_LENGTH'
_MIN_TIME_DIFF = '_VehicleGunRotator__INSUFFICIENT_TIME_DIFF'
_ON_TICK = '_VehicleGunRotator__onTick'
_UPDATE_SERVER = '_VehicleGunRotator__updateShotPointOnServer'
_TICK_TIME = '_velet_tick_time'
_SPAN_STATE = '_velet_span'
_MISSING = object()
_hooks = []
_state = {'animation': None}


def _is_enabled():
    try:
        with open(_CONFIG_PATH, 'r') as config_file:
            config = json.load(config_file)
        if isinstance(config, dict) and isinstance(config.get('enabled'), bool):
            return config['enabled']
    except IOError as error:
        if error.errno == errno.ENOENT:
            return True
    except ValueError:
        pass
    LOG_WARNING('[Velet Presicion] Invalid configuration, using defaults')
    return True


def _use_local_tick(rotator):
    if not _hooks or BattleReplay.g_replayCtrl.isPlaying or not rotator.clientMode:
        return False
    avatar = rotator._avatar
    handler = avatar.inputHandler
    descriptor = avatar.vehicleTypeDescriptor
    return (
        handler is not None
        and handler.ctrlModeName in ('arcade', 'sniper')
        and not handler.isObserverFPV
        and not avatar.isObserver()
        and descriptor is not None
        and not descriptor.isHullAimingAvailable
        and rotator._VehicleGunRotator__fixedShotAngles is None
        and not handler.getAimingMode(AIMING_MODE.TARGET_LOCK)
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
        if not _hooks or BattleReplay.g_replayCtrl.isPlaying:
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
        if (_hooks and duration >= _MIN_ANIMATION
                and marker._gunMarkerType in (GUN_MARKER_TYPE.CLIENT, GUN_MARKER_TYPE.DUAL_ACC)):
            view = BigWorld.camera()
            if view is not None:
                animation = marker._dataProvider.positionMatrixProvider
                frames = _projected_keyframes(Math.Matrix(animation), positionMatrix, duration, view, marker)
                if frames is not None:
                    animation.keyframes = frames
                    animation.time = 0.0
                    return
        setattr(marker, _SPAN_STATE, None)
        return original(marker, positionMatrix, relaxTime)

    return animate


def init():
    if _hooks or not _is_enabled():
        return
    from AvatarInputHandler.gun_marker_ctrl import _DefaultGunMarkerController
    from VehicleGunRotator import VehicleGunRotator

    targets = (
        (VehicleGunRotator, _UPDATE_SERVER, _wrap_server_update),
        (VehicleGunRotator, _ON_TICK, _wrap_local_tick),
        (_DefaultGunMarkerController, '_updateMatrixProvider', _wrap_marker_animation),
    )
    for owner, name, wrap in targets:
        original = getattr(owner, name).im_func
        _hooks.append((owner, name, owner.__dict__.get(name, _MISSING), wrap(original)))
    for owner, name, original, wrapper in _hooks:
        setattr(owner, name, wrapper)
    LOG_NOTE('[Velet Presicion] Gun marker updates every frame (120 Hz target)')


def fini():
    _state['animation'] = None
    while _hooks:
        owner, name, original, wrapper = _hooks.pop()
        if getattr(owner, name).im_func is wrapper:
            _restore_override(owner, name, original)
