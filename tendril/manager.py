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
import pkg_resources


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
    _running_managers = weakref.WeakValueDictionary()

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
                         connections.  If not given, defaults to ('',
                         0).
        """

        # First, normalize the proto and endpoint
        proto = proto.tolower()
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

    def __init__(self, endpoint=None):
        """
        Initialize a TendrilManager.

        :param endpoint: Identifies the endpoint of the
                         TendrilManager.  This will be the IP address
                         and port number, as a tuple, on which to
                         accept connections and from which to initiate
                         connections.  If not given, defaults to ('',
                         0).
        """

        self.endpoint = endpoint or ('', 0)
        self.tendrils = {}
        self.running = False

        self._listen_thread = None

        # Make sure we don't already exist...
        if self._manager_key in self._managers:
            raise ValueError("Identical TendrilManager already exists")

        # Save a reference to ourself
        self._managers[self._manager_key] = self

    def __getitem__(self, addr):
        """
        Finds the tendril corresponding to the given remote address.
        Returns the Tendril object, or raises KeyError if the tendril
        is not tracked by this TendrilManager.
        """

        return self.tendrils[addr]

    def _track_tendril(self, tendril):
        """
        Adds the tendril to the set of tracked tendrils.
        """

        self.tendrils[tendril.addr] = tendril

    def _untrack_tendril(self, tendril):
        """
        Removes the tendril from the set of tracked tendrils.
        """

        try:
            del self.tendrils[tendril.addr]
        except KeyError:
            pass

    def start(self, acceptor=None, wrapper=None, *args, **kwargs):
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
                        socket.socket object.  All other positional
                        and keyword arguments will be passed to this
                        wrapping callable.  The callable must return a
                        valid proxy for the socket.socket object,
                        which will subsequently be used to communicate
                        on the connection.
        """

        # Don't allow a double-start
        if self.running:
            raise ValueError("TendrilManager already running")

        # Look out for conflicts
        if self._manager_key in self._running_managers:
            raise ValueError("Identical TendrilManager already exists")

        # In a moment, we will begin running
        self.running = True

        # Add ourself to the dictionary of running managers
        self._running_managers[self._manager_key] = self

        # Start the listening thread
        self._listen_thread = gevent.spawn(self.listener, acceptor,
                                           wrapper, args, kwargs)

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
        self._listen_thread = None

    @property
    def _manager_key(self):
        """
        Returns a unique key identifying this manager.
        """

        return (self.proto, self.endpoint)

    @abc.abstractmethod
    def connect(self, target, acceptor, wrapper=None, *args, **kwargs):
        """
        Initiate a connection from the tendril manager's endpoint.
        Once the connection is completed, a Tendril object will be
        created and passed to the given acceptor.  The acceptor should
        examine the Tendril object to see if any errors occurred.

        :param target: The target of the connection attempt.
        :param acceptor: A callable which will initialize the state of
                         the new Tendril object.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  All other positional
                        and keyword arguments will be passed to this
                        wrapping callable.  The callable must return a
                        valid proxy for the socket.socket object,
                        which will subsequently be used to communicate
                        on the connection.
        """

        if not self.running:
            raise ValueError("TendrilManager not running")

    @abc.abstractmethod
    def listener(self, acceptor, wrapper, args, kwargs):
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
        :param args: A sequence of arguments to pass to the wrapper.
        :param kwargs: A dictionary of keyword arguments to pass to
                       the wrapper.
        """

        pass

    @abc.abstractproperty
    def proto(self):
        """Retrieve the name of the underlying network protocol."""

        pass
