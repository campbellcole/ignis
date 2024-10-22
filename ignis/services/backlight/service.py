import os
from gi.repository import GObject  # type: ignore
from ignis.base_service import BaseService
from .device import BacklightDevice
from .constants import SYS_BACKLIGHT
from ignis.utils import Utils


class BacklightService(BaseService):
    """
    A backlight service.
    Allows controlling device screen brightness.

    Properties:
        - **devices** (list[:class:`~ignis.services.backlight.BacklightDevice`], read-only): List of all backlight devices.
        - **brightness** (``int``, read-write): Current brightness of the first backlight device in the list, ``-1`` if there are no backlight devices. Setting this property will set provided brightness on ALL backlight devices.
        - **max_brightness** (``int``, read-only): Maximum brightness allowed by the first backlight device in the list, ``-1`` if there are no backlight devices.
        - **available** (``bool``, read-only): Whether there are controllable backlight devices.

    **Example Usage:**

    .. code-block:: python

        from ignis.services.backlight import BacklightService

        backlight = BacklightService.get_default()

        print(backlight.brightness)
        print(backlight.max_brightness)
        print(backlight.available)

        backlight.set_brightness(30) # set brightness to 30 on all devices

        # backlight.devices[1].set_brightness(50) # set brightness to 50 on the second device in the list
    """

    def __init__(self):
        super().__init__()

        self._devices: list[BacklightDevice] = []

        # FIXME: not working
        Utils.FileMonitor(
            path=SYS_BACKLIGHT,
            callback=lambda path, event_type: self.__sync_devices()
            if event_type == "deleted" or event_type == "created"
            else None,
        )

        self.__sync_devices()

    def __sync_devices(self) -> None:
        self._devices = []

        for device_name in os.listdir(SYS_BACKLIGHT):
            self._devices.append(BacklightDevice(device_name))

        self.notify("devices")
        self.notify("available")

    @GObject.Property
    def available(self) -> bool:
        return len(self._devices) > 0

    @GObject.Property
    def devices(self) -> list[BacklightDevice]:
        return self._devices

    @GObject.Property
    def brightness(self) -> int:
        if len(self._devices) > 0:
            return self._devices[0].brightness
        else:
            return -1

    @brightness.setter
    def brightness(self, value: int) -> None:
        for device in self._devices:
            device.brightness = value

    @GObject.Property
    def max_brightness(self) -> int:
        if len(self._devices) > 0:
            return self._devices[0].max_brightness
        else:
            return -1