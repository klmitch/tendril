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
from gevent import coros
from gevent import event
from gevent import socket

from tendril import application
from tendril import connection
from tendril import framers
from tendril import manager
from tendril import utils


class TCPTendril(connection.Tendril):
    """
    Manages state associated with a single TCP connection.  In
    addition to the attributes available on the Tendril class, this
    class includes the attribute ``recv_bufsize``, which allows tuning
    of the amount of data requested from the system for each call to
    the socket ``recv()`` method.  This class also provides the
    property ``sock``, allowing access to the underlying ``socket``
    object (or its wrapper).
    """

    default_framer = framers.LineFramer
    proto = 'tcp'
    recv_bufsize = 4096

    def __init__(self, manager, sock, remote_addr=None):
        """
        Initialize a TCPTendril.

        :param manager: The TCPTendrilManager responsible for the
                        Tendril.
        :param sock: The socket for the underlying connection.
        :param remote_addr: The address of the remote end of the
                            connection represented by the TCPTendril.
                            If not provided, will be derived by
                            calling the ``getpeername()`` method on
                            the socket.
        """

        super(TCPTendril, self).__init__(manager,
                                         sock.getsockname(),
                                         remote_addr or sock.getpeername())

        self._sock = sock

        # Send buffer and support
        self._sendbuf_event = event.Event()
        self._sendbuf = ''

        # Thread objects for the send and receive threads
        self._recv_thread = None
        self._send_thread = None

        # Locks for the send and receive threads
        self._recv_lock = None
        self._send_lock = None

    def _start(self):
        """
        Starts the underlying send and receive threads.
        """

        # Initialize the locks
        self._recv_lock = coros.Semaphore(0)
        self._send_lock = coros.Semaphore(0)

        # Boot the threads
        self._recv_thread = gevent.spawn(self._recv)
        self._send_thread = gevent.spawn(self._send)

        # Link the threads such that we get notified if one or the
        # other exits
        self._recv_thread.link(self._thread_error)
        self._send_thread.link(self._thread_error)

    def _recv(self):
        """
        Implementation of the receive thread.  Waits for data to
        arrive on the socket, then passes the data through the defined
        receive framer and sends it on to the application.
        """

        # Outer loop: receive some data
        while True:
            # Wait until we can go
            self._recv_lock.release()
            gevent.sleep()  # Yield to another thread
            self._recv_lock.acquire()

            recv_buf = self._sock.recv(self.recv_bufsize)

            # If it's empty, the peer closed the other end
            if not recv_buf:
                # Manually kill the send thread; do this manually
                # instead of calling close() because close() will kill
                # us, and since close() would be running in our thread
                # context, it would never get around to killing the
                # send thread
                if self._send_thread:
                    self._send_thread.kill()
                    self._send_thread = None

                # Manually close the socket
                self._sock.close()
                self._sock = None

                # Make sure the manager knows we're closed
                super(TCPTendril, self).close()

                # Notify the application
                self.closed()

                # As our last step, commit seppuku; this will keep
                # _thread_error() from notifying the application of an
                # erroneous exit from the receive thread
                raise gevent.GreenletExit()

            # Process the received data
            self._recv_frameify(recv_buf)

    def _send(self):
        """
        Implementation of the send thread.  Waits for data to be added
        to the send buffer, then passes as much of the buffered data
        to the socket ``send()`` method as possible.
        """

        # Outer loop: wait for data to send
        while True:
            # Release the send lock and wait for data, then reacquire
            # the send lock
            self._send_lock.release()
            self._sendbuf_event.wait()
            self._send_lock.acquire()

            # Inner loop: send as much data as we can
            while self._sendbuf:
                sent = self._sock.send(self._sendbuf)

                # Trim that much data off the send buffer, so we don't
                # accidentally re-send anything
                self._sendbuf = self._sendbuf[sent:]

            # OK, _sendbuf is empty; clear the event so we'll sleep
            self._sendbuf_event.clear()

    def _thread_error(self, thread):
        """
        Handles the case that the send or receive thread exit or throw
        an exception.
        """

        # Avoid double-killing the thread
        if thread == self._send_thread:
            self._send_thread = None
        if thread == self._recv_thread:
            self._recv_thread = None

        # Figure out why the thread exited
        if thread.successful():
            exception = socket.error('thread exited prematurely')
        elif isinstance(thread.exception, gevent.GreenletExit):
            # Thread was killed; don't do anything but close
            self.close()
            return
        else:
            exception = thread.exception

        # Close the connection...
        self.close()

        # Notify the application what happened
        self.closed(exception)

    def wrap(self, wrapper):
        """
        Allows the underlying socket to be wrapped, as by an SSL
        connection.

        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.

        Note: Be extremely careful with calling this method after the
        TCP connection has been initiated.  The action of this method
        affects both sending and receiving streams simultaneously, and
        no attempt is made to deal with buffered data, other than
        ensuring that both the sending and receiving threads are at
        stopping points.
        """

        if self._recv_thread and self._send_thread:
            # Have to suspend the send/recv threads
            self._recv_lock.acquire()
            self._send_lock.acquire()

        # Wrap the socket
        self._sock = wrapper(self._sock)

        # OK, restart the send/recv threads
        if self._recv_thread and self._send_thread:
            # Release our locks
            self._send_lock.release()
            self._recv_lock.release()

    @property
    def sock(self):
        """
        Retrieve the underlying socket object.  Read-only.
        """

        return self._sock

    def send_frame(self, frame):
        """
        Sends a frame to the other end of the connection.
        """

        self._sendbuf += self._send_streamify(frame)
        self._sendbuf_event.set()

    def close(self):
        """
        Close the connection.  Kills the send and receive threads, as
        well as closing the underlying socket.
        """

        if self._recv_thread:
            self._recv_thread.kill()
            self._recv_thread = None

        if self._send_thread:
            self._send_thread.kill()
            self._send_thread = None

        if self._sock:
            self._sock.close()
            self._sock = None

        # Make sure to notify the manager we're closed
        super(TCPTendril, self).close()


class TCPTendrilManager(manager.TendrilManager):
    """
    Manages new connections through a particular endpoint.  Handles
    accepting new connections and creating new outgoing connections.
    This class includes the attribute ``backlog``, which allows tuning
    of the size of the backlog passed to the socket ``listen()``
    method.
    """

    proto = 'tcp'
    backlog = 1024

    def connect(self, target, acceptor, wrapper=None):
        """
        Initiate a connection from the tendril manager's endpoint.
        Once the connection is completed, a TCPTendril object will be
        created and passed to the given acceptor.

        :param target: The target of the connection attempt.
        :param acceptor: A callable which will initialize the state of
                         the new TCPTendril object.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.

        For passing extra arguments to the acceptor or the wrapper,
        see the ``TendrilPartial`` class; for chaining together
        multiple wrappers, see the ``WrapperChain`` class.
        """

        # Call some common sanity-checks
        super(TCPTendrilManager, self).connect(target, acceptor, wrapper)

        # Set up the socket
        sock = socket.socket(self.addr_family, socket.SOCK_STREAM)

        with utils.SocketCloser(sock, ignore=[application.RejectConnection]):
            # Bind to our endpoint
            sock.bind(self.endpoint)

            # Connect to our target
            sock.connect(target)

            # Call any wrappers
            if wrapper:
                sock = wrapper(sock)

            # Now, construct a Tendril
            tend = TCPTendril(self, sock)

            # Finally, set up the application
            tend.application = acceptor(tend)

            # OK, let's track the tendril
            self._track_tendril(tend)

            # Start the tendril
            tend._start()

            # Might as well return the tendril, too
            return tend

        # The acceptor raised a RejectConnection exception, apparently
        sock.close()
        return None

    def listener(self, acceptor, wrapper):
        """
        Listens for new connections to the manager's endpoint.  Once a
        new connection is received, a TCPTendril object is generated
        for it and it is passed to the acceptor, which must initialize
        the state of the connection.  If no acceptor is given, no new
        connections can be initialized.

        :param acceptor: If given, specifies a callable that will be
                         called with each newly received TCPTendril;
                         that callable is responsible for initial
                         acceptance of the connection and for setting
                         up the initial state of the connection.  If
                         not given, no new connections will be
                         accepted by the TCPTendrilManager.
        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.
        """

        # If we have no acceptor, there's nothing for us to do here
        if not acceptor:
            # Not listening on anything
            self.local_addr = None

            # Just sleep in a loop
            while True:
                gevent.sleep(600)
            return

        # OK, set up the socket
        sock = socket.socket(self.addr_family, socket.SOCK_STREAM)

        with utils.SocketCloser(sock):
            # Set up SO_REUSEADDR
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to our endpoint
            sock.bind(self.endpoint)

            # Get the assigned port number
            self.local_addr = sock.getsockname()

            # Call any wrappers
            if wrapper:
                sock = wrapper(sock)

            # Initiate listening
            sock.listen(self.backlog)

        # OK, now go into an accept loop with an error threshold of 10
        closer = utils.SocketCloser(sock, 10,
                                    ignore=[application.RejectConnection])
        while True:
            with closer:
                cli, addr = sock.accept()

                # OK, the connection has been accepted; construct a
                # Tendril for it
                tend = TCPTendril(self, cli, addr)

                # Set up the application
                with utils.SocketCloser(cli):
                    tend.application = acceptor(tend)

                    # Make sure we track the new tendril, but only if
                    # the acceptor doesn't throw any exceptions
                    self._track_tendril(tend)

                    # Start the tendril
                    tend._start()
