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

import socket
import sys
import time

import gevent
from gevent import event
from gevent import coros

from tendril import connection
from tendril import framers
from tendril import manager


class TCPTendril(connection.Tendril):
    default_framer = framers.LineFramer
    proto = 'tcp'
    recv_bufsize = 4096

    def __init__(self, manager, sock, remote_addr=None):
        super(TCPTendril, self).__init__(manager,
                                         sock.getsockname(),
                                         remote_addr or sock.getpeername())

        self._sock = sock

        self._sendbuf_event = event.Event()
        self._sendbuf = ''

        self._recv_thread = None
        self._send_thread = None

        self._recv_lock = None
        self._send_lock = None

        self._restart = event.Event()

    def _start(self):
        # Initialize the locks
        self._recv_lock = coros.Semaphore(0)
        self._send_lock = coros.Semaphore(0)

        # Make sure the threads can restart
        self._restart.set()

        # Boot the threads
        self._recv_thread = gevent.spawn(self._recv)
        self._send_thread = gevent.spawn(self._send)

        # Link the threads such that we get notified if one or the
        # other exits
        self._recv_thread.link(self._thread_error)
        self._send_thread.link(self._thread_error)

    def _recv(self):
        # Outer loop: receive some data
        while True:
            # Wait until we can go
            if self._restart.is_set():
                self._recv_lock.release()
                self._restart.wait()
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

    def wrap(wrapper):
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
            self._restart.clear()

            # Now wait until they're at a stopping point
            self._recv_lock.acquire()
            self._send_lock.acquire()

        # Wrap the socket
        self._sock = wrapper(self._sock)

        # OK, restart the send/recv threads
        if self._recv_thread and self._send_thread:
            # Release our locks
            self._send_lock.release()
            self._recv_lock.release()

            # And signal the all-clear
            self._restart.set()

    @property
    def sock(self):
        return self._sock

    def send_frame(self, frame):
        self._sendbuf += self._send_frameify(frame)
        self._sendbuf_event.set()

    def close(self):
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
    proto = 'tcp'
    backlog = 1024

    def connect(self, target, acceptor, wrapper=None):
        # Call some common sanity-checks
        super(TCPTendrilManager, self).connect(target, accept, wrapper)

        # Set up the socket
        sock = socket.socket(self.addr_family, socket.SOCK_STREAM)

        try:
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
        except Exception:
            # What comes next may overwrite the exception, so save it
            # for reraise later...
            exc_class, exc_value, exc_tb = sys.exc_info()

            # Make sure the socket is closed
            try:
                sock.close()
            except Exception:
                pass

            raise exc_class, exc_value, exc_tb

        # OK, let's track the tendril
        self._track_tendril(tend)

        # Might as well return the tendril, too
        return tend

    def listener(self, acceptor, wrapper):
        # If we have no acceptor, there's nothing for us to do here
        if not acceptor:
            # Just sleep in a loop
            while True:
                gevent.sleep(600)
            return

        # OK, set up the socket
        sock = socket.socket(self.addr_family, socket.SOCK_STREAM)

        try:
            # Set up SO_REUSEADDR
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Bind to our endpoint
            sock.bind(self.endpoint)

            # Call any wrappers
            if wrapper:
                sock = wraper(sock)

            # Initiate listening
            sock.listen(self.backlog)
        except Exception:
            # What comes next may overwrite the exception, so save it
            # for reraise later...
            exc_class, exc_value, exc_tb = sys.exc_info()

            # Make sure the socket is closed
            try:
                sock.close()
            except Exception:
                pass

            raise exc_class, exc_value, exc_tb

        # OK, now go into an accept loop
        err_thresh = 0
        while True:
            try:
                cli, addr = serv.accept()

                # OK, the connection has been accepted; construct a
                # Tendril for it
                tend = TCPTendril(self, cli, addr)

                # Set up the application
                try:
                    tend.application = acceptor(tend)
                except Exception:
                    # Make sure the connection is closed
                    cli.close()
                    raise
            except Exception:
                # Do something if we're in an error loop
                err_thresh += 1
                if err_thresh >= 10:
                    raise
                continue

            # Decrement the error threshold
            err_thresh = max(err_thresh - 1, 0)

            # Make sure we track the new tendril
            self._track_tendril(tend)
