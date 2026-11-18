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
