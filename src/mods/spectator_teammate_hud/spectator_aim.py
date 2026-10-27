from __future__ import division
import math

try:
    import BigWorld
except ImportError:
    BigWorld = None
try:
    import Math
except ImportError:
    Math = None


def calculate_ray_endpoint(pos, direction, distance=1000.0):
    return tuple(pos[index] + direction[index] * distance for index in range(3))


def calculate_dispersion_radius(dispersion_angle, distance):
    return max(0.0, float(distance) * float(dispersion_angle))


class SpectatorAimManager(object):
    def __init__(self, marker_controller=None, bigworld=None):
        self._marker_controller = marker_controller
        self._bigworld = bigworld
        self._current_vehicle_id = None
        self._is_active = False
        self._direction = None
        self._collision = None
        self._gun_index = None

    def activate(self, vehicle_id):
        if self._is_active and vehicle_id != self._current_vehicle_id:
            self._clear_marker()
        self._current_vehicle_id = vehicle_id
        self._is_active = True

    def deactivate(self):
        self._current_vehicle_id = None
        self._is_active = False

    enable = activate
    disable = deactivate

    def is_active(self):
        return self._is_active

    def set_marker_controller(self, controller):
        self._marker_controller = controller

    def _clear_marker(self):
        self._direction = self._collision = None
        self._gun_index = None
        if self._marker_controller is not None and hasattr(self._marker_controller, 'clear'):
            self._marker_controller.clear()

    def _get_vehicle_matrix(self, vehicle):
        vehicle_filter = getattr(vehicle, 'filter', None)
        bw = self._bigworld or BigWorld
        player = bw.player() if bw is not None else None
        if player is not None and getattr(player, 'isObserver', lambda: False)():
            attached = getattr(player, 'getVehicleAttached', lambda: None)()
            if attached is not None and attached.id == vehicle.id:
                getter = getattr(player, 'getObservedVehicleStabilisedMatrix', None)
                matrix = getter() if getter is not None else getattr(vehicle_filter, 'stabilisedMatrix', None)
                if matrix is not None:
                    return matrix
        matrix = getattr(vehicle_filter, 'bodyMatrix', None)
        return matrix if matrix is not None else vehicle.matrix

    def _get_shot_params(self, vehicle, shot):
        if getattr(vehicle, 'appearance', None) is None or not hasattr(vehicle, 'getAimParams'):
            return None
        descr = vehicle.typeDescriptor
        gun_offset = descr.activeGunShotPosition
        multi_gun = descr.gun.multiGun
        self._gun_index = None
        active_guns = ()
        if getattr(descr, 'isDualgunVehicle', False):
            active_guns = (vehicle.dualGunIndex,)
        elif multi_gun:
            from items.vehicle_mechanics_types import VehicleMechanicKeys
            twin_gun = vehicle.getVehicleMechanicComponent(VehicleMechanicKeys.TWIN_GUN)
            if twin_gun is not None:
                active_guns = twin_gun.getActiveGunIndexes()
        if multi_gun and len(active_guns) == 1:
            gun_index = active_guns[0]
            if gun_index < 0 or gun_index >= len(multi_gun):
                return None
            gun_offset = multi_gun[gun_index].shotPosition
            self._gun_index = gun_index
        turret_yaw, gun_pitch = vehicle.getAimParams()
        body_matrix = self._get_vehicle_matrix(vehicle)
        turret_matrix = Math.Matrix()
        turret_matrix.setRotateY(turret_yaw)
        turret_matrix.translation = descr.hull.turretPositions[0] + descr.chassis.hullPosition
        turret_matrix.postMultiply(Math.Matrix(body_matrix))
        position = turret_matrix.applyPoint(gun_offset)
        gun_matrix = Math.Matrix()
        gun_matrix.setRotateX(gun_pitch)
        gun_matrix.postMultiply(turret_matrix)
        velocity = gun_matrix.applyVector(Math.Vector3(0.0, 0.0, shot.speed))
        return position, velocity

    def _get_shot_descriptor(self, vehicle, shell_hint=None):
        descr = getattr(vehicle, 'typeDescriptor', None)
        shell_cd = getattr(getattr(vehicle, 'ownVehicle', None), 'currentShell', -1)
        if (shell_cd is None or shell_cd < 0) and shell_hint is not None:
            shell_cd = shell_hint
        if shell_cd is not None and shell_cd >= 0:
            for shot in getattr(getattr(descr, 'gun', None), 'shots', ()):
                if shot.shell.compactDescr == shell_cd:
                    return shot
            return None
        return getattr(descr, 'shot', None)

    def get_gun_marker_data(self, vehicle, raycast_distance=1000.0, server_marker=None, shell_hint=None):
        if vehicle is None or not getattr(vehicle, 'inWorld', False) or Math is None:
            return None
        descr = getattr(vehicle, 'typeDescriptor', None)
        if descr is None:
            return None
        from AvatarInputHandler import AimingSystems
        bw = self._bigworld or BigWorld
        player = bw.player()
        if player is None:
            return None
        shot = self._get_shot_descriptor(vehicle, shell_hint)
        if shot is None:
            shot = getattr(descr, 'shot', None)
        if shot is None or shot.speed <= 0.0:
            return None
        if server_marker is not None:
            position = Math.Vector3(*server_marker[0])
            velocity = Math.Vector3(*server_marker[1])
            angle = server_marker[2] if server_marker[2] > 0.0 else descr.gun.shotDispersionAngle
        else:
            transform = self._get_shot_params(vehicle, shot)
            if transform is None:
                return None
            position, velocity = transform
            angle = descr.gun.shotDispersionAngle
            observed = getattr(player, 'observedVehicleData', {}).get(vehicle.id)
            if observed is not None and getattr(observed, 'dispAngle', 0.0) > 0.0:
                angle = observed.dispAngle
        min_bounds, max_bounds = player.arena.getSpaceBB()
        end, self._direction, self._collision, used_max = AimingSystems.getCappedShotTargetInfos(position, velocity, Math.Vector3(0.0, -shot.gravity, 0.0), shot, vehicle.id, min_bounds, max_bounds, AimingSystems.CollisionStrategy.COLLIDE_DYNAMIC_AND_STATIC)
        distance = shot.maxDistance if used_max else math.sqrt(sum((end[index] - position[index]) ** 2 for index in range(3)))
        return tuple(float(value) for value in end), calculate_dispersion_radius(angle, distance)

    def get_dispersion_size(self, vehicle, target_point):
        data = self.get_gun_marker_data(vehicle)
        return data[1] if data else 0.0

    def update_aim(self, vehicle=None, raycast_distance=1000.0, server_marker=None, shell_hint=None, relax_time=0.0):
        if not self._is_active:
            return None
        if vehicle is None or getattr(vehicle, 'id', None) != self._current_vehicle_id:
            self._clear_marker()
            return None
        data = self.get_gun_marker_data(vehicle, raycast_distance, server_marker, shell_hint)
        if data is None:
            self._clear_marker()
            return None
        if self._marker_controller is not None:
            if hasattr(self._marker_controller, 'update_ballistic_marker'):
                self._marker_controller.update_ballistic_marker(data[0], data[1], self._direction, self._collision, relax_time)
            else:
                self._marker_controller.update_marker(*data)
        return data
