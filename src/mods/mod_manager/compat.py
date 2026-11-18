import sys
import types


class Templates(object):
    @staticmethod
    def createCheckbox(**options):
        return options

    @staticmethod
    def createSlider(**options):
        return options


class SettingsAPI(object):
    def setModTemplate(self, linkage, template, callback):
        return None


class ModsListAPI(object):
    def addModification(self, *args, **kwargs):
        return None


def load_view(api=None):
    from .hangar import open_legacy
    open_legacy()


def install_legacy_bridge():
    # WoT rejects an entire wotmod when another package owns one of its paths — 2026-11-18
    gui = sys.modules['gui']
    settings = types.ModuleType('gui.modsSettingsApi')
    settings.__path__ = []
    settings.g_modsSettingsApi = SettingsAPI()
    settings.templates = Templates()
    view = types.ModuleType('gui.modsSettingsApi.view')
    view.loadView = load_view
    settings.view = view
    listing = types.ModuleType('gui.modsListApi')
    listing.g_modsListApi = ModsListAPI()
    if settings.__name__ not in sys.modules:
        sys.modules[settings.__name__] = gui.modsSettingsApi = settings
        sys.modules[view.__name__] = view
    if listing.__name__ not in sys.modules:
        sys.modules[listing.__name__] = gui.modsListApi = listing
