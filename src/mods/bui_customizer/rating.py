import math


_active = None
_rect = None


def model_type(native):
    class RatingModel(native):
        __slots__ = ('onBuiMeasure',)

        def __init__(self, properties=7, commands=1):
            native.__init__(self, properties=properties, commands=commands + 1)

        def _initialize(self):
            native._initialize(self)
            self.onBuiMeasure = self._addCommand('onBuiMeasure')

    return RatingModel


def initialize(original, view, *args, **kwargs):
    global _active, _rect
    result = original(view, *args, **kwargs)
    _active, _rect = view, None
    view.viewModel.onBuiMeasure += receive
    return result


def finalize(original, view, *args, **kwargs):
    global _active, _rect
    view.viewModel.onBuiMeasure -= receive
    if _active is view:
        _active, _rect = None, None
    return original(view, *args, **kwargs)


def receive(data):
    global _rect
    try:
        rect = tuple(float(data[name]) for name in ('x', 'y', 'width', 'height'))
        if (all(not math.isinf(n) and not math.isnan(n) and 0 <= n <= 1 for n in rect)
                and rect[2] > 0 and rect[3] > 0):
            _rect = rect
    except (AttributeError, KeyError, ValueError, TypeError):
        pass


def content_bounds(viewport):
    if _rect is None:
        return None
    x, y, w, h = viewport
    left, top, width, height = _rect
    return x + w * left, y + h * top, w * width, h * height
