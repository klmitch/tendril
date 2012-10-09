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

import collections

from gevent import socket

import netaddr


__all__ = ["TendrilPartial", "WrapperChain", "addr_info", "SocketCloser"]


class TendrilPartial(object):
    """
    Similar to ``functools.partial()``; however, the positional
    arguments are passed after the positional arguments to the
    callable invocation.  This is formulated to allow additional
    arguments to be passed to socket wrappers and to connection
    acceptors.
    """

    def __init__(self, func, *args, **kwargs):
        """
        Initialize a TendrilPartial.

        :param func: The function to be called.
        :param args: Extra positional arguments to be passed after the
                     positional arguments in the function call.
        :param kwargs: Extra keyword arguments to be passed in the
                       function call.
        """

        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self, *args):
        """
        Call the actual function.  The passed-in positional arguments
        will be followed by positional and keyword arguments
        identified when the ``TendrilPartial`` object was initialized.
        """

        positional = args + self.args
        return self.func(*positional, **self.kwargs)


class WrapperChain(object):
    """
    Allows multiple wrappers to be chained.  Each wrapper will be
    called in turn, in the order defined, to effect its respective
    changes on the socket.
    """

    def __init__(self, wrapper=None, *args, **kwargs):
        """
        Initialize the WrapperChain.  If a wrapper is given, it will
        be added to the chain as the first wrapper to be invoked.  Any
        extra positional or keyword arguments will be passed to that
        wrapper through construction of a ``TendrilPartial``.
        """

        self._wrappers = []

        # Use the chain method to add the wrapper for us
        if wrapper:
            self.chain(wrapper, *args, **kwargs)

    def __call__(self, sock):
        """
        Call the wrapper chain.  Each wrapper will be called in turn
        on the return result of the previous wrapper.  The result of
        the final wrapper will be returned as the wrapped socket.
        """

        for wrapper in self._wrappers:
            sock = wrapper(sock)

        return sock

    def chain(self, wrapper, *args, **kwargs):
        """
        Add a wrapper to the chain.  Any extra positional or keyword
        arguments will be passed to that wrapper through construction
        of a ``TendrilPartial``.  For convenience, returns the
        WrapperChain object, allowing ``chain()`` to be called on the
        return result to register multiple wrappers.
        """

        if args or kwargs:
            wrapper = TendrilPartial(wrapper, *args, **kwargs)

        self._wrappers.append(wrapper)

        # For convenience...
        return self


def addr_info(addr):
    """
    Interprets an address in standard tuple format to determine if it
    is valid, and, if so, which socket family it is.  Returns the
    socket family.
    """

    # If it's a string, it's in the UNIX family
    if isinstance(addr, basestring):
        return socket.AF_UNIX

    # Verify that addr is a tuple
    if not isinstance(addr, collections.Sequence):
        raise ValueError("address is not a tuple")

    # Make sure it has at least 2 fields
    if len(addr) < 2:
        raise ValueError("cannot understand address")

    # Sanity-check the port number
    if not (0 <= addr[1] < 65536):
        raise ValueError("cannot understand port number")

    # OK, first field should be an IP address; suck it out...
    ipaddr = addr[0]

    # Empty string means IPv4
    if not ipaddr:
        if len(addr) != 2:
            raise ValueError("cannot understand address")

        return socket.AF_INET

    # See if it's valid...
    if netaddr.valid_ipv6(ipaddr):
        if len(addr) > 4:
            raise ValueError("cannot understand address")

        return socket.AF_INET6
    elif netaddr.valid_ipv4(ipaddr):
        if len(addr) != 2:
            raise ValueError("cannot understand address")

        return socket.AF_INET

    raise ValueError("cannot understand address")


class SocketCloser(object):
    """
    Context manager that ensures a socket is closed.
    """

    def __init__(self, sock, err_thresh=0, ignore=None):
        """
        Initialize the SocketCloser.

        :param sock: The socket to be closed in the event of an error.
        :param err_thresh: The maximum number of errors to allow
                           before the socket is closed.  If not given
                           or given as 0, no error counting behavior
                           will be used.
        """

        self.sock = sock
        self.err_thresh = err_thresh
        self.errors = 0 if err_thresh > 0 else None
        self.ignore = frozenset(ignore) if ignore else frozenset()

    def __enter__(self):
        """Enter the context.  Returns the SocketCloser."""

        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        """
        Exit the context.  If an exception was raised, ensures that
        the socket is closed.  If the error threshold logic is enabled
        by passing a non-zero value for err_thresh to the initializer,
        socket will only be closed if the exception is not an
        Exception (i.e., a BaseException) or if the error threshold is
        exceeded.
        """

        if exc_type:
            # Skip ignored errors
            if exc_type in self.ignore:
                return True

            # An error occurred; handle threshold counting logic: if
            # we're doing error threshold and the error is not a
            # BaseException (like GreenletExit) and the count of
            # errors is less than the error threshold, we declare the
            # exception handled.
            if (self.errors is not None and
                    issubclass(exc_type, Exception) and
                    self.errors < self.err_thresh):
                # Increment the error count
                self.errors += 1

                return True

            # OK, a legitimate error occurred; ensure the socket gets
            # closed
            try:
                self.sock.close()
            except Exception:
                pass
        elif self.errors:
            # No error occurred, so decrement the error count
            self.errors -= 1
