import ast
import os
import unittest


def load_functions(*names):
    source = os.path.join(os.path.dirname(__file__), 'mod_platoon_autostart.py')
    with open(source, 'rb') as handle:
        nodes = ast.parse(handle.read(), source).body
    selected = [node for node in nodes if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {}
    exec compile(ast.Module(body=selected), source, 'exec') in namespace
    return namespace


class Entity(object):
    def __init__(self, queue, entity_type=None):
        self.queue = queue
        self.entity_type = entity_type

    def getQueueType(self):
        return self.queue

    def getEntityType(self):
        return self.entity_type


class SquadModesTest(unittest.TestCase):
    def test_lobby_queue_allowlist(self):
        namespace = load_functions('_allowed_squad_entity')
        namespace['QUEUE_TYPE'] = type('Queues', (), dict(RANDOMS=1, STRONGHOLD_UNITS=2))
        namespace['PREBATTLE_TYPE'] = type('Types', (), dict(TRAINING=3, STRONGHOLD=9))
        allowed = namespace['_allowed_squad_entity']
        self.assertTrue(allowed(Entity(1)))
        self.assertTrue(allowed(Entity(2)))
        self.assertTrue(allowed(Entity(None, 3)))
        self.assertFalse(allowed(Entity(8, 3)))
        self.assertFalse(allowed(Entity(40)))
        self.assertFalse(allowed(None))

    def test_event_windows_delegate_to_the_original_handlers(self):
        names = ('_hooked_MembersWindow_init', '_hooked_SelectionWindow_init',
                 '_hooked_MembersWindow_move', '_hooked_SquadMembersView_onLeavePlatoon')
        namespace = load_functions(*names)
        namespace['_is_in_hangar'] = lambda: False
        view = object()
        for name in names:
            original = name.replace('_hooked_', '_orig_')
            namespace[original] = lambda *args: args
        self.assertEqual(namespace[names[0]](view, 10), (view, 10))
        self.assertEqual(namespace[names[1]](view), (view,))
        self.assertEqual(namespace[names[2]](view, 20, 30), (view, 20, 30))
        self.assertEqual(namespace[names[3]](view), (view,))

    def test_battle_events_do_not_get_solo_features(self):
        namespace = load_functions('_battle_features_enabled')
        arena = type('Modes', (), dict(REGULAR=1, TRAINING=2, SORTIE_2=3, FORT_BATTLE_2=4))
        player = type('Player', (), {})()
        namespace.update(
            BigWorld=type('BigWorld', (), dict(player=staticmethod(lambda: player))),
            ARENA_BONUS_TYPE=arena,
            _CONFIG={'enabled': True},
        )
        allowed = namespace['_battle_features_enabled']
        for mode in (None, 188, 154, 45):
            player.arenaBonusType = mode
            self.assertFalse(allowed())
        player.arenaBonusType = 1
        self.assertTrue(allowed())
        namespace['_CONFIG']['enabled'] = False
        self.assertFalse(allowed())

    def test_event_visibility_and_clicks_use_stock_handlers(self):
        focus = '_hooked_SquadMembersView_onFocusChange'
        visible = '_hooked_PlatoonController_evaluateVisibility'
        namespace = load_functions(focus, visible)
        namespace['_is_in_hangar'] = lambda: False
        namespace['_squad_features_enabled'] = lambda: False
        namespace['_orig_SquadMembersView_onFocusChange'] = lambda view, data: data
        namespace['_orig_PlatoonController_evaluateVisibility'] = lambda view, toggleUI: toggleUI
        self.assertEqual(namespace[focus](object(), {'closeFriendList': True}), {'closeFriendList': True})
        self.assertTrue(namespace[visible](object(), True))


if __name__ == '__main__':
    unittest.main()
