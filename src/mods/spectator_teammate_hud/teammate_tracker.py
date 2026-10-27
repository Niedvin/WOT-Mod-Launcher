from __future__ import division
from collections import OrderedDict
import math


class TeammateTracker(object):
    def __init__(self):
        self._reloads = {}
        self._unavailable_reloads = {}
        self._equipments = {}
        self._equipment_snapshots = {}
        self._devices = {}
        self._gun_markers = {}
        self._shell_hints = {}

    def record_reload(self, vehicle_id, current_time, remaining, base, clip_time=None):
        remaining = float(remaining)
        base = float(base)
        if math.isnan(remaining) or math.isinf(remaining):
            return
        if remaining < 0.0:
            self._reloads.pop(vehicle_id, None)
            self._unavailable_reloads[vehicle_id] = float(current_time)
            return
        self._unavailable_reloads.pop(vehicle_id, None)
        if math.isnan(base) or math.isinf(base):
            base = remaining
        self._reloads[vehicle_id] = (float(current_time), float(current_time) + remaining, max(base, remaining), clip_time, True)

    def record_shot(self, vehicle_id, current_time, base_reload, clip_time=None):
        base_reload = float(base_reload)
        if base_reload <= 0.0 or math.isnan(base_reload) or math.isinf(base_reload):
            return
        unavailable = self._unavailable_reloads.get(vehicle_id)
        if unavailable is not None and current_time - unavailable < 0.5:
            return
        previous = self._reloads.get(vehicle_id)
        if previous and previous[4] and previous[1] > current_time and current_time - previous[0] < 0.5:
            return
        self._unavailable_reloads.pop(vehicle_id, None)
        self._reloads[vehicle_id] = (float(current_time), float(current_time) + base_reload, float(base_reload), clip_time, False)

    def record_equipment_used(self, vehicle_id, item_cd, current_time, cooldown):
        self._equipments.setdefault(vehicle_id, {})[item_cd] = (float(current_time), float(cooldown))

    def record_equipment(self, vehicle_id, item_cd, quantity, stage, remaining, total, index, current_time):
        records = self._equipment_snapshots.setdefault(vehicle_id, OrderedDict())
        index = index or 0
        if index <= 0 and item_cd:
            matches = [key[0] for key in records if key[1] == item_cd and key[0] > 0]
            if len(matches) == 1:
                index = matches[0]
        if index > 0:
            for key in list(records):
                if key[0] == index and key[1] != item_cd or key == (0, item_cd):
                    del records[key]
                    if not any(candidate[1] == key[1] for candidate in records):
                        self._equipments.get(vehicle_id, {}).pop(key[1], None)
        records[(index, item_cd)] = (quantity, stage, max(0.0, remaining), max(0.0, total), float(current_time))
        if item_cd:
            self.record_equipment_used(vehicle_id, item_cd, current_time, max(0.0, remaining))

    def replace_equipment(self, vehicle_id, old_item_cd, new_item_cd, quantity, stage, remaining, total, index, current_time):
        records = self._equipment_snapshots.get(vehicle_id, {})
        if not index:
            matches = [key[0] for key in records if key[1] == old_item_cd and key[0] > 0]
            if len(matches) == 1:
                index = matches[0]
        for key in list(records):
            if key[1] == old_item_cd and (not index or key[0] in (0, index)):
                del records[key]
        if not any(key[1] == old_item_cd for key in records):
            self._equipments.get(vehicle_id, {}).pop(old_item_cd, None)
        self.record_equipment(vehicle_id, new_item_cd, quantity, stage, remaining, total, index, current_time)

    def get_equipment_snapshot(self, vehicle_id, current_time):
        result = []
        records = self._equipment_snapshots.get(vehicle_id, OrderedDict()).items()
        for (index, item_cd), (quantity, stage, remaining, total, received) in sorted(records, key=lambda pair: pair[0][0]):
            result.append((index, item_cd, quantity, stage, max(0.0, remaining - max(0.0, current_time - received)), total))
        return result

    def record_device_state(self, vehicle_id, device_name, state):
        self._devices.setdefault(vehicle_id, {})[device_name] = state

    def record_gun_marker(self, vehicle_id, current_time, shot_pos, shot_vec, dispersion_angle):
        self._gun_markers[vehicle_id] = (float(current_time),
                                         tuple(float(shot_pos[index]) for index in range(3)),
                                         tuple(float(shot_vec[index]) for index in range(3)),
                                         float(dispersion_angle))

    def get_server_gun_marker(self, vehicle_id, current_time, max_age=0.3):
        record = self._gun_markers.get(vehicle_id)
        if record is None:
            return None
        age = float(current_time) - record[0]
        if age < 0.0 or age > max_age:
            return None
        return record[1], record[2], record[3]

    def record_shell_hint(self, vehicle_id, shell_cd, current_time):
        if shell_cd:
            self._shell_hints[vehicle_id] = (shell_cd, float(current_time))

    def get_shell_hint(self, vehicle_id):
        record = self._shell_hints.get(vehicle_id)
        return record[0] if record is not None else None

    def get_actual_reload(self, vehicle_id, current_time):
        record = self._reloads.get(vehicle_id)
        if not record:
            return (0.0, 0.0, False, None)
        received, end, base, clip_time, authoritative = record
        remaining = max(0.0, end - received - max(0.0, current_time - received))
        return (remaining, base, remaining > 0.0, clip_time)

    def has_reload(self, vehicle_id):
        return vehicle_id in self._reloads

    def is_reload_estimated(self, vehicle_id):
        record = self._reloads.get(vehicle_id)
        return bool(record and not record[4])

    def get_equipment_cooldown(self, vehicle_id, item_cd, current_time):
        record = self._equipments.get(vehicle_id, {}).get(item_cd)
        return max(0.0, record[1] - max(0.0, current_time - record[0])) if record else 0.0

    def get_devices(self, vehicle_id):
        return dict(self._devices.get(vehicle_id, {}))

    def clear(self):
        self._reloads.clear()
        self._unavailable_reloads.clear()
        self._equipments.clear()
        self._equipment_snapshots.clear()
        self._devices.clear()
        self._gun_markers.clear()
        self._shell_hints.clear()
