import os
import json
from ignis.dbus import DBusService
from gi.repository import GLib, GObject, GdkPixbuf  # type: ignore
from ignis.utils import Utils
from ignis.gobject import IgnisGObject
from loguru import logger
from ignis.services import Service
from datetime import datetime
from ignis import CACHE_DIR

POPUP_TIMEOUT_OPTION = "notification_timeout"
MAX_POPUPS_COUNT_OPTION = "notification_max_popups_count"
DND_OPTION = "dnd"

NOTIFICATIONS_CACHE_DIR = f"{CACHE_DIR}/notifications"
NOTIFICATIONS_CACHE_FILE = f"{NOTIFICATIONS_CACHE_DIR}/notifications.json"
NOTIFICATIONS_IMAGE_DATA = f"{NOTIFICATIONS_CACHE_DIR}/images"
NOTIFICATIONS_EMPTY_CACHE_FILE: dict = {"id": 0, "notifications": []}


class Notification(IgnisGObject):
    """
    A notification object. Contain data about the notification and allows performing actions.

    Signals:
        - **"closed"** (): Emitted when notification has been closed.
        - **"dismissed"** (): Emitted when notification has been dismissed.

    Properties:
        - **id** (``int``, read-only): ID of the notification.
        - **app_name** (``int``, read-only): Name of the application that sent the notification.
        - **icon** (``str``, read-only): Icon name, path to image or ``None``.
        - **summary** (``int``, read-only): Summary text of the notification, usually the title.
        - **body** (``int``, read-only): Body text of the notification, usually containing additional information.
        - **actions** (list[:class:`~ignis.services.notifications.NotificationAction`], read-only): A list of actions associated with the notification.
        - **timeout** (``int``, read-only): Timeout for the notification. Usually equal to ``popup_timeout`` property of the :class:`~ignis.services.NotificationService` unless the notification specifies otherwise
        - **time** (``float``, read-only): Time in POSIX format when the notification was sent.
        - **popup** (``bool``, read-only):Whether the notification is a popup.

    """

    __gsignals__ = {
        "closed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE, ()),
        "dismissed": (GObject.SignalFlags.RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(
        self,
        dbus: DBusService,
        id: int,
        app_name: str,
        icon: str,
        summary: str,
        body: str,
        actions: list[str],
        urgency: int,
        timeout: int,
        time: float,
        popup: bool,
    ):
        super().__init__()

        self.__dbus = dbus
        self._id = id
        self._app_name = app_name
        self._icon = icon
        self._summary = summary
        self._body = body
        self._timeout = timeout
        self._time = time
        self._urgency = urgency
        self._popup = popup
        self._actions = [
            NotificationAction(
                id=str(actions[i]),
                label=str(actions[i + 1]),
                dbus=self.__dbus,
                notification=self,
            )
            for i in range(0, len(actions), 2)
        ]

        Utils.Timeout(timeout, self.dismiss)

    @GObject.Property
    def id(self) -> int:
        return self._id

    @GObject.Property
    def app_name(self) -> str:
        return self._app_name

    @GObject.Property
    def icon(self) -> str:
        return self._icon

    @GObject.Property
    def summary(self) -> str:
        return self._summary

    @GObject.Property
    def body(self) -> str:
        return self._body

    @GObject.Property
    def actions(self) -> list["NotificationAction"]:
        return self._actions

    @GObject.Property
    def timeout(self) -> int:
        return self._timeout

    @GObject.Property
    def time(self) -> float:
        return self._time

    @GObject.Property
    def urgency(self) -> int:
        return self._urgency

    @GObject.Property
    def popup(self) -> bool:
        return self._popup

    @GObject.Property
    def json(self) -> dict:
        return {
            "id": self._id,
            "app_name": self._app_name,
            "icon": self._icon,
            "summary": self._summary,
            "body": self._body,
            "actions": [j for i in self._actions for j in (i.id, i.label)],
            "timeout": self._timeout,
            "time": self._time,
            "urgency": self._urgency,
        }

    def close(self) -> None:
        self.emit("closed")

    def dismiss(self) -> None:
        if self._popup:
            self._popup = False
            self.emit("dismissed")
            self.notify("popup")


class NotificationAction(IgnisGObject):
    """
    A simple object that contains data about a notification action.

    Properties:
        - **id** (``str``, read-only): The ID of the action.
        - **label** (``int``, read-only): The label of the notification. This one should be displayed to user.
    """

    def __init__(
        self, dbus: DBusService, notification: Notification, id: str, label: str
    ):
        super().__init__()
        self.__dbus = dbus
        self.__notification = notification
        self._id = id
        self._label = label

    @GObject.Property
    def id(self) -> str:
        return self._id

    @GObject.Property
    def label(self) -> str:
        return self._label

    def invoke(self) -> None:
        """
        Invoke action.
        """
        self.__dbus.emit_signal(
            "ActionInvoked", GLib.Variant("(us)", (self.__notification.id, self.id))
        )


class NotificationService(IgnisGObject):
    """
    A notification daemon.
    Allow receiving notifications and perform actions on them.

    Signals:
        - **"notified"** (:class:`~ignis.services.notifications.Notification`): Emitted when a new notification appears.
        - **"new_popup"** (:class:`~ignis.services.notifications.Notification`): Emitted when a new popup notification appears. Only emitted if ``dnd`` is set to ``False``.

    Properties:
        - **notifications** (list[:class:`~ignis.services.notifications.Notification`], read-only): A list of all notifications.
        - **popups** (list[:class:`~ignis.services.notifications.Notification`], read-only): A list of currently active popup notifications, sorted from newest to oldest.
        - **dnd** (``bool``, read-write): Do Not Disturb mode. If set to ``True``, the ``"new_popup"`` signal will not be emitted, and all new :class:`~ignis.services.notifications.Notification` instances will have ``popup`` set to ``False``. Default: ``False``.
        - **popup_timeout** (``int``, read-write): Timeout before a popup is automatically dismissed, in milliseconds. Default: ``5000``.
        - **max_popups_count** (``int``, read-write): Maximum number of popups. If the length of the ``popups`` list exceeds ``max_popups_count``, the oldest popup will be dismissed. Default: ``3``.

    **Example usage:**

    .. code-block:: python

        from ignis.services import Service

        notifications = Service.get("notifications")

        notifications.connect("notified", lambda x, notification: print(notification.app_name, notification.summary))
    """

    __gsignals__ = {
        "notified": (
            GObject.SignalFlags.RUN_FIRST,
            GObject.TYPE_NONE,
            (GObject.Object,),
        ),
        "new_popup": (
            GObject.SignalFlags.RUN_FIRST,
            GObject.TYPE_NONE,
            (GObject.Object,),
        ),
    }

    def __init__(self):
        super().__init__()

        self.__dbus = DBusService(
            name="org.freedesktop.Notifications",
            object_path="/org/freedesktop/Notifications",
            info=Utils.load_interface_xml("org.freedesktop.Notifications"),
            on_name_lost=lambda x, y: logger.error(
                "Another notification daemon is already running. Try removing all other notification daemons (e.g dunst, mako, swaync)."
            ),
        )

        self.__dbus.register_dbus_method(
            name="GetServerInformation", method=self.__GetServerInformation
        )
        self.__dbus.register_dbus_method(
            name="GetCapabilities", method=self.__GetCapabilities
        )
        self.__dbus.register_dbus_method(
            name="CloseNotification", method=self.__CloseNotification
        )
        self.__dbus.register_dbus_method(name="Notify", method=self.__Notify)

        self._id: int = 0
        self._notifications: dict[int, Notification] = {}
        self._popups: dict[int, Notification] = {}

        os.makedirs(NOTIFICATIONS_CACHE_DIR, exist_ok=True)
        os.makedirs(NOTIFICATIONS_IMAGE_DATA, exist_ok=True)

        self._options = Service.get("options")

        self._options.create_option(name=DND_OPTION, default=False, exists_ok=True)
        self._options.create_option(
            name=POPUP_TIMEOUT_OPTION, default=5000, exists_ok=True
        )
        self._options.create_option(
            name=MAX_POPUPS_COUNT_OPTION, default=3, exists_ok=True
        )

        self.__load_notifications()

    @GObject.Property
    def notifications(self) -> list[Notification]:
        return list(self._notifications.values())

    @GObject.Property
    def popups(self) -> list[Notification]:
        return list(self._popups.values())

    @GObject.Property
    def dnd(self) -> bool:
        return self._options.get_option(DND_OPTION)

    @dnd.setter
    def dnd(self, value: bool) -> None:
        self._options.set_option(DND_OPTION, value)

    @GObject.Property
    def popup_timeout(self) -> int:
        return self._options.get_option(POPUP_TIMEOUT_OPTION)

    @popup_timeout.setter
    def popup_timeout(self, value: int) -> None:
        self._options.set_option(POPUP_TIMEOUT_OPTION, value)

    @GObject.Property
    def max_popups_count(self) -> int:
        return self._options.get_option(MAX_POPUPS_COUNT_OPTION)

    @max_popups_count.setter
    def max_popups_count(self, value: int) -> None:
        self._options.set_option(MAX_POPUPS_COUNT_OPTION, value)

    def __GetServerInformation(self, *args) -> GLib.Variant:
        return GLib.Variant(
            "(ssss)",
            ("Ignis Notifications service", "linkfrg", "1.0", "1.2"),
        )

    def __GetCapabilities(self, *args) -> GLib.Variant:
        return GLib.Variant(
            "(as)", (["actions", "body", "icon-static", "persistence"],)
        )

    def __CloseNotification(self, invocation, id: int) -> None:
        notification = self.get_notification(id)
        if notification:
            notification.close()

    def get_notification(self, id: int) -> Notification | None:
        """
        Get :class:`~ignis.services.notifications.Notification` by ID.

        Args:
            id (``int``): ID of notification.

        Returns:
            :class:`~ignis.services.notifications.Notification` or ``None``
        """
        return self._notifications.get(id, None)

    def __Notify(
        self,
        invocation,
        app_name: str,
        replaces_id: int,
        app_icon: str,
        summary: str,
        body: str,
        actions: list,
        hints: dict,
        timeout: int,
    ) -> GLib.Variant:
        def _init(_id: int) -> None:
            self.__init_notification(
                _id=_id,
                app_name=app_name,
                app_icon=app_icon,
                summary=summary,
                body=body,
                actions=actions,
                hints=hints,
                timeout=timeout,
            )

        if replaces_id == 0:
            _id = self._id = self._id + 1
            _init(_id)

        else:
            _id = replaces_id
            old_notification = self.get_notification(replaces_id)
            if old_notification:
                old_notification.close()
                old_notification.connect("closed", lambda x: _init(_id))
            else:
                _init(_id)

        return GLib.Variant("(u)", (_id,))

    def __init_notification(
        self,
        _id: int,
        app_name: str,
        app_icon: str,
        summary: str,
        body: str,
        actions: list,
        hints: dict,
        timeout: int,
    ) -> None:
        icon = None

        if isinstance(app_icon, str):
            icon = app_icon

        if "image-data" in hints:
            icon = f"{NOTIFICATIONS_IMAGE_DATA}/{_id}"
            self.__save_pixbuf(hints["image-data"], icon)

        notification = Notification(
            dbus=self.__dbus,
            id=_id,
            app_name=app_name,
            icon=icon,
            summary=summary,
            body=body,
            actions=actions,
            urgency=hints.get("urgency", 1),
            timeout=self.popup_timeout if timeout == -1 else timeout,
            time=datetime.now().timestamp(),
            popup=not self.dnd,
        )

        if len(self.popups) >= self.max_popups_count:
            if not self.max_popups_count == 0:
                self.popups[-1].dismiss()

        if notification.popup:
            self._popups[notification.id] = notification
            self.emit("new_popup", notification)
            self.notify("popups")

        self.__add_notification(notification)
        self.__sync()
        self.emit("notified", notification)
        self.notify("notifications")

    def __save_pixbuf(self, px_args: list, save_path: str) -> None:
        GdkPixbuf.Pixbuf.new_from_bytes(
            width=px_args[0],
            height=px_args[1],
            has_alpha=px_args[3],
            data=GLib.Bytes.new(px_args[6]),
            colorspace=GdkPixbuf.Colorspace.RGB,
            rowstride=px_args[2],
            bits_per_sample=px_args[4],
        ).savev(save_path, "png")

    def clear_all(self) -> None:
        """
        Clear all notifications.
        """
        for notify in self.notifications:
            notify.close()

    def __close_notification(self, notification: Notification) -> None:
        self._notifications.pop(notification.id)
        if notification.popup:
            notification.dismiss()
        self.__sync()

        self.__dbus.emit_signal(
            "NotificationClosed", GLib.Variant("(uu)", (notification.id, 2))
        )

        self.notify("notifications")

    def __dismiss_popup(self, notification: Notification) -> None:
        if self._popups.get(notification.id, None):
            self._popups.pop(notification.id)
            self.notify("popups")

    def __sync(self) -> None:
        data = {
            "id": self._id,
            "notifications": [n.json for n in self.notifications],
        }
        with open(NOTIFICATIONS_CACHE_FILE, "w") as file:
            json.dump(data, file, indent=2)

    def __add_notification(self, notification: Notification) -> None:
        notification.connect("closed", lambda x: self.__close_notification(x))
        notification.connect("dismissed", lambda x: self.__dismiss_popup(x))
        self._notifications[notification.id] = notification

    def __load_notifications(self) -> None:
        try:
            with open(NOTIFICATIONS_CACHE_FILE) as file:
                log_file = json.load(file)

            for n in log_file.get("notifications", []):
                notification = Notification(**n, popup=False, dbus=self.__dbus)
                self.__add_notification(notification)

            self._id = log_file.get("id", 0)

        except Exception:
            logger.warning("Notification history file is corrupted! Cleaning...")
            with open(NOTIFICATIONS_CACHE_FILE, "w") as file:
                json.dump(NOTIFICATIONS_EMPTY_CACHE_FILE, file, indent=2)