import imp
import marshal
import math
import os
import shutil
import tempfile
from collections import namedtuple
import sys
import types
import unittest
from zipfile import ZipFile


class Simulation(object):
    def __init__(self):
        self.now = 0.0
        self.pending = []
        self.player = None

    def time(self):
        return self.now

    def callback(self, delay, function):
        self.pending.append((self.now + delay, function))
        return len(self.pending)

    def run(self, frames, fps=180.0):
        for frame in range(1, frames + 1):
            self.now = frame / fps
            queued, self.pending = self.pending, []
            for deadline, function in queued:
                if deadline <= self.now + 1e-9:
                    function()
                else:
                    self.pending.append((deadline, function))


class VehicleGunRotator(object):
    __ROTATION_TICK_LENGTH = 0.1
    __INSUFFICIENT_TIME_DIFF = 0.02
    __MAX_TIME_DIFF = 0.2
    USE_LOCK_PREDICTION = True

    def __init__(self, simulation, mode='sniper', client_mode=True):
        self._avatar = types.ModuleType('Avatar')
        self._avatar.inputHandler = types.ModuleType('InputHandler')
        self._avatar.inputHandler.ctrlModeName = mode
        self._avatar.inputHandler.getAimingMode = lambda setting: False
        self._avatar.inputHandler.isObserverFPV = False
        self._avatar.isObserver = lambda: False
        self._avatar.vehicleTypeDescriptor = types.ModuleType('VehicleType')
        self._avatar.vehicleTypeDescriptor.isHullAimingAvailable = False
        self._avatar.gunRotator = self
        simulation.player = self._avatar
        self.simulation = simulation
        self.clientMode = self.__clientMode = client_mode
        self.__time = -0.1
        self.__fixedShotAngles = None
        self.__targetLastShotPoint = False
        self.__shotPointSourceFunctor = simulation.time
        self.local = []
        self.server = []

    def __updateShotPointOnServer(self, shot_point):
        self.server.append((self.simulation.now, shot_point))

    def updateRotationAndGunMarker(self, shot_point, elapsed):
        self.local.append((self.simulation.now, shot_point, elapsed, self.__ROTATION_TICK_LENGTH))

    def predictLockedTargetShotPoint(self):
        return None

    def __getShotPosition(self, yaw, pitch):
        return 0.0, None


class Point(namedtuple('Point', 'x z')):
    y = 0.0

    def __add__(self, other):
        return Point(self.x + other.x, self.z + other.z)

    def __sub__(self, other):
        return Point(self.x - other.x, self.z - other.z)

    def __mul__(self, scale):
        return Point(self.x * scale, self.z * scale)

    def dot(self, other):
        return self.x * other.x + self.z * other.z


class Matrix(object):
    def __init__(self, source=None):
        self.translation = getattr(source, 'translation', source) or Point(0, 0)

    def applyPoint(self, point):
        return self.translation + point


class MatrixProduct(object):
    @property
    def translation(self):
        return self.b.applyPoint(self.a.translation)


class Animation(object):
    def __init__(self, origin=None):
        self.keyframes = ((0.0, Matrix(origin)),)
        self.time = 0.0

    @property
    def translation(self):
        for (start_time, start), (end_time, end) in zip(self.keyframes, self.keyframes[1:]):
            if self.time < end_time:
                fraction = (self.time - start_time) / (end_time - start_time)
                return start.translation + (end.translation - start.translation) * fraction
        return self.keyframes[-1][1].translation


class GunMarkerController(object):
    def __init__(self, origin, marker_type=1):
        self._gunMarkerType = marker_type
        self._dataProvider = DisplayProvider()
        self._dataProvider.positionMatrixProvider = Animation(origin)


class DisplayProvider(object):
    def __init__(self):
        self.sizeConstraint = (32.0, 1440.0)
        self.sizes = None

    def setStartSizes(self, size, offset):
        self.sizes = size, offset

    def updateSizes(self, size, offset, duration, inertness):
        self.sizes = size, offset


class DefaultGunMarkerController(GunMarkerController):
    _DefaultGunMarkerController__offsetInertness = 1.0

    def update(self, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime):
        self._updateMatrixProvider(gunMarkerInfo.position, relaxTime)
        size = gunMarkerInfo.dualAccSize if markerType == MARKER_TYPES.DUAL_ACC else gunMarkerInfo.size
        self._dataProvider.updateSizes(size, 0, relaxTime, 1.0)

    def getSizes(self):
        return self._dataProvider.sizes


class DefaultGunMarkerComponent(object):
    def __init__(self, marker):
        self._dataProvider = marker._dataProvider
        self._markerType = marker._gunMarkerType
        self._view = self
        self.display = None

    def setDataProvider(self, provider):
        self.display = provider

    def _setupDataProvider(self):
        self._view.setDataProvider(self._dataProvider)


class SPGGunMarkerController(GunMarkerController):
    def __init__(self, origin, marker_type=1):
        GunMarkerController.__init__(self, origin, marker_type)
        self._dataProvider.relaxTime = 0.1
        self._dataProvider.setRelaxTime = self._set_relax_time
        self.updates = []
        self.disabled = False

    def _set_relax_time(self, value):
        self._dataProvider.relaxTime = value

    def update(self, markerType, gunMarkerInfo, supportMarkersInfo, relaxTime):
        self.updates.append(relaxTime)
        self._updateMatrixProvider(gunMarkerInfo.position, relaxTime)

    def disable(self):
        self.disabled = True


class SniperCamera(object):
    def __init__(self, zoom):
        self._cfg = dict(sensitivity=0.005, keySensitivity=0.01, scrollSensitivity=0.0025,
                         horzInvert=False, vertInvert=False)
        self.__zoom = zoom
        self.__autoUpdateDxDyDz = self.__aimingSystem = self
        self.movement = []
        self.keyboard = []
        self.wheel = []

    def set(self, dx, dy, dz):
        self.keyboard.append((dx, dy, dz))

    def handleMovement(self, yaw, pitch):
        self.movement.append((yaw, pitch))

    def __setupZoom(self, dz):
        self.wheel.append(dz)


class ArcadeCamera(object):
    def __init__(self):
        self._cfg = dict(sensitivity=0.0025)
        self._userCfg = dict(sensitivity=1.0)
        self.__sensitivity = None
        self.calls = []

    def update(self, dx, dy, dz, rotateMode=True, zoomMode=True, updatedByKeyboard=False):
        self.calls.append((dx, dy, dz, rotateMode, zoomMode, updatedByKeyboard))


def load_method(archive, file_name, class_name, name, globals_):
    module = marshal.loads(archive.read('scripts/client/' + file_name)[8:])
    owner = module
    if class_name is not None:
        owner = next(code for code in module.co_consts if isinstance(code, types.CodeType)
                     and code.co_name == class_name)
    function = next(code for code in owner.co_consts if isinstance(code, types.CodeType)
                    and code.co_name == name)
    return types.FunctionType(function, globals_)


def make_module(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


SIMULATION = Simulation()
BIG_WORLD = make_module('BigWorld')
REPLAY = make_module('BattleReplay')
REPLAY.g_replayCtrl = types.ModuleType('ReplayController')
REPLAY.g_replayCtrl.isRecording = False
REPLAY.g_replayCtrl.isPlaying = False
REPLAY.g_replayCtrl.getGunRotatorTargetPoint = SIMULATION.time
REPLAY.g_replayCtrl.resetUpdateGunOnTimeWarp = lambda: None
SETTINGS = make_module('constants', SERVER_TICK_LENGTH=0.1)
SETTINGS.AIMING_MODE = types.ModuleType('AimingMode')
SETTINGS.AIMING_MODE.TARGET_LOCK = 1
MATH = make_module('Math', Matrix=Matrix, MatrixProduct=MatrixProduct, MatrixAnimation=Animation,
                   Vector3=lambda x, y, z: Point(x, z))
make_module('GUI', screenResolution=lambda: (2560, 1440), WGGunMarkerDataProvider=DisplayProvider)
PROJECTION = types.ModuleType('Projection')
BIG_WORLD.projection = lambda: PROJECTION
MARKER_TYPES = make_module('aih_constants').GUN_MARKER_TYPE = types.ModuleType('GunMarkerType')
MARKER_TYPES.CLIENT, MARKER_TYPES.SERVER, MARKER_TYPES.DUAL_ACC = 1, 2, 3
MOD = None
ORIGINAL = None


class PrecisionTest(unittest.TestCase):
    def setUp(self):
        SIMULATION.__init__()
        REPLAY.g_replayCtrl.isPlaying = False
        BIG_WORLD.time = SIMULATION.time
        BIG_WORLD.callback = SIMULATION.callback
        BIG_WORLD.player = lambda: SIMULATION.player
        view = types.ModuleType('Camera')
        view.position, view.direction = Point(0, 0), Point(0, 1)
        view.matrix = Matrix(Point(0, 0))
        view.invViewMatrix = Matrix(Point(0, 0))
        BIG_WORLD.camera = lambda: view
        BIG_WORLD.InvViewMatrix = lambda: view.invViewMatrix
        if MOD is not None:
            temp_dir = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, temp_dir)
            MOD._CONFIG_PATH = os.path.join(temp_dir, 'config.json')
            MOD.init()

    def tearDown(self):
        if MOD is not None:
            MOD.fini()
        self.assertIs(VehicleGunRotator._VehicleGunRotator__onTick.im_func, ORIGINAL)
        self.assertNotIn('_updateMatrixProvider', DefaultGunMarkerController.__dict__)
        self.assertIs(GunMarkerController._updateMatrixProvider.im_func, ORIGINAL_ANIMATION)
        self.assertIs(SPGGunMarkerController.update.im_func, ORIGINAL_SPG_UPDATE)
        self.assertIs(SPGGunMarkerController.disable.im_func, ORIGINAL_SPG_DISABLE)
        self.assertIs(SniperCamera.update.im_func, ORIGINAL_SNIPER_UPDATE)
        self.assertIs(ArcadeCamera.update.im_func, ORIGINAL_ARCADE_UPDATE)

    def _write_config(self, text):
        if MOD is None:
            return
        MOD.fini()
        with open(MOD._CONFIG_PATH, 'w') as config:
            config.write(text)
        MOD.init()

    def test_manual_marker_updates_with_finer_time_steps(self):
        for mode in ('arcade', 'sniper'):
            SIMULATION.__init__()
            rotator = VehicleGunRotator(SIMULATION, mode=mode)
            rotator._VehicleGunRotator__onTick()
            SIMULATION.run(90)
            self.assertGreaterEqual(len(rotator.local), 80)
            self.assertLess(max(item[2] for item in rotator.local[1:]), 0.019)
            self.assertTrue(all(item[0] == item[1] for item in rotator.local))
            self.assertTrue(all(item[3] < 0.02 for item in rotator.local))

    def test_server_keeps_vanilla_tick_cadence(self):
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(180)
        self.assertEqual([round(item[0], 6) for item in rotator.server],
                         [item / 10.0 for item in range(11)])

    def test_replay_uses_vanilla_tick(self):
        REPLAY.g_replayCtrl.isPlaying = True
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)
        self.assertTrue(all(item[3] == 0.1 for item in rotator.local))

    def test_artillery_ticks_with_frames(self):
        for mode in ('strategic', 'arty'):
            SIMULATION.__init__()
            rotator = VehicleGunRotator(SIMULATION, mode=mode)
            rotator._VehicleGunRotator__onTick()
            SIMULATION.run(90)
            self.assertGreaterEqual(len(rotator.local), 80)
            self.assertLess(max(item[2] for item in rotator.local[1:]), 0.019)
            server_times = [item[0] for item in rotator.server]
            self.assertTrue(all(b - a >= 0.1 - 1e-9 for a, b in zip(server_times, server_times[1:])))

    def test_target_lock_ticks_with_frames(self):
        rotator = VehicleGunRotator(SIMULATION)
        rotator._avatar.inputHandler.getAimingMode = lambda setting: True
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertGreaterEqual(len(rotator.local), 80)
        self.assertLess(max(item[2] for item in rotator.local[1:]), 0.019)
        server_times = [item[0] for item in rotator.server]
        self.assertTrue(all(b - a >= 0.1 - 1e-9 for a, b in zip(server_times, server_times[1:])))

    def test_artillery_config_keeps_vanilla_tick(self):
        self._write_config('{"enabled": true, "artillery": false}')
        rotator = VehicleGunRotator(SIMULATION, mode='strategic')
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)

    def test_target_lock_config_keeps_vanilla_tick(self):
        self._write_config('{"enabled": true, "target_lock": false}')
        rotator = VehicleGunRotator(SIMULATION)
        rotator._avatar.inputHandler.getAimingMode = lambda setting: True
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)

    def test_artillery_marker_is_interpolated(self):
        marker = SPGGunMarkerController(Point(5.0, 10.0))
        marker._updateMatrixProvider(Matrix(Point(6.0, 10.0)), 0.1)
        animation = marker._dataProvider.positionMatrixProvider
        self.assertEqual(len(animation.keyframes), 9)
        animation.time = 0.05
        self.assertEqual(animation.translation, Point(5.5, 10.0))

    def test_artillery_marker_drops_the_engine_relax(self):
        marker = SPGGunMarkerController(Point(5.0, 10.0))
        info = types.ModuleType('GunMarkerInfo')
        info.position = Matrix(Point(6.0, 10.0))
        MOD._state['animation'] = 0.00833
        try:
            marker.update(MARKER_TYPES.CLIENT, info, (), 0.00417)
        finally:
            MOD._state['animation'] = None
        self.assertAlmostEqual(marker._dataProvider.relaxTime, 0.00833)
        marker.disable()
        self.assertEqual(marker._dataProvider.relaxTime, SETTINGS.SERVER_TICK_LENGTH)

    def test_server_artillery_marker_keeps_the_engine_relax(self):
        marker = SPGGunMarkerController(Point(5.0, 10.0), MARKER_TYPES.SERVER)
        info = types.ModuleType('GunMarkerInfo')
        info.position = Matrix(Point(6.0, 10.0))
        MOD._state['animation'] = 0.00833
        try:
            marker.update(MARKER_TYPES.SERVER, info, (), 0.1)
        finally:
            MOD._state['animation'] = None
        self.assertEqual(marker._dataProvider.relaxTime, 0.1)

    def test_server_mode_is_not_accelerated(self):
        rotator = VehicleGunRotator(SIMULATION, client_mode=False)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertFalse(rotator.local)
        self.assertFalse(rotator.server)
        self.assertAlmostEqual(SIMULATION.pending[0][0], 0.6)

    def test_unsupported_mode_restores_vanilla_timing(self):
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(4)
        rotator._avatar.inputHandler.ctrlModeName = 'postmortem'
        SIMULATION.run(30)
        self.assertEqual(rotator.local[-1][3], 0.1)
        server_times = [item[0] for item in rotator.server]
        self.assertTrue(all(b - a >= 0.1 - 1e-9 for a, b in zip(server_times, server_times[1:])))

    def test_marker_crosses_depth_change_in_screen_space(self):
        for start_depth, end_depth in ((10.0, 700.0), (700.0, 10.0)):
            marker = SPGGunMarkerController(Point(0.5 * start_depth, start_depth))
            destination = Matrix(Point(0.6 * end_depth, end_depth))
            marker._updateMatrixProvider(destination, 0.1)
            animation = marker._dataProvider.positionMatrixProvider
            for step in range(5):
                animation.time = 0.025 * step
                point = animation.translation
                self.assertAlmostEqual(point.x / point.z, 0.5 + 0.025 * step)
            self.assertIs(animation.keyframes[-1][1], destination)

    def test_marker_position_on_flat_surface_is_preserved(self):
        marker = SPGGunMarkerController(Point(5.0, 10.0))
        marker._updateMatrixProvider(Matrix(Point(6.0, 10.0)), 0.1)
        animation = marker._dataProvider.positionMatrixProvider
        self.assertEqual(len(animation.keyframes), 9)
        animation.time = 0.05
        self.assertEqual(animation.translation, Point(5.5, 10.0))

    def test_marker_carries_velocity_between_updates(self):
        marker = SPGGunMarkerController(Point(5.0, 10.0))
        marker._updateMatrixProvider(Matrix(Point(15.0, 10.0)), 0.1)
        animation = marker._dataProvider.positionMatrixProvider
        animation.time = 0.1
        marker._updateMatrixProvider(Matrix(Point(16.0, 10.0)), 0.1)
        animation = marker._dataProvider.positionMatrixProvider
        animation.time = 0.025
        self.assertAlmostEqual(animation.translation.x, 15.53125)
        animation.time = 0.05
        self.assertAlmostEqual(animation.translation.x, 15.75)
        animation.time = 0.1
        self.assertEqual(animation.translation, Point(16.0, 10.0))
        positions = [frame[1].translation.x for frame in animation.keyframes]
        self.assertEqual(positions, sorted(positions))
        self.assertLessEqual(max(positions), 16.0)

    def test_server_marker_and_immediate_resets_use_vanilla_animation(self):
        for marker_type, duration in ((MARKER_TYPES.SERVER, 0.1), (MARKER_TYPES.CLIENT, 0.0)):
            marker = DefaultGunMarkerController(Point(5.0, 10.0), marker_type)
            marker._updateMatrixProvider(Matrix(Point(420.0, 700.0)), duration)
            self.assertEqual(len(marker._dataProvider.positionMatrixProvider.keyframes), 2)

    def test_disabled_config_keeps_vanilla_behavior(self):
        self._write_config('{"enabled": false}')
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)

    def test_single_mouse_count_stays_below_one_pixel(self):
        VehicleGunRotator(SIMULATION)
        self._write_config('{"fine_mouse": true}')
        for zoom in (2, 4, 8, 16, 25):
            PROJECTION.fov = math.radians(120.0 / (19.0 / 12)) / zoom
            camera = SniperCamera(zoom)
            camera._cfg['horzInvert'] = True
            camera.update(1, 1, 0)
            yaw, pitch = camera.movement[-1]
            pixels = math.tan(abs(yaw)) * 720 / math.tan(PROJECTION.fov / 2)
            self.assertGreater(pixels, 0)
            self.assertLess(pixels * math.sqrt(2), 1.0)
            self.assertAlmostEqual(-yaw, pitch)

    def test_large_mouse_moves_and_non_mouse_inputs_keep_stock_values(self):
        VehicleGunRotator(SIMULATION)
        PROJECTION.fov = math.radians(38.0)
        camera = SniperCamera(2)
        camera.update(10, -6, 1)
        self.assertEqual(camera.movement[-1], (0.025, -0.015))
        self.assertEqual(camera.wheel[-1], 1)
        camera.update(1, 2, 0, updatedByKeyboard=True)
        self.assertEqual(camera.keyboard[-1], (1, 2, 0))
        self.assertEqual(len(camera.movement), 1)

    def test_arcade_precision_uses_active_camera_gain(self):
        VehicleGunRotator(SIMULATION, mode='arcade')
        self._write_config('{"fine_mouse": true}')
        PROJECTION.fov = math.radians(65.0)
        camera = ArcadeCamera()
        camera._ArcadeCamera__sensitivity = 0.008
        camera._userCfg['sensitivity'] = 0.5
        camera.update(1, -1, 0)
        dx, dy = camera.calls[-1][:2]
        self.assertGreater(dx, 0)
        self.assertAlmostEqual(dx, -dy)
        self.assertLess(dx * 0.004 * 720 / math.tan(PROJECTION.fov / 2), 0.7)
        camera.update(1, -1, 0, rotateMode=False)
        self.assertEqual(camera.calls[-1][:2], (1, -1))

    def test_mouse_precision_can_be_disabled(self):
        VehicleGunRotator(SIMULATION)
        PROJECTION.fov = math.radians(38.0)
        self._write_config('{"fine_mouse": false}')
        camera = SniperCamera(2)
        camera.update(1, 0, 0)
        self.assertEqual(camera.movement[-1], (0.0025, 0.0))

    def test_display_position_is_camera_relative_and_raw_position_is_preserved(self):
        VehicleGunRotator(SIMULATION)
        marker = DefaultGunMarkerController(Point(0, 10))
        component = DefaultGunMarkerComponent(marker)
        component._setupDataProvider()
        info = types.ModuleType('GunMarkerInfo')
        info.position, info.size = Matrix(Point(0, 10)), 64.0
        marker.update(MARKER_TYPES.CLIENT, info, (), 0.1)
        view = BIG_WORLD.camera()
        view.matrix.translation = Point(-1, 0)
        view.invViewMatrix.translation = Point(1, 0)
        rendered = component.display.positionMatrixProvider.translation
        self.assertAlmostEqual((rendered.x - 1) / rendered.z, 0.0)
        self.assertEqual(marker._dataProvider.positionMatrixProvider.translation, Point(0, 10))

    def test_display_smooths_a_rapid_reversal_in_both_circles(self):
        VehicleGunRotator(SIMULATION)
        info = types.ModuleType('GunMarkerInfo')
        info.size, info.dualAccSize = 88.0, 58.0
        for kind, diameter in ((MARKER_TYPES.CLIENT, 88.0), (MARKER_TYPES.DUAL_ACC, 58.0)):
            marker = DefaultGunMarkerController(Point(0, 10), kind)
            component = DefaultGunMarkerComponent(marker)
            component._setupDataProvider()
            info.position = Matrix(Point(0, 10))
            marker.update(kind, info, (), 0.005)
            info.position = Matrix(Point(0.1, 10))
            marker.update(kind, info, (), 0.005)
            position = component.display.positionMatrixProvider
            position.a.time = 1.0 / 120
            progress = position.translation.x / position.translation.z
            self.assertGreater(progress, 0)
            self.assertLess(progress, 0.005)
            self.assertEqual(component.display.sizes, (diameter, 0))
            info.position = Matrix(Point(0, 10))
            marker.update(kind, info, (), 0.005)
            self.assertAlmostEqual(position.translation.x / position.translation.z, progress)
            position.a.time = 0.1
            self.assertAlmostEqual(position.translation.x / position.translation.z, 0.0)


if __name__ == '__main__':
    stock_globals = dict(BigWorld=BIG_WORLD, BattleReplay=REPLAY, AIMING_MODE=SETTINGS.AIMING_MODE,
                         VehicleGunRotator=VehicleGunRotator)
    with ZipFile('res/packages/scripts.pkg') as archive:
        for method in ('__onTick', '__getTimeDiff'):
            setattr(VehicleGunRotator, '_VehicleGunRotator' + method,
                    load_method(archive, 'VehicleGunRotator.pyc', 'VehicleGunRotator', method, stock_globals))
        stock_animation = load_method(archive, 'AvatarInputHandler/gun_marker_ctrl.pyc', '_GunMarkerController',
                                      '_updateMatrixProvider', dict(Math=MATH))
        stock_animation.func_defaults = (0.0,)
        GunMarkerController._updateMatrixProvider = stock_animation
        base = 'AvatarInputHandler/DynamicCameras/'
        calc_delta = load_method(archive, base + '__init__.pyc', None, 'calcYawPitchDelta', {})
        SniperCamera._SniperCamera__rotateAndZoom = load_method(
            archive, base + 'SniperCamera.pyc', 'SniperCamera', '__rotateAndZoom',
            dict(calcYawPitchDelta=calc_delta))
        sniper_update = load_method(archive, base + 'SniperCamera.pyc', 'SniperCamera', 'update', {})
        sniper_update.func_defaults = (False,)
        SniperCamera.update = sniper_update
    ORIGINAL = VehicleGunRotator._VehicleGunRotator__onTick.im_func
    ORIGINAL_ANIMATION = GunMarkerController._updateMatrixProvider.im_func
    ORIGINAL_SPG_UPDATE = SPGGunMarkerController.update.im_func
    ORIGINAL_SPG_DISABLE = SPGGunMarkerController.disable.im_func
    ORIGINAL_SNIPER_UPDATE = SniperCamera.update.im_func
    ORIGINAL_ARCADE_UPDATE = ArcadeCamera.update.im_func
    make_module('VehicleGunRotator', VehicleGunRotator=VehicleGunRotator)
    make_module('AvatarInputHandler')
    make_module('AvatarInputHandler.DynamicCameras')
    make_module('AvatarInputHandler.DynamicCameras.SniperCamera', SniperCamera=SniperCamera)
    make_module('AvatarInputHandler.DynamicCameras.ArcadeCamera', ArcadeCamera=ArcadeCamera)
    make_module('AvatarInputHandler.gun_marker_ctrl', _GunMarkerController=GunMarkerController,
                _DefaultGunMarkerController=DefaultGunMarkerController,
                _SPGGunMarkerController=SPGGunMarkerController)
    crosshair_package = 'gui.Scaleform.daapi.view.battle.shared.crosshair'
    parts = crosshair_package.split('.')
    for index in range(1, len(parts) + 1):
        make_module('.'.join(parts[:index]), __path__=[])
    make_module(crosshair_package + '.gm_components',
                DefaultGunMarkerComponent=DefaultGunMarkerComponent)
    make_module('debug_utils', LOG_NOTE=lambda *args: None, LOG_WARNING=lambda *args: None)
    if len(sys.argv) > 1 and sys.argv[1] != '--vanilla':
        loader = imp.load_compiled if sys.argv[1].endswith('.pyc') else imp.load_source
        MOD = loader('velet_presicion', sys.argv[1])
    unittest.main(argv=sys.argv[:1])
