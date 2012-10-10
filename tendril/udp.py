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

import gevent
from gevent import event
from gevent import queue
from gevent import socket

from tendril import application
from tendril import connection
from tendril import manager
from tendril import utils


class UDPTendril(connection.Tendril):
    """
    Manages state associated with a single UDP "connection".
    """

    proto = 'udp'

    def send_frame(self, frame):
        """
        Sends a frame to the other end of the connection.
        """

        # Get the socket
        sock = self.manager.sock

        if not sock:
            raise ValueError("UDPTendrilManager not running")

        # Send the packet
        try:
            sock.sendto(self._send_streamify(frame), self.remote_addr)
        except Exception:
            # We're a best-effort service anyway, so ignore exceptions
            pass

    def close(self):
        """
        Close the connection.
        """

        # Untrack the tendril
        super(UDPTendril, self).close()


class UDPTendrilManager(manager.TendrilManager):
    """
    Manages new connections through a particular endpoint.  Handles
    accepting new connections and creating new outgoing connections.
    This class includes the attribute ``recv_bufsize``, which allows
    tuning of the amount of data requested from the system for each
    call to the socket ``recvfrom()`` method.  This class also
    provides the property ``sock``, allowing access to the underlying
    ``socket`` object (or its wrapper).
    """

    proto = 'udp'
    recv_bufsize = 4096

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

        super(UDPTendrilManager, self).__init__(endpoint)

        # Need a place to store the socket
        self._sock = None
        self._sock_event = event.Event()
        self._sock_event.clear()

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

        super(UDPTendrilManager, self).start(acceptor, wrapper)

        # Reset the socket and socket event
        self._sock = None
        self._sock_event.clear()

    def stop(self, *args):
        """
        Stops the TendrilManager.  Requires cooperation from the
        listener implementation, which must watch the ``running``
        attribute and ensure that it stops accepting connections
        should that attribute become False.  Note that some tendril
        managers will not exit from the listening thread until all
        connections have been closed.
        """

        super(UDPTendrilManager, self).stop(*args)

        # Reset the socket and socket event
        self._sock = None
        self._sock_event.clear()

    def shutdown(self):
        """
        Unconditionally shuts the TendrilManager down, killing all
        threads and closing all tendrils.
        """

        super(UDPTendrilManager, self).shutdown()

        # Reset the socket and socket event
        self._sock = None
        self._sock_event.clear()

    def connect(self, target, acceptor):
        """
        Initiate a connection from the tendril manager's endpoint.
        Once the connection is completed, a UDPTendril object will be
        created and passed to the given acceptor.

        :param target: The target of the connection attempt.
        :param acceptor: A callable which will initialize the state of
                         the new UDPTendril object.
        """

        # Call some common sanity-checks
        super(UDPTendrilManager, self).connect(target, acceptor, None)

        # Construct the Tendril
        tend = UDPTendril(self, self.local_addr, target)

        try:
            # Set up the application
            tend.application = acceptor(tend)
        except application.RejectConnection:
            # The acceptor raised a RejectConnection
            return None

        # OK, let's track the tendril
        self._track_tendril(tend)

        # Might as well return the tendril, too
        return tend

    def listener(self, acceptor, wrapper):
        """
        Listens for new connections to the manager's endpoint.  Once a
        new connection is received, a UDPTendril object is generated
        for it and it is passed to the acceptor, which must initialize
        the state of the connection.  If no acceptor is given, no new
        connections can be initialized.

        :param acceptor: If given, specifies a callable that will be
                         called with each newly received UDPTendril;
                         that callable is responsible for initial
                         acceptance of the connection and for setting
                         up the initial state of the connection.  If
                         not given, no new connections will be
                         accepted by the UDPTendrilManager.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.
        """

        # OK, set up the socket
        sock = socket.socket(self.addr_family, socket.SOCK_DGRAM)

        with utils.SocketCloser(sock):
            # Bind to our endpoint
            sock.bind(self.endpoint)

            # Get the assigned port number
            self.local_addr = sock.getsockname()

            # Call any wrappers
            if wrapper:
                sock = wrapper(sock)

        # Senders need the socket, too...
        self._sock = sock
        self._sock_event.set()

        # OK, now go into the listening loop with an error threshold
        # of 10
        closer = utils.SocketCloser(sock, 10,
                                    ignore=[application.RejectConnection])
        while True:
            with closer:
                data, addr = sock.recvfrom(self.recv_bufsize)

                # Look up the tendril or create a new one
                try:
                    tend = self[(self.local_addr, addr)]
                except KeyError:
                    if not acceptor:
                        # Can't accept new connections
                        continue

                    # Construct a Tendril
                    tend = UDPTendril(self, self.local_addr, addr)

                    # Set up the application
                    tend.application = acceptor(tend)

                    # OK, let's track the tendril
                    self._track_tendril(tend)

                # We now have a tendril; process the received data
                try:
                    tend._recv_frameify(data)
                except Exception as exc:
                    # Close the Tendril
                    tend.close()

                    # Notify the application what happened
                    tend.closed(exc)

    @property
    def sock(self):
        """
        Retrieve the socket the UDPTendrilManager is listening on.
        """

        # If we're not running, just return None
        if not self.running:
            return None

        # OK, we're running; wait on the _sock_event
        self._sock_event.wait()

        # Return the socket
        return self._sock
