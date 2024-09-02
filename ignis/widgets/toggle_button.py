from gi.repository import GObject, Gtk  # type: ignore
from ignis.base_widget import BaseWidget
from typing import Callable


class ToggleButton(Gtk.ToggleButton, BaseWidget):
    """
    Bases: `Gtk.ToggleButton <https://lazka.github.io/pgi-docs/#Gtk-4.0/classes/ToggleButton.html>`_.

    A toggle button widget.

    Properties:
        - **on_toggled** (``Callable``, optional, read-write): Function to call when the button is toggled by the user.

    .. code-block:: python

        Widget.ToggleButton(
            on_toggled=lambda x, active: print(active)
        )
    """

    __gtype_name__ = "IgnisToggleButton"
    __gproperties__ = {**BaseWidget.gproperties}

    def __init__(self, **kwargs) -> None:
        Gtk.ToggleButton.__init__(self)
        self._on_toggled: Callable | None = None
        BaseWidget.__init__(self, **kwargs)

        self.connect(
            "toggled",
            lambda x: self.on_toggled(self, self.active) if self.on_toggled else None,
        )

    @GObject.Property
    def on_toggled(self) -> Callable | None:
        return self._on_toggled

    @on_toggled.setter
    def on_toggled(self, value: Callable | None) -> None:
        self._on_toggled = value