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
import collections

from tendril import application
from tendril import framers


__all__ = ["TendrilFramers", "TendrilFramerStates"]


TendrilFramers = collections.namedtuple('TendrilFramers', ['send', 'recv'])
TendrilFramerStates = collections.namedtuple('TendrilFramerStates',
                                             ['send', 'recv'])


class Tendril(object):
    """
    Manages state associated with a single logical connection, called
    a "tendril".  This is an abstract base class; see the tcp.py and
    udp.py files for implementations.

    Several attributes are available on all subclasses.  They
    include::

    ``manager``
      The responsible TendrilManager.

    ``endpoint``
      The address of the local socket, as a (host, port) tuple.

    ``addr``
      The address of the remote socket, as a (host, port) tuple.

    ``application``
      The application object.  May be changed by the application.
      Should be a subclass of ``tendril.Application``.

    ``recv_framer``
      An instance of a class which chops a received stream into a
      logical sequence of frames, buffering any incomplete frames.

    ``send_framer``
      An instance of a class which assembles sent frames into a
      stream, buffering any incomplete packets.

    ``proto``
      The name of the underlying network protocol.

    ``error``
      An exception object describing the most recent error observed on
      the tendril.  Will be cleared once accessed.  Will be None in
      the event the connection was closed by the peer.
    """

    __metaclass__ = abc.ABCMeta

    default_framer = framers.IdentityFramer

    def __init__(self, manager, local_addr, remote_addr):
        """
        Initialize a Tendril.

        :param manager: The TendrilManager responsible for the
                        Tendril.
        :param local_addr: The address of the local end of the
                           connection represented by the Tendril.
        :param remote_addr: The address of the remote end of the
                            connection represented by the Tendril.
        """

        self.manager = manager
        self.local_addr = local_addr
        self.remote_addr = remote_addr

        self._application = None

        # Set the initial framer
        f = self.default_framer()
        self._send_framer = f
        self._recv_framer = f

        # Set up state for the framer
        self._send_framer_state = framers.FrameState()
        self._recv_framer_state = framers.FrameState()

    def _send_streamify(self, frame):
        """
        Helper method to streamify a frame.
        """

        # Get the state and framer
        state = self._send_framer_state
        framer = self._send_framer

        # Reset the state as needed
        state._reset(framer)

        # Now pass the frame through streamify() and return the result
        return framer.streamify(state, frame)

    def _recv_frameify(self, data):
        """
        Helper method to frameify a stream.
        """

        # Get the state and framer
        state = self._recv_framer_state
        framer = None

        # Grab off as many frames as we can
        frameify = None
        while True:
            # Check if we need to change framers
            if framer != self._recv_framer:
                # Notify the currently-running framer
                if frameify:
                    try:
                        frameify.throw(framers.FrameSwitch)
                    except StopIteration:
                        pass

                # Set up the new framer
                framer = self._recv_framer
                state._reset(framer)
                frameify = framer.frameify(state, data)
                data = ''  # Now part of the state's buffer

            # Get the next frame
            try:
                frame = frameify.next()
            except StopIteration:
                # OK, we've extracted as many frames as we can
                break

            # OK, send the frame to the application
            if self._application:
                self._application.recv_frame(frame)

    def wrap(self, wrapper):
        """
        Allows the underlying socket to be wrapped, as by an SSL
        connection.  Not implemented by all Tendril subclasses.

        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  The callable must
                        return a valid proxy for the socket.socket
                        object, which will subsequently be used to
                        communicate on the connection.
        """

        raise NotImplementedError("Cannot wrap this connection")

    def closed(self, error=None):
        """
        Notify the application that the connection has been closed.

        :param error: The exception which has caused the connection to
                      be closed.  If the connection has been closed
                      due to an EOF, pass ``None``.
        """

        if self._application:
            try:
                self._application.closed(error)
            except Exception:
                # Ignore exceptions from the notification
                pass

    @property
    def _tendril_key(self):
        """
        Retrieve a key which can be used to look up this tendril.
        """

        return self.local_addr, self.remote_addr

    @property
    def send_framer(self):
        """
        Retrieve the framer in use for the sending side of the
        connection.
        """

        return self._send_framer

    @send_framer.setter
    def send_framer(self, value):
        """
        Set the framer in use for the sending side of the connection.
        The framer state will be reset next time the framer is used.
        """

        if not isinstance(value, framers.Framer):
            raise ValueError("framer must be an instance of tendril.Framer")

        self._send_framer = value

    @send_framer.deleter
    def send_framer(self):
        """
        Reset the framer in use for the sending side of the connection
        to be a tendril.IdentityFramer.  The framer state will be
        reset next time the framer is used.
        """

        self._send_framer = self.default_framer()

    @property
    def send_framer_state(self):
        """
        Retrieve the framer state in use for the sending side of the
        connection.
        """

        return self._send_framer_state

    @property
    def recv_framer(self):
        """
        Retrieve the framer in use for the receiving side of the
        connection.
        """

        return self._recv_framer

    @recv_framer.setter
    def recv_framer(self, value):
        """
        Set the framer in use for the receiving side of the
        connection.  The framer state will be reset next time the
        framer is used.
        """

        if not isinstance(value, framers.Framer):
            raise ValueError("framer must be an instance of tendril.Framer")

        self._recv_framer = value

    @recv_framer.deleter
    def recv_framer(self):
        """
        Reset the framer in use for the receiving side of the
        connection to be a tendril.IdentityFramer.  The framer state
        will be reset next time the framer is used.
        """

        self._recv_framer = self.default_framer()

    @property
    def recv_framer_state(self):
        """
        Retrieve the framer state in use for the receiving side of the
        connection.
        """

        return self._recv_framer_state

    @property
    def framers(self):
        """
        Retrieve the framers in use for the connection.
        """

        return TendrilFramers(self._send_framer, self._recv_framer)

    @framers.setter
    def framers(self, value):
        """
        Set the framers in use for the connection.  The framer states
        will be reset next time their respective framer is used.
        """

        # Handle sequence values
        if isinstance(value, collections.Sequence):
            if len(value) != 2:
                raise ValueError('need exactly 2 values to unpack')
            elif (not isinstance(value[0], framers.Framer) or
                  not isinstance(value[1], framers.Framer)):
                raise ValueError("framer must be an instance of "
                                 "tendril.Framer")

            self._send_framer, self._recv_framer = value

        # If we have a single value, assume it's a framer
        else:
            if not isinstance(value, framers.Framer):
                raise ValueError("framer must be an instance of "
                                 "tendril.Framer")

            self._send_framer = value
            self._recv_framer = value

    @framers.deleter
    def framers(self):
        """
        Reset the framers in use for the connection to be a
        tendril.IdentityFramer.  The framer states will be reset next
        time their respective framer is used.
        """

        f = self.default_framer()
        self._send_framer = f
        self._recv_framer = f

    @property
    def framer_states(self):
        """
        Retrieve the framer states in use for the connection.
        """

        return TendrilFramerStates(self._send_framer_state,
                                   self._recv_framer_state)

    @property
    def application(self):
        """Retrieve the current application."""

        return self._application

    @application.setter
    def application(self, value):
        """Update the application."""

        # Always allow None
        if value is None:
            self._application = None
            return

        # Check that the state is valid
        if not isinstance(value, application.Application):
            raise ValueError("application must be an instance of "
                             "tendril.Application")

        self._application = value

    @application.deleter
    def application(self):
        """Clear the application state."""

        self._application = None

    @abc.abstractmethod
    def send_frame(self, frame):
        """Send a frame on the connection."""

        pass

    @abc.abstractmethod
    def close(self):
        """
        Close the connection.  Must not call the ``closed()`` method;
        that will be taken care of at a higher layer.
        """

        # Make sure we're untracked
        self.manager._untrack_tendril(self)

    @abc.abstractproperty
    def proto(self):
        """Retrieve the name of the underlying network protocol."""

        pass
