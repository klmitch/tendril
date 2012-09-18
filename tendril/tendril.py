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

from tendril import framers


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

    ``state``

      The application-provided state.  May be set by the application.
      Should be a subclass of ``tendril.ApplicationState``.

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
        self.endpoint = manager.endpoint
        self.local_addr = local_addr
        self.remote_addr = remote_addr

        self._state = None

        # Set the initial framer
        f = self.default_framer()
        self._send_framer = f
        self._recv_framer = f

        # Set up state for the framer
        self._send_framer_state = framers.FramerState()
        self._recv_framer_state = framers.FramerState()

    def wrap(self, wrapper, *args, **kwargs):
        """
        Allows the underlying socket to be wrapped, as by an SSL
        connection.  Not implemented by all Tendril subclasses.

        :param wrapper: A callable taking, as its first argument, a
                        socket.socket object.  All other positional
                        and keyword arguments will be passed to this
                        wrapping callable.  The callable must return a
                        valid proxy for the socket.socket object,
                        which will subsequently be used to communicate
                        on the connection.
        """

        raise NotImplementedError("Cannot wrap this connection")

    def close(self):
        """Close the connection."""

        # Close the connection, but do not call the closed() method.
        self._close()

    def closed(self, error=None):
        """
        Notify the application that the connection has been closed.

        :param error: The exception which has caused the connection to
                      be closed.  If the connection has been closed
                      due to an EOF, pass ``None``.
        """

        if self._state:
            self._state.closed(error)

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
        elif isinstance(value, collections.Sequence):
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
    def state(self):
        """Retrieve the current application state."""

        return self._state

    @state.setter
    def state(self, value):
        """Set the value of the application state."""

        # Always allow None
        if value is None:
            self._state = None

        # Check that the state is valid
        if not isinstance(value, application.ApplicationState):
            raise ValueError("application state must be an instance of "
                             "tendril.ApplicationState")

        self._state = value

    @state.deleter
    def state(self):
        """Clear the application state."""

        self._state = None

    @abc.abstractmethod
    def send_frame(self, frame):
        """Send a frame on the connection."""

        pass

    @abc.abstractmethod
    def _close(self):
        """
        Close the connection.  Must not call the ``closed()`` method;
        that will be taken care of at a higher layer.
        """

        pass

    @abc.abstractproperty
    def proto(self):
        """Retrieve the name of the underlying network protocol."""

        pass
