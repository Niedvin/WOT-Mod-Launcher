import imp
import marshal
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
    def __add__(self, other):
        return Point(self.x + other.x, self.z + other.z)

    def __sub__(self, other):
        return Point(self.x - other.x, self.z - other.z)

    def __mul__(self, scale):
        return Point(self.x * scale, self.z * scale)

    def dot(self, other):
        return self.x * other.x + self.z * other.z


class Matrix(object):
    def __init__(self, source):
        self.translation = source.translation if hasattr(source, 'translation') else source


class Animation(object):
    def __init__(self, origin):
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
        self._dataProvider = types.ModuleType('MarkerData')
        self._dataProvider.positionMatrixProvider = Animation(origin)


class DefaultGunMarkerController(GunMarkerController):
    pass


def load_method(archive, file_name, class_name, name, globals_):
    module = marshal.loads(archive.read('scripts/client/' + file_name)[8:])
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
MATH = make_module('Math', Matrix=Matrix)
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
        BIG_WORLD.camera = lambda: view
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

    def test_artillery_uses_vanilla_tick(self):
        rotator = VehicleGunRotator(SIMULATION, mode='strategic')
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)

    def test_target_lock_uses_vanilla_tick(self):
        rotator = VehicleGunRotator(SIMULATION)
        rotator._avatar.inputHandler.getAimingMode = lambda setting: True
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)

    def test_server_mode_is_not_accelerated(self):
        rotator = VehicleGunRotator(SIMULATION, client_mode=False)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertFalse(rotator.local)
        self.assertFalse(rotator.server)
        self.assertAlmostEqual(SIMULATION.pending[0][0], 0.6)

    def test_switching_view_restores_vanilla_timing(self):
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(4)
        rotator._avatar.inputHandler.ctrlModeName = 'strategic'
        SIMULATION.run(30)
        self.assertEqual(rotator.local[-1][3], 0.1)
        server_times = [item[0] for item in rotator.server]
        self.assertTrue(all(b - a >= 0.1 - 1e-9 for a, b in zip(server_times, server_times[1:])))

    def test_marker_crosses_depth_change_in_screen_space(self):
        for start_depth, end_depth in ((10.0, 700.0), (700.0, 10.0)):
            marker = DefaultGunMarkerController(Point(0.5 * start_depth, start_depth))
            destination = Matrix(Point(0.6 * end_depth, end_depth))
            marker._updateMatrixProvider(destination, 0.1)
            animation = marker._dataProvider.positionMatrixProvider
            for step in range(5):
                animation.time = 0.025 * step
                point = animation.translation
                self.assertAlmostEqual(point.x / point.z, 0.5 + 0.025 * step)
            self.assertIs(animation.keyframes[-1][1], destination)

    def test_marker_position_on_flat_surface_is_preserved(self):
        marker = DefaultGunMarkerController(Point(5.0, 10.0))
        marker._updateMatrixProvider(Matrix(Point(6.0, 10.0)), 0.1)
        animation = marker._dataProvider.positionMatrixProvider
        self.assertEqual(len(animation.keyframes), 9)
        animation.time = 0.05
        self.assertEqual(animation.translation, Point(5.5, 10.0))

    def test_marker_carries_velocity_between_updates(self):
        marker = DefaultGunMarkerController(Point(5.0, 10.0))
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
        if MOD is not None:
            MOD.fini()
            with open(MOD._CONFIG_PATH, 'w') as config:
                config.write('{"enabled": false}')
            MOD.init()
        rotator = VehicleGunRotator(SIMULATION)
        rotator._VehicleGunRotator__onTick()
        SIMULATION.run(90)
        self.assertEqual(len(rotator.local), 6)


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
    ORIGINAL = VehicleGunRotator._VehicleGunRotator__onTick.im_func
    make_module('VehicleGunRotator', VehicleGunRotator=VehicleGunRotator)
    make_module('AvatarInputHandler')
    make_module('AvatarInputHandler.gun_marker_ctrl', _DefaultGunMarkerController=DefaultGunMarkerController)
    make_module('debug_utils', LOG_NOTE=lambda *args: None, LOG_WARNING=lambda *args: None)
    if len(sys.argv) > 1 and sys.argv[1] != '--vanilla':
        loader = imp.load_compiled if sys.argv[1].endswith('.pyc') else imp.load_source
        MOD = loader('velet_presicion', sys.argv[1])
    unittest.main(argv=sys.argv[:1])
