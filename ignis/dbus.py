from __future__ import annotations
from gi.repository import Gio, GLib, GObject  # type: ignore
from typing import Any, Callable
from ignis.utils import Utils
from ignis.gobject import IgnisGObject
from ignis.exceptions import DBusMethodNotFoundError, DBusPropertyNotFoundError


class DBusService(IgnisGObject):
    """
    Class to help create DBus services.

    Properties:
        - **name** (``str``, required, read-only): The well-known name to own.
        - **object_path** (``str``, required, read-only): An object path.
        - **info** (`Gio.DBusInterfaceInfo <https://lazka.github.io/pgi-docs/Gio-2.0/classes/DBusInterfaceInfo.html>`_, required, read-only): A ``Gio.DBusInterfaceInfo`` instance. You can get it from XML using :class:`~ignis.utils.Utils.load_interface_xml`.
        - **on_name_acquired** (``Callable``, optional, read-write): Function to call when ``name`` is acquired.
        - **on_name_lost** (``Callable``, optional, read-write): Function to call when ``name`` is lost.
        - **connection** (`Gio.DBusConnection <https://lazka.github.io/pgi-docs/Gio-2.0/classes/DBusConnection.html>`_, not argument, read-only): The ``Gio.DBusConnection`` instance.
        - **methods** (``Dict[str, Callable]``, not argument, read-only): The dictionary of registred DBus methods. See :func:`~ignis.dbus.DBusService.register_dbus_method`.
        - **properties** (``Dict[str, Callable]``, not argument, read-only): The dictionary of registred DBus properties. See :func:`~ignis.dbus.DBusService.register_dbus_property`.

    DBus methods:
        - Must accept `Gio.DBusMethodInvocation <https://lazka.github.io/pgi-docs/index.html#Gio-2.0/classes/DBusMethodInvocation.html>`_ as the first argument.
        - Must accept all other arguments typical for this method (specified by interface info).
        - Must return `GLib.Variant <https://lazka.github.io/pgi-docs/index.html#GLib-2.0/classes/Variant.html>`_ or ``None``, as specified by interface info.

    DBus properties:
        - Must return `GLib.Variant <https://lazka.github.io/pgi-docs/index.html#GLib-2.0/classes/Variant.html>`_, as specified by interface info.

    .. code-block:: python

        from gi.repository import Gio, GLib
        from ignis.dbus import DBusService

        def _MyMethod(invocation: Gio.DBusMethodInvocation, prop1: str, prop2: str, *args) -> GLib.Variant:
            print("do something")
            return GLib.Variant("(is)", (42, "hello"))

        def _MyProperty() -> GLib.Variant:
            return GLib.Variant("(b)", (False,))

        dbus = DBusService(...)
        dbus.register_dbus_method("MyMethod", _MyMethod)
        dbus.register_dbus_property("MyProperty", _MyProperty)
    """

    def __init__(
        self,
        name: str,
        object_path: str,
        info: Gio.DBusInterfaceInfo,
        on_name_acquired: Callable | None = None,
        on_name_lost: Callable | None = None,
    ):
        super().__init__()

        self._name = name
        self._object_path = object_path
        self._info = info
        self._on_name_acquired = on_name_acquired
        self._on_name_lost = on_name_lost

        self._methods: dict[str, Callable] = {}
        self._properties: dict[str, Callable] = {}

        self._id = Gio.bus_own_name(
            Gio.BusType.SESSION,
            name,
            Gio.BusNameOwnerFlags.NONE,
            self.__export_object,
            self._on_name_acquired,
            self._on_name_lost,
        )

    @GObject.Property
    def name(self) -> str:
        return self._name

    @GObject.Property
    def object_path(self) -> str:
        return self._object_path

    @GObject.Property
    def on_name_acquired(self) -> Callable:
        return self._on_name_acquired

    @on_name_acquired.setter
    def on_name_acquired(self, value: Callable) -> None:
        self._on_name_acquired = value

    @GObject.Property
    def on_name_lost(self) -> Callable:
        return self._on_name_lost

    @on_name_lost.setter
    def on_name_lost(self, value: Callable) -> None:
        self._on_name_lost = value

    @GObject.Property
    def info(self) -> Gio.DBusInterfaceInfo:
        return self._info

    @GObject.Property
    def connection(self) -> Gio.DBusConnection:
        return self._connection

    @GObject.Property
    def methods(self) -> dict[str, Callable]:
        return self._methods

    @GObject.Property
    def properties(self) -> dict[str, Callable]:
        return self._properties

    def __export_object(self, connection: Gio.DBusConnection, name: str) -> None:
        self._connection = connection
        self._connection.register_object(
            self._object_path,
            self._info,
            self.__handle_method_call,
            self.__handle_get_property,
            None,
        )

    def __handle_method_call(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface_name: str,
        method_name: str,
        params: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        def callback(func: Callable, unpacked_params) -> None:
            result = func(invocation, *unpacked_params)
            invocation.return_value(result)

        func = self._methods.get(method_name, None)
        if not func:
            raise DBusMethodNotFoundError(method_name)

        # params can contain pixbuf, very large amount of data
        # and unpacking may take some time and block the main thread
        # so we unpack in another thread, and call DBus method when unpacking is finished
        Utils.ThreadTask(
            target=params.unpack, callback=lambda result: callback(func, result)
        )

    def __handle_get_property(
        self,
        connection: Gio.DBusConnection,
        sender: str,
        object_path: str,
        interface: str,
        value: str,
    ) -> GLib.Variant:
        func = self._properties.get(value, None)
        if not func:
            raise DBusPropertyNotFoundError(value)

        return func()

    def register_dbus_method(self, name: str, method: Callable) -> None:
        """
        Register a D-Bus method for this service.

        Args:
            name (``str``): The name of the method to register.
            method (``Callable``): A function to call when the method is invoked (from D-Bus).
        """
        self._methods[name] = method

    def register_dbus_property(self, name: str, method: Callable) -> None:
        """
        Register D-Bus property for this service.

        Args:
            name (``str``): The name of the property to register.
            method (``Callable``): A function to call when the property is accessed (from DBus).
        """
        self._properties[name] = method

    def emit_signal(
        self, signal_name: str, parameters: GLib.Variant | None = None
    ) -> None:
        """
        Emit a D-Bus signal on this service.

        Args:
            signal_name (``str``): The name of the signal to emit.
            parameters (`GLib.Variant <https://lazka.github.io/pgi-docs/index.html#GLib-2.0/classes/Variant.html>`_, optional): The ``GLib.Variant`` containing paramaters to pass with the signal.
        """

        self._connection.emit_signal(
            None,
            self._object_path,
            self._name,
            signal_name,
            parameters,
        )

    def unown_name(self) -> None:
        """
        Release ownership of the name.
        """
        Gio.bus_unown_name(self._id)


class DBusProxy(IgnisGObject):
    """
    Class to interact with D-Bus services (create a D-Bus proxy).
    Unlike `Gio.DBusProxy <https://lazka.github.io/pgi-docs/index.html#Gio-2.0/classes/DBusProxy.html>`_,
    this class also provides convenient pythonic property access.

    Properties:
        - **name** (``str``, required, read-only): A bus name (well-known or unique).
        - **object_path** (``str``, required, read-only): An object path.
        - **interface_name** (``str``, required, read-only): A D-Bus interface name.
        - **info** (`Gio.DBusInterfaceInfo <https://lazka.github.io/pgi-docs/Gio-2.0/classes/DBusInterfaceInfo.html>`_, required, read-only): A ``Gio.DBusInterfaceInfo`` instance. You can get it from XML using :class:`~ignis.utils.Utils.load_interface_xml`.
        - **proxy** (`Gio.DBusProxy <https://lazka.github.io/pgi-docs/index.html#Gio-2.0/classes/DBusProxy.html>`_, not argument, read-only): The ``Gio.DBusProxy`` instance.
        - **methods** (``list[str]``, not argument, read-only): A list of methods exposed by D-Bus service.
        - **properties** (``list[str]``, not argument, read-only): A list of properties exposed by D-Bus service.
        - **has_owner** (``bool``, not argument, read-only): Whether the ``name`` has an owner.

    To call a D-Bus method, use the standart pythonic way.
    The first argument always needs to be the DBus signature tuple of the method call.
    Subsequent arguments must match the provided D-Bus signature.
    If the D-Bus method does not accept any arguments, do not pass arguments.

    .. code-block:: python

        from ignis.dbus import DBusProxy
        proxy = DBusProxy(...)
        proxy.MyMethod("(is)", 42, "hello")

    To get a D-Bus property, also use the standart pythonic way.

    .. code-block:: python

        from ignis.dbus import DBusProxy
        proxy = DBusProxy(...)
        value = proxy.MyValue
        print(value)
    """

    def __init__(
        self,
        name: str,
        object_path: str,
        interface_name: str,
        info: Gio.DBusInterfaceInfo,
    ):
        super().__init__()
        self._name = name
        self._object_path = object_path
        self._interface_name = interface_name
        self._info = info

        self._methods: list[str] = []
        self._properties: list[str] = []

        self._proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE,
            info,
            name,
            object_path,
            interface_name,
            None,
        )

        for i in info.methods:
            self._methods.append(i.name)

        for i in info.properties:  # type: ignore
            self._properties.append(i.name)

    @GObject.Property
    def name(self) -> str:
        return self._name

    @GObject.Property
    def object_path(self) -> str:
        return self._object_path

    @GObject.Property
    def interface_name(self) -> str:
        return self._interface_name

    @GObject.Property
    def info(self) -> Gio.DBusInterfaceInfo:
        return self._info

    @GObject.Property
    def connection(self) -> Gio.DBusConnection:
        return self._proxy.get_connection()

    @GObject.Property
    def proxy(self) -> Gio.DBusProxy:
        return self._proxy

    @GObject.Property
    def methods(self) -> list[str]:
        return self._methods

    @GObject.Property
    def properties(self) -> list[str]:
        return self._properties

    @GObject.Property
    def has_owner(self) -> bool:
        dbus = DBusProxy(
            name="org.freedesktop.DBus",
            object_path="/org/freedesktop/DBus",
            interface_name="org.freedesktop.DBus",
            info=Utils.load_interface_xml("org.freedesktop.DBus"),
        )
        return dbus.NameHasOwner("(s)", self.name)

    def __getattr__(self, name: str) -> Any:
        if name in self.methods:
            return getattr(self._proxy, name)
        elif name in self.properties:
            return self.__get_dbus_property(name)
        else:
            return super().__getattribute__(name)

    def signal_subscribe(
        self,
        signal_name: str,
        callback: Callable | None = None,
    ) -> int:
        """
        Subscribe to D-Bus signal.

        Args:
            signal_name (``str``): The signal name to subscribe.
            callback (``Callable``, optional): A function to call when signal is emitted.
        Returns:
            ``int``: a subscription ID that can be used with :func:`~ignis.dbus.DBusProxy.signal_unsubscribe`
        """
        return self.connection.signal_subscribe(
            self.name,
            self.interface_name,
            signal_name,
            self.object_path,
            None,
            Gio.DBusSignalFlags.NONE,
            callback,
        )

    def signal_unsubscribe(self, id: int) -> None:
        """
        Unsubscribe from D-Bus signal.

        Args:
            id (``int``): The ID of the subscription.
        """
        self.connection.signal_unsubscribe(id)

    def __get_dbus_property(self, property_name: str) -> Any:
        try:
            return self.connection.call_sync(
                self.name,
                self.object_path,
                "org.freedesktop.DBus.Properties",
                "Get",
                GLib.Variant(
                    "(ss)",
                    (self.interface_name, property_name),
                ),
                None,
                Gio.DBusCallFlags.NONE,
                -1,
                None,
            )[0]
        except GLib.GError:  # type: ignore
            return None

    def watch_name(
        self,
        on_name_appeared: Callable | None = None,
        on_name_vanished: Callable | None = None,
    ) -> None:
        """
        Watch ``name``.

        Args:
            on_name_appeared (``Callable``, optional): A function to call when ``name`` appeared.
            on_name_vanished (``Callable``, optional): A function to call when ``name`` vanished.
        """
        self._watcher = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            self.name,
            Gio.BusNameWatcherFlags.NONE,
            on_name_appeared,
            on_name_vanished,
        )

    def unwatch_name(self) -> None:
        """
        Unwatch name.
        """
        Gio.bus_unwatch_name(self._watcher)