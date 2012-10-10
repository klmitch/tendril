## Copyright (C) 2012 by Kevin L. Mitchell <klmitch@mit.edu>
##
## This program is free software: you can redistribute it and/or
## modify it under the terms of the GNU General Public License as
## published by the Free Software Foundation, either version 3 of the
## License, or (at your option) any later version.
##
## This program is distributed in the hope that it will be useful, but
## WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
## General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see
## <http://www.gnu.org/licenses/>.

import abc
import weakref

import gevent
from gevent import event
import pkg_resources

from tendril import utils


__all__ = ["get_manager", "find_tendril"]


class TendrilManager(object):
    """
    Manages all connections through a particular endpoint.  Handles
    accepting new connections, creating new outgoing connections, and
    buffering data to and from the network in the case of network
    protocols that do not provide connection state (i.e., UDP).  This
    is an abstract base class; see the tcp.py and udp.py files for
    implementations.

    The TendrilManager wraps connection state in a Tendril object,
    which provides the necessary information to maintain state for the
    connection--including application-provided state.  Application
    state should subclass the tendril.ApplicationState class.
    """

    __metaclass__ = abc.ABCMeta

    _managers = weakref.WeakValueDictionary()
    _tendrils = {}
    _running_managers = {}

    @classmethod
    def get_manager(cls, proto, endpoint=None):
        """
        Find a manager matching the given protocol and endpoint.  If
        no matching manager currently exists, creates a new one.
        (Manager classes are looked up using the ``tendril.manager``
        entrypoint, and the name of the entrypoint corresponds to the
        ``proto``.  This method makes no guarantees about whether the
        manager is running; make sure to check the ``running``
        attribute and call the ``start()`` method if necessary.

        :param proto: The underlying network protocol, such as "tcp"
                      or "udp".
        :param endpoint: Identifies the endpoint of the
                         TendrilManager.  This will be the IP address
                         and port number, as a tuple, on which to
                         accept connections and from which to initiate
                         connections.  If not given, defaults to
                         ``('', 0)``.

        Note: TendrilManager instances can only support one of IPv4 or
        IPv6, and outgoing connection addresses must match how the
        TendrilManager was initialized.  To get a TendrilManager
        supporting outgoing IPv6 connections, use the endpoint
        ``('::', 0)``.
        """

        # First, normalize the proto and endpoint
        proto = proto.lower()
        endpoint = endpoint or ('', 0)

        # See if the manager already exists
        if (proto, endpoint) in cls._managers:
            return cls._managers[(proto, endpoint)]

        # OK, need to create a new one; use pkg_resources
        for ep in pkg_resources.iter_entry_points('tendril.manager', proto):
            try:
                manager_cls = ep.load()
                break
            except (ImportError, pkg_resources.UnknownExtra):
                continue
        else:
            raise ValueError("unknown protocol %r" % proto)

        return manager_cls(endpoint)

    @classmethod
    def find_tendril(cls, proto, addr):
        """
        Finds the tendril corresponding to the protocol and address
        tuple.  Returns the Tendril object, or raises KeyError if the
        tendril is not tracked.

        The address tuple is the tuple of the local address and the
        remote address for the tendril.
        """

        # First, normalize the proto
        proto = proto.lower()

        # Now, find and return the tendril
        return cls._tendrils[proto][addr]

    def __init__(self, endpoint=None):
        """
        Initialize a TendrilManager.

        :param endpoint: Identifies the endpoint of the
                         TendrilManager.  This will be the IP address
                         and port number, as a tuple, on which to
                         accept connections and from which to initiate
                         connections.  If not given, defaults to
                         ``('', 0)``.

        Note: TendrilManager instances can only support one of IPv4 or
        IPv6, and outgoing connection addresses must match how the
        TendrilManager was initialized.  To get a TendrilManager
        supporting outgoing IPv6 connections, use the endpoint
        ``('::', 0)``.
        """

        self.endpoint = endpoint or ('', 0)
        self.addr_family = utils.addr_info(self.endpoint)
        self.tendrils = {}
        self.running = False
        self._local_addr = None
        self._local_addr_event = event.Event()
        self._local_addr_event.clear()

        self._listen_thread = None

        # Make sure we don't already exist...
        if self._manager_key in self._managers:
            raise ValueError("Identical TendrilManager already exists")

        # Save a reference to ourself
        self._managers[self._manager_key] = self

    def __contains__(self, addr):
        """
        Finds if a tendril corresponding to the address tuple exists.
        Returns ``True`` if it does or ``False`` otherwise.

        The address tuple is the tuple of the local address and the
        remote address for the tendril.
        """

        return addr in self.tendrils

    def __getitem__(self, addr):
        """
        Finds the tendril corresponding to the address tuple.  Returns
        the Tendril object, or raises KeyError if the tendril is not
        tracked by this TendrilManager.

        The address tuple is the tuple of the local address and the
        remote address for the tendril.
        """

        return self.tendrils[addr]

    def _track_tendril(self, tendril):
        """
        Adds the tendril to the set of tracked tendrils.
        """

        self.tendrils[tendril._tendril_key] = tendril

        # Also add to _tendrils
        self._tendrils.setdefault(tendril.proto, weakref.WeakValueDictionary())
        self._tendrils[tendril.proto][tendril._tendril_key] = tendril

    def _untrack_tendril(self, tendril):
        """
        Removes the tendril from the set of tracked tendrils.
        """

        try:
            del self.tendrils[tendril._tendril_key]
        except KeyError:
            pass

        # Also remove from _tendrils
        try:
            del self._tendrils[tendril.proto][tendril._tendril_key]
        except KeyError:
            pass

    def start(self, acceptor=None, wrapper=None):
        """
        Starts the TendrilManager.

        :param acceptor: If given, specifies a callable that will be
                         called with each newly received Tendril;
                         that callable is responsible for initial
                         acceptance of the connection and for setting
                         up the initial state of the connection.  If
                         not given, no new connections will be
                         accepted by the TendrilManager.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.

        For passing extra arguments to the acceptor or the wrapper,
        see the ``TendrilPartial`` class; for chaining together
        multiple wrappers, see the ``WrapperChain`` class.
        """

        # Don't allow a double-start
        if self.running:
            raise ValueError("TendrilManager already running")

        # Look out for conflicts
        if self._manager_key in self._running_managers:
            raise ValueError("Identical TendrilManager already exists")

        # In a moment, we will begin running
        self.running = True
        self._local_addr = None
        self._local_addr_event.clear()

        # Add ourself to the dictionary of running managers
        self._running_managers[self._manager_key] = self

        # Start the listening thread
        self._listen_thread = gevent.spawn(self.listener, acceptor,
                                           wrapper)

        # Make sure to reset running if it exits
        self._listen_thread.link(self.stop)

    def stop(self, *args):
        """
        Stops the TendrilManager.  Requires cooperation from the
        listener implementation, which must watch the ``running``
        attribute and ensure that it stops accepting connections
        should that attribute become False.  Note that some tendril
        managers will not exit from the listening thread until all
        connections have been closed.
        """

        # Remove ourself from the dictionary of running managers
        try:
            del self._running_managers[self._manager_key]
        except KeyError:
            pass

        self.running = False
        self._local_addr = None
        self._local_addr_event.clear()

    def shutdown(self):
        """
        Unconditionally shuts the TendrilManager down, killing all
        threads and closing all tendrils.
        """

        # Remove ourself from the dictionary of running managers
        try:
            del self._running_managers[self._manager_key]
        except KeyError:
            pass

        # Kill the listening thread
        self._listen_thread.kill()

        # Close all the connections
        for conn in self.tendrils.values():
            conn.close()

        # Ensure all data is appropriately reset
        self.tendrils = {}
        self.running = False
        self._local_addr = None
        self._local_addr_event.clear()
        self._listen_thread = None

    def get_local_addr(self, timeout=None):
        """
        Retrieve the current local address.

        :param timeout: If not given or given as ``None``, waits until
                        the local address is available.  Otherwise,
                        waits for as long as specified.  If the local
                        address is not set by the time the timeout
                        expires, returns ``None``.
        """

        # If we're not running, just return None
        if not self.running:
            return None

        # OK, we're running; wait on the _local_addr_event
        if not self._local_addr_event.wait(timeout):
            # Still not set after timeout
            return None

        # We have a local address!
        return self._local_addr

    @property
    def _manager_key(self):
        """
        Returns a unique key identifying this manager.
        """

        return (self.proto, self.endpoint)

    @property
    def local_addr(self):
        """
        Retrieve the local address the manager is listening on.
        """

        return self.get_local_addr()

    @local_addr.setter
    def local_addr(self, value):
        """
        Set the local address the manager is listening on.  Notifies
        all waiters that the address is available.
        """

        self._local_addr = value
        self._local_addr_event.set()

    @abc.abstractmethod
    def connect(self, target, acceptor, wrapper=None):
        """
        Initiate a connection from the tendril manager's endpoint.
        Once the connection is completed, a Tendril object will be
        created and passed to the given acceptor.

        :param target: The target of the connection attempt.
        :param acceptor: A callable which will initialize the state of
                         the new Tendril object.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.

        For passing extra arguments to the acceptor or the wrapper,
        see the ``TendrilPartial`` class; for chaining together
        multiple wrappers, see the ``WrapperChain`` class.
        """

        if not self.running:
            raise ValueError("TendrilManager not running")

        # Check the target address
        fam = utils.addr_info(target)

        # Verify that we're in the right family
        if self.addr_family != fam:
            raise ValueError("address family mismatch")

    @abc.abstractmethod
    def listener(self, acceptor, wrapper):
        """
        Listens for new connections to the manager's endpoint.  Once a
        new connection is received, a Tendril object is generated
        for it and it is passed to the acceptor, which must initialize
        the state of the connection.  If no acceptor is given, no new
        connections can be initialized, but some tendril managers
        still need a listening thread anyway.

        :param acceptor: If given, specifies a callable that will be
                         called with each newly received Tendril;
                         that callable is responsible for initial
                         acceptance of the connection and for setting
                         up the initial state of the connection.  If
                         not given, no new connections will be
                         accepted by the TendrilManager.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.
        """

        pass

    @abc.abstractproperty
    def proto(self):
        """Retrieve the name of the underlying network protocol."""

        pass


get_manager = TendrilManager.get_manager
find_tendril = TendrilManager.find_tendril
