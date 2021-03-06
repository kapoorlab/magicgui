"""Widgets backed by a backend implementation, ready to be instantiated by the user.

All of these widgets should provide the `widget_type` argument to their
super().__init__ calls.
"""
import inspect
import math
import os
from pathlib import Path
from typing import Callable, Sequence, Tuple, Type, Union

from magicgui._parse import docstring_to_param_list, param_list_to_str
from magicgui.application import use_app
from magicgui.types import FileDialogMode, PathLike

from ._bases import (
    ButtonWidget,
    CategoricalWidget,
    ContainerWidget,
    RangedWidget,
    SliderWidget,
    TransformedRangedWidget,
    ValueWidget,
    Widget,
)
from ._transforms import make_float, make_literal_eval


def merge_super_sigs(cls, exclude=("self", "widget_type", "kwargs", "args", "kwds")):
    """Merge the signature and kwarg docs from all superclasses, for clearer docs.

    Parameters
    ----------
    exclude : tuple, optional
        A list of parameter names to excluded from the merged docs/signature,
        by default ("self", "widget_type", "kwargs", "args", "kwds")

    Returns
    -------
    Type
        The modified class (can be used as a decorator)
    """
    params = {}
    param_docs = []
    for sup in reversed(inspect.getmro(cls)):
        sig = inspect.signature(getattr(sup, "__init__"))
        for name, param in sig.parameters.items():
            if name in exclude:
                continue
            params[name] = param

        param_docs += docstring_to_param_list(getattr(sup, "__doc__", ""))

    cls.__signature__ = inspect.Signature(sorted(params.values(), key=lambda x: x.kind))
    param_docs = [p for p in param_docs if p.name not in exclude]
    cls.__doc__ = (cls.__doc__ or "").split("Parameters")[0].rstrip() + "\n\n"
    cls.__doc__ += "\n".join(param_list_to_str(param_docs))
    return cls


def backend_widget(
    cls: Type = None, widget_name: str = None, transform: Callable[[Type], Type] = None
):
    """Decorate cls to inject the backend widget of the same name.

    The purpose of this decorator is to "inject" the appropriate backend
    `widget_type` argument into the `Widget.__init__` function, according to the
    app currently being used (i.e. returned by `use_app()`).

    Parameters
    ----------
    cls : Type, optional
        The class being decorated, by default None.
    widget_name : str, optional
        The name of the backend widget to wrap. If None, the name of the class being
        decorated is used.  By default None.
    transform : callable, optional
        A optional function that takes a class and returns a class.  May be used
        to transform the characteristics/methods of the class, by default None

    Returns
    -------
    cls : Type
        The final concrete class backed by a backend widget.
    """

    def wrapper(cls) -> Type[Widget]:
        def __init__(self, **kwargs):
            app = use_app()
            assert app.native
            widget = app.get_obj(widget_name or cls.__name__)
            if transform:
                widget = transform(widget)
            kwargs["widget_type"] = widget
            super(cls, self).__init__(**kwargs)

        cls.__init__ = __init__
        cls = merge_super_sigs(cls)
        return cls

    return wrapper(cls) if cls else wrapper


@backend_widget
class Label(ValueWidget):
    """A non-editable text or image display."""


@backend_widget
class LineEdit(ValueWidget):
    """A one-line text editor."""


@backend_widget(widget_name="LineEdit", transform=make_literal_eval)
class LiteralEvalLineEdit(ValueWidget):
    """A one-line text editor that evaluates strings as python literals."""


@backend_widget
class TextEdit(ValueWidget):
    """A widget to edit and display both plain and rich text."""


@backend_widget
class DateTimeEdit(ValueWidget):
    """A widget for editing dates and times."""


@backend_widget
class PushButton(ButtonWidget):
    """A clickable command button."""


@backend_widget
class CheckBox(ButtonWidget):
    """A checkbox with a text label."""


@backend_widget
class RadioButton(ButtonWidget):
    """A radio button with a text label."""


@backend_widget
class SpinBox(RangedWidget):
    """A widget to edit an integer with clickable up/down arrows."""


@backend_widget
class FloatSpinBox(RangedWidget):
    """A widget to edit a float with clickable up/down arrows."""


@backend_widget
class Slider(SliderWidget):
    """A slider widget to adjust an integer value within a range."""


@backend_widget(widget_name="Slider", transform=make_float)
class FloatSlider(SliderWidget):
    """A slider widget to adjust a float value within a range."""


@merge_super_sigs
class LogSlider(TransformedRangedWidget):
    """A slider widget to adjust a numerical value logarithmically within a range.

    Parameters
    ----------
    base : Enum, Iterable, or Callable
        The base to use for the log, by default math.e.
    """

    def __init__(
        self, minimum: float = 1, maximum: float = 100, base: float = math.e, **kwargs
    ):
        self._base = base
        app = use_app()
        assert app.native
        super().__init__(
            minimum=minimum,
            maximum=maximum,
            widget_type=app.get_obj("Slider"),
            **kwargs,
        )

    @property
    def _scale(self):
        minv = math.log(self.minimum, self.base)
        maxv = math.log(self.maximum, self.base)
        return (maxv - minv) / (self._max_pos - self._min_pos)

    def _value_from_position(self, position):
        minv = math.log(self.minimum, self.base)
        return math.pow(self.base, minv + self._scale * (position - self._min_pos))

    def _position_from_value(self, value):
        minv = math.log(self.minimum, self.base)
        return (math.log(value, self.base) - minv) / self._scale + self._min_pos

    @property
    def base(self):
        """Return base used for the log."""
        return self._base

    @base.setter
    def base(self, base):
        prev = self.value
        self._base = base
        self.value = prev


@backend_widget
class ComboBox(CategoricalWidget):
    """A dropdown menu, allowing selection between multiple choices."""


@backend_widget
class Container(ContainerWidget):
    """A Widget to contain other widgets."""


@merge_super_sigs
class FileEdit(Container):
    """A LineEdit widget with a button that opens a FileDialog.

    Parameters
    ----------
    mode : FileDialogMode or str
        The mode used for the file dialog:
            'r': returns one existing file.
            'rm': return one or more existing files.
            'w': return one file name that does not have to exist.
            'd': returns one existing directory.
    filter : str, optional
        The filter is used to specify the kind of files that should be shown.
        It should be a glob-style string, like '*.png' (this may be backend-specific)
    """

    def __init__(
        self, mode: FileDialogMode = FileDialogMode.EXISTING_FILE, filter=None, **kwargs
    ):
        self.line_edit = LineEdit()
        self.choose_btn = PushButton()
        self.mode = mode  # sets the button text too
        self.filter = filter
        kwargs["widgets"] = [self.line_edit, self.choose_btn]
        kwargs["labels"] = False
        super().__init__(**kwargs)
        self.margins = (0, 0, 0, 0)
        self._show_file_dialog = use_app().get_obj("show_file_dialog")
        self.choose_btn.changed.connect(self._on_choose_clicked)

    @property
    def mode(self) -> FileDialogMode:
        """Mode for the FileDialog."""
        return self._mode

    @mode.setter
    def mode(self, value: Union[FileDialogMode, str]):
        self._mode = FileDialogMode(value)
        self.choose_btn.text = self._btn_text

    @property
    def _btn_text(self) -> str:
        if self.mode is FileDialogMode.EXISTING_DIRECTORY:
            return "Choose directory"
        else:
            return "Select file" + ("s" if self.mode.name.endswith("S") else "")

    def _on_choose_clicked(self, event=None):
        _p = self.value
        start_path: Path = _p[0] if isinstance(_p, tuple) else _p
        _start_path = os.fspath(start_path.expanduser().absolute())
        result = self._show_file_dialog(
            self.mode,
            caption=self._btn_text,
            start_path=_start_path,
            filter=self.filter,
        )
        if result:
            self.value = result

    @property
    def value(self) -> Union[Tuple[Path, ...], Path]:
        """Return current value of the widget.  This may be interpreted by backends."""
        text = self.line_edit.value
        if self.mode is FileDialogMode.EXISTING_FILES:
            return tuple(Path(p) for p in text.split(", "))
        return Path(text)

    @value.setter
    def value(self, value: Union[Sequence[PathLike], PathLike]):
        """Set current file path."""
        if isinstance(value, (list, tuple)):
            value = ", ".join([os.fspath(p) for p in value])
        if not isinstance(value, (str, Path)):
            raise TypeError(
                f"value must be a string, or list/tuple of strings, got {type(value)}"
            )
        self.line_edit.value = os.fspath(Path(value).expanduser().absolute())

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<FileEdit mode={self.mode.value!r}, value={self.value!r}>"


@merge_super_sigs
class RangeEdit(Container):
    """A widget to represent a python range object, with start/stop/step.

    A range object produces a sequence of integers from start (inclusive)
    to stop (exclusive) by step.  range(i, j) produces i, i+1, i+2, ..., j-1.
    start defaults to 0, and stop is omitted!  range(4) produces 0, 1, 2, 3.
    These are exactly the valid indices for a list of 4 elements.
    When step is given, it specifies the increment (or decrement).

    Parameters
    ----------
    start : int, optional
        The range start value, by default 0
    stop : int, optional
        The range stop value, by default 10
    step : int, optional
        The range step value, by default 1
    """

    def __init__(self, start=0, stop=10, step=1, **kwargs):
        self.start = SpinBox(default=start)
        self.stop = SpinBox(default=stop)
        self.step = SpinBox(default=step)
        kwargs["widgets"] = [self.start, self.stop, self.step]
        super().__init__(**kwargs)

    @property
    def value(self) -> range:
        """Return current value of the widget.  This may be interpreted by backends."""
        return range(self.start.value, self.stop.value, self.step.value)

    @value.setter
    def value(self, value: range):
        """Set current file path."""
        self.start.value = value.start
        self.stop.value = value.stop
        self.step.value = value.step

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<{self.__class__.__name__} value={self.value!r}>"


class SliceEdit(RangeEdit):
    """A widget to represent range objects, with start/stop/step.

    slice(stop)
    slice(start, stop[, step])

    Slice objects may be used for extended slicing (e.g. a[0:10:2])
    """

    @property  # type: ignore
    def value(self) -> slice:  # type: ignore
        """Return current value of the widget.  This may be interpreted by backends."""
        return slice(self.start.value, self.stop.value, self.step.value)

    @value.setter
    def value(self, value: slice):
        """Set current file path."""
        self.start.value = value.start
        self.stop.value = value.stop
        self.step.value = value.step
