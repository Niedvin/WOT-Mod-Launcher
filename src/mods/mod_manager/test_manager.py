from __future__ import unicode_literals

import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
import zipfile

from .manager import Manager, apply_pending, migrate_legacy, scan_packages, switch_packages, write_json


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.pkg = os.path.join(self.root, 'mods', '2.4.1.1')
        self.module_name = 'gui.mods.mod_background_fps_limiter'
        self.commits = []
        os.makedirs(self.pkg)

    def tearDown(self):
        sys.modules.pop(self.module_name, None)
        shutil.rmtree(self.root)

    def package(self, path, identifier):
        path = os.path.join(self.pkg, path)
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('meta.xml', '<root><id>%s</id><name>Sample</name><version>1.0</version></root>' % identifier)
        return path

    def test_restart_switch_groups_duplicate_paths_and_is_reversible(self):
        one = self.package('cache.wotmod', 'net.openwg.fix.battleresultscache')
        two = self.package('openwg/cache.wotmod', 'net.openwg.fix.battleresultscache')
        catalog = scan_packages(self.pkg)
        self.assertEqual(1, len(catalog))
        paths = catalog['net.openwg.fix.battleresultscache']['paths']
        self.assertEqual(2, len(paths))
        switch_packages(paths, False)
        self.assertFalse(os.path.exists(one))
        self.assertTrue(os.path.exists(two + '.manager-off'))
        switch_packages(paths, True)
        self.assertTrue(os.path.exists(one))
        self.assertTrue(os.path.exists(two))

    def test_live_commit_calls_game_and_preserves_additional_data(self):
        identifier = 'ua.background_fps_limiter'
        self.package('fps.wotmod', identifier)
        settings = os.path.join(self.root, 'mods', 'configs', 'background_fps_limiter', 'config.json')
        write_json(settings, {'enabled': True, 'target_fps': 5, 'extension': 'keep'})
        module = types.ModuleType(str(self.module_name))
        module._CONFIG = {'enabled': True, 'target_fps': 5}
        module._update_fps_limit = lambda: self.commits.append(dict(module._CONFIG))
        sys.modules[self.module_name] = module
        manager = Manager(self.root, '2.4.1.1')
        manager.change(identifier, 'target_fps', 9)
        manager.change(identifier, 'enabled', False)
        manager.change(identifier, 'enabled', True)
        self.assertEqual([9, 9, 9], [change['target_fps'] for change in self.commits])
        self.assertEqual([True, False, True], [change['enabled'] for change in self.commits])
        with io.open(settings, encoding='utf-8') as handle:
            self.assertEqual('keep', json.load(handle)['extension'])

    def test_invalid_numeric_value_leaves_setting_alone(self):
        identifier = 'ua.background_fps_limiter'
        self.package('fps.wotmod', identifier)
        manager = Manager(self.root, '2.4.1.1')
        with self.assertRaises(ValueError):
            manager.change(identifier, 'target_fps', 300)
        self.assertFalse(os.path.exists(os.path.join(self.root, 'mods', 'configs', 'background_fps_limiter')))

    def test_hotkey_conflicts_can_be_reassigned_or_cancelled(self):
        velet = 'ua.velet_presicion'
        bui = 'ua.bui_customizer'
        locker = 'ua.appropriate_locker'
        for identifier in (velet, bui, locker):
            self.package(identifier + '.wotmod', identifier)
        manager = Manager(self.root, '2.4.1.1')
        settings = manager.config_path(manager.catalog[velet])
        write_json(settings, {'artillery': False, 'toggle_key': 'F10'})
        self.assertEqual('F10', manager.bindings.value(velet))
        keys = types.ModuleType(str('Keys'))
        keys.KEY_F10, keys.KEY_Q, keys.KEY_W, keys.KEY_RALT, keys.KEY_TAB = 68, 16, 17, 184, 15
        commands = types.ModuleType(str('CommandMapping'))
        player_input = types.ModuleType(str('Input'))

        class Mapping(object):
            _CommandMapping__mapping = {17: [(1, (), True), (2, (29,), True)], 65: [(1, (), True)]}

            def getName(self, command):
                return 'CMD_MOVE_FORWARD' if command == 1 else 'CMD_MOVE_FORWARD_SPEC'

        commands.g_instance = Mapping()
        applied = []
        player_input.setCommandMapping = lambda mapping: applied.append({key: list(actions) for key, actions in mapping.items()})
        modules = dict(Keys=keys, CommandMapping=commands, Input=player_input)
        gui = types.ModuleType(str('gui'))
        gui.ua_bui = types.ModuleType(str('gui.ua_bui'))
        bui_modes = types.ModuleType(str('gui.ua_bui.modes'))
        bui_modes.is_supported_battle = lambda: False
        gui.ua_bui.modes = bui_modes
        modules.update((module.__name__, module) for module in (gui, gui.ua_bui, bui_modes))
        sys.modules.update(modules)
        try:
            offer = manager.bindings.preview(bui, 'Q')
            self.assertEqual([locker], offer['mods'])
            self.assertEqual(offer, manager.bindings.assign(offer))
            self.assertEqual('Q', manager.bindings.value(locker))
            self.assertIsNone(manager.bindings.assign(offer, replace=True))
            self.assertEqual('', manager.bindings.value(locker))
            offer = manager.bindings.preview(velet, 'Q')
            self.assertEqual([bui], offer['mods'])
            self.assertIsNone(manager.bindings.assign(offer, replace=True))
            self.assertEqual('', manager.bindings.value(bui))
            offer = manager.bindings.preview(bui, 'TAB')
            self.assertTrue(offer['conflicts'])
            self.assertFalse(offer['replaceable'])
            self.assertEqual(offer, manager.bindings.assign(offer, replace=True))
            offer = manager.bindings.preview(bui, 'W')
            self.assertEqual(2, len(offer['game']))
            self.assertIsNone(manager.bindings.assign(offer, replace=True))
            manager.bindings.enter_battle()
            self.assertIn(17, commands.g_instance._CommandMapping__mapping)
            self.assertFalse(applied)
            bui_modes.is_supported_battle = lambda: True
            manager.bindings.enter_battle()
            self.assertNotIn(17, applied[-1])
            self.assertIn(65, applied[-1])
            self.assertIn(17, commands.g_instance._CommandMapping__mapping)
            commands.g_instance._CommandMapping__mapping[17].append((3, (), False))
            manager.bindings.leave_battle()
            self.assertEqual(commands.g_instance._CommandMapping__mapping, applied[-1])
            self.assertIn((3, (), False), applied[-1][17])
            restored = Manager(self.root, '2.4.1.1')
            self.assertEqual('W', restored.bindings.value(bui))
            self.assertEqual('Q', restored.bindings.value(velet))
            self.assertEqual(1, len(restored.bindings.issues(bui, 'W')))
            with io.open(settings, encoding='utf-8') as handle:
                self.assertEqual({'artillery': False, 'toggle_key': 'F10'}, json.load(handle))
        finally:
            manager.bindings.leave_battle()
            for name in modules:
                sys.modules.pop(name, None)

    def test_a_failed_restart_move_rolls_back_first_package(self):
        one = self.package('cache.wotmod', 'net.openwg.fix.battleresultscache')
        two = self.package('openwg/cache.wotmod', 'net.openwg.fix.battleresultscache')
        os.mkdir(two + '.manager-off')
        with self.assertRaises(OSError):
            switch_packages([one, two], False)
        self.assertTrue(os.path.isfile(one))
        self.assertTrue(os.path.isfile(two))

    def test_restart_can_cancel_before_game_exit(self):
        identifier = 'local.zdiag'
        path = self.package('diag.wotmod', identifier)
        manager = Manager(self.root, '2.4.1.1')
        manager.change(identifier, 'enabled', False)
        self.assertFalse(manager.snapshot()[0]['enabled'])
        self.assertTrue(manager.snapshot()[0]['running'])
        manager.change(identifier, 'enabled', True)
        self.assertTrue(manager.snapshot()[0]['enabled'])
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(manager.pending)

    def test_legacy_packages_migrate_once_with_backup(self):
        legacy_id = 'me.poliroid.modslistapi'
        obsolete = self.package('nested/' + legacy_id + '_1.8.0.wotmod', legacy_id)
        unrelated = self.package('other.wotmod', 'sample')
        self.assertTrue(migrate_legacy(self.root, '2.4.1.1'))
        backup = os.path.join(self.root, '.backups', 'mod-manager-legacy', '2.4.1.1', 'nested', os.path.basename(obsolete))
        self.assertTrue(os.path.isfile(backup))
        self.assertFalse(os.path.exists(obsolete))
        self.assertTrue(os.path.isfile(unrelated))
        self.package('nested/' + legacy_id + '_1.8.0.wotmod', legacy_id)
        self.assertFalse(migrate_legacy(self.root, '2.4.1.1'))
        self.assertTrue(os.path.isfile(obsolete))

    def test_openwg_core_switch_preserves_dependencies(self):
        core = 'net.openwg.common'
        upscaler = 'net.openwg.gpu.upscaler'
        xess = 'net.openwg.gpu.upscaler.xess'
        for identifier in (core, upscaler, xess):
            self.package(identifier + '.wotmod', identifier)
        manager = Manager(self.root, '2.4.1.1')
        manager.change(core, 'enabled', False)
        self.assertEqual({core: False, upscaler: False, xess: False}, manager.pending)
        self.assertFalse(apply_pending(self.root, '2.4.1.1'))
        manager = Manager(self.root, '2.4.1.1')
        manager.change(xess, 'enabled', True)
        self.assertEqual({core: True, upscaler: True, xess: True}, manager.pending)
        self.assertFalse(apply_pending(self.root, '2.4.1.1'))
        self.assertTrue(all(row['installed'] for row in scan_packages(self.pkg).values()))

    def test_graphics_setting_uses_native_controller_without_restart(self):
        identifier = 'net.openwg.common'
        self.package('openwg.wotmod', identifier)
        module_name = 'openwg_gpu.settings'
        module = types.ModuleType(str(module_name))

        class Controller(object):
            def get_ui_settings(self):
                return dict(battleFps=dict(key='battle', value=180), hangarFps=dict(key='hangar', value=179),
                            inactiveWindowFps=dict(key='inactive', value=120), latencyTechnology=None)

            def set_setting(inner, name, value):
                self.commits.append((name, value))

        module.get_controller = lambda: Controller()
        sys.modules[module_name] = module
        try:
            manager = Manager(self.root, '2.4.1.1')
            manager.change(identifier, 'hangar', 0)
            manager.change(identifier, 'hangar', 179)
            self.assertEqual([('hangar', 0), ('hangar', 179)], self.commits)
            with self.assertRaises(ValueError):
                manager.change(identifier, 'hangar', 29)
        finally:
            sys.modules.pop(module_name)


if __name__ == '__main__':
    unittest.main()
