import BigWorld
from constants import ARENA_BONUS_TYPE


SUPPORTED_MODES = frozenset(
    getattr(ARENA_BONUS_TYPE, name) for name in (
        'REGULAR', 'EPIC_RANDOM', 'RANDOM_NP2', 'TRAINING', 'EPIC_RANDOM_TRAINING', 'MAPS_TRAINING',
        'SORTIE_2', 'FORT_BATTLE_2', 'CLAN', 'GLOBAL_MAP', 'TOURNAMENT', 'TOURNAMENT_REGULAR', 'TOURNAMENT_CLAN',
    ) if hasattr(ARENA_BONUS_TYPE, name)
)


def is_supported_battle():
    return getattr(BigWorld.player(), 'arenaBonusType', None) in SUPPORTED_MODES
