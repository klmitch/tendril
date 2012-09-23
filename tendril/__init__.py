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

"""
==============================================
Tendril Frame-based Network Connection Tracker
==============================================

Tendril is a network communication library based on two main features:
it is based on sending and receiving frames, and it tracks the state
of an abstract connection as defined by the application.  Tendril is
designed to be easy to use: creating an application requires
subclassing the ``Application`` class and providing an implementation
for the recv_frame() method; then get a ``TendrilManager`` class
instance and start it, and Tendril manages the rest.

Tendril Concepts
================

Frames
------

Tendril is based on the concept of passing around frames or packets of
data.  The fact is, most network protocols are based on sending and
receiving frames; for instance, in the SMTP protocol used for sending
email, the sender will start off sending the frame "MAIL FROM
email@example.com" followed by a line termination sequence (a carriage
return followed by a newline).  The SMTP server will then respond with
another frame acknowledging the "MAIL FROM" frame, and that frame will
also end with a line termination sequence.  Thus, even though SMTP is
defined on top of the TCP protocol, which provides an undivided stream
of data between the client and server, a framing boundary is imposed
upon it--in this case, the carriage return followed by a newline that
terminates each frame.

Tendril includes the concept of *framers*.  A framer is nothing more
than a subclass of ``Framer`` which has one method which extracts a
single frame from the stream of undifferentiated data, and another
method which converts a frame into an appropriate representation.  In
the case of the SMTP protocol exchange above, the ``frameify()``
method finds each line terminated by the carriage return-newline pair,
strips off those characters, and returns just the frame.  In the same
way, the corresponding ``streamify()`` method takes the frame and
appends a carriage return-newline pair.

For text-based protocols such as SMTP, this may seem like overkill.
However, for binary-based protocols, a lot of code is dedicated to
determining the boundaries between frames, and in some cases even
decoding the frame.  Tendril's concept of a framer for a connection
enables the framing logic to be isolated from the rest of the
application, and even reused: Tendril comes with several pre-built
framers, including framers designed to work with a text-based protocol
such as SMTP.

Another important advantage of the framer concept is the ability to
switch between framers as needed.  Taking again the example of the
SMTP protocol--the actual email data is transferred to the server by
the client first sending a "DATA" frame; the server responds
indicating that it is ready to begin receiving the message data, and
then the client simply sends the message data, ending it with a line
containing only a single period (".").  In this case, an SMTP server
application based on Tendril may wish to receive the message data as a
single frame; it can do this by creating a framer which buffers stream
data until it sees that ending sentinel (the period on a line by
itself), then returns the whole message as a single frame.  Once the
server receives the "DATA" frame from the client, all it has to do is
temporarily switch out the framer in use for the receiving side of the
connection, then switch it back to the standard line-based framer once
it has received the message frame.

Tendril allows for different framers to be used on the receiving side
and sending side of the connection.  This could be used in a case like
the SMTP server example cited above, where the server still wishes to
send line-oriented frames to the client, even while buffering a
message data frame.  In addition, although the provided framers deal
with byte data, Tendril itself treats the frames as opaque;
applications can use this to build a framer that additionally parses a
given frame into a class object that the rest of the application then
processes as necessary.

Connection Tracking
-------------------

Tendril is also based on the concept of tracking connection state.
For connection-oriented protocols such as TCP, obviously, this is not
a big problem; however, Tendril is also designed to support
connectionless protocols such as UDP, where some applications need to
manage state information relevant to a given exchange.  As an
admittedly contrived example, consider DNS, which is based on UDP.  A
client of the DNS system will send a request to a DNS server over UDP;
when a response is received from that DNS server, the connection state
information tracked by Tendril can help connect that response with the
appropriate request, ensuring that the response goes to the right
place.

This connection state tracking is primarily intended to assist
applications which desire to be available over both
connection-oriented protocols such as TCP and over connectionless
protocols such as UDP.  Although Tendril does not address reliability
or frame ordering, its connection state tracking eases the
implementation of an application which utilizes both types of
protocols.

Extensibility
-------------

Careful readers may have noticed the use of the terms, "such as TCP"
and "such as UDP."  Although Tendril only has built-in support for TCP
and UDP connections, it is possible to extend Tendril to support other
protocols.  All that is required is to create subclasses of
``Tendril`` (representing an individual connection) and of
``TendrilManager`` (which accepts and creates connections and manages
any necessary socket data flows), and to register the
``TendrilManager`` subclasses as ``pkg_resources`` entry points under
the ``tendril.manager`` namespace.  See the ``setup.py`` for Tendril
for an example of how this may be done.

In addition to allowing Tendril to support protocols other than TCP
and UDP, it is also possible to implement new framers by subclassing
the ``Framer`` class.  (Note: as Tendril deals with ``Framer``
objects, it is not necessary to register these framers using
``pkg_resources`` entry points.)  Objects of these classes may then
simply be assigned to the appropriate ``framers`` attribute on the
``Tendril`` instance representing the connection.

Advanced Interfaces
-------------------

Tendril also provides an advanced interface that allows a given raw
socket to be "wrapped."  Using this feature, an ordinary TCP socket
could be converted into an SSL socket.  Other uses for this interface
are possible, such as setting socket options for the socket.  Tendril
also provides an interface to allow multiple of these wrapper
functions to be called in a given order.

Standard Usage
==============

The first step in using Tendril is to define an application by
subclassing the ``Application`` class.  (Subclassing is not strictly
necessary--Tendril uses Python's standard ``abc`` package for defining
abstract base classes--but using subclassing will pull in a few
helpful and/or required methods.)  The subclass need merely implement
the recv_frame() method, which will be called when a frame is
received.  The ``Application`` subclass constructor itself can be the
*acceptor* to be used by Tendril (more on acceptors in a moment).

Once the ``Application`` subclass has been created, the developer then
needs to get a ``TendrilManager`` instance, using the
``get_manager()`` factory function.  The exact call to
``get_manager()`` depends on the needs; for making outgoing
connections, simply calling ``get_manager("tcp")`` is sufficient.  If
listening on a port or making an outgoing connection from a specific
address and/or port is desired, the second argument to
``get_manager()`` may be a tuple of the desired local IP address and
the port number (i.e., ``("127.0.0.1", 80)``).

All managers must be started, and ``get_manager()`` does not start the
manager by itself.  Check the manager's ``running`` attribute to see
if the manager is already running, and if it is not, call its
``start()`` method.  To accept connections, pass ``start()`` the
*acceptor* (usually the ``Application`` subclass).  The ``start()``
method also accepts a *wrapper*, which will be called with the
listening socket when it is created.

If, instead of accepting connections (as a server would do), the
desire is to make outgoing connections, simply call ``start()`` with
no arguments, then call the ``connect()`` method of the manager.  This
method takes the *target* of the connection (i.e., the IP address and
port number, as a tuple) and the *acceptor*.  (It also has an optional
*wrapper*, which will be called with the outgoing socket just prior to
initiating the connection.)

Acceptors
---------

An *acceptor* is simply a callable taking a single argument--the
``Tendril`` instance representing the connection--and returning an
instance of a subclass of ``Application``, which will be assigned to
the ``application`` attribute of the ``Tendril`` instance.  The
acceptor initializes the application; it also has the opportunity to
manipulate that ``Tendril``, such as setting framers, calling the
``Tendril`` instance's ``wrap()`` method, or simply closing the
connection.

Although the ``TendrilManager`` does not provide the opportunity to
pass arguments to the acceptor, it is certainly possible to do so.
The standard Python ``functools.partial()`` is one obvious interface,
but Tendril additionally provides its own ``TendrilPartial`` utility;
the advantage of ``TendrilPartial`` is that the positional argument
passed to the acceptor--the ``Tendril`` instance--will be the first
positional argument, rather than the last one, as would be the case
with ``functools.partial()``.

Wrappers
--------

A *wrapper* is simply a callable again taking a single argument--in
this case, the socket object--and returning a wrapped version of that
argument; that wrapped version of the socket will then be used in
subsequent network calls.  A wrapper which manipulates socket options
can simply return the socket object which was passed in, while one
which performs SSL encapsulation can return the SSL wrapper.  Again,
although there is no opportunity to pass arguments to the wrapper in a
manager ``start()`` or ``connect()`` call (or a ``Tendril`` object's
``wrap()`` call), ``functools.partial()`` or Tendril's
``TendrilPartial`` utility can be used.  In particular, in conjunction
with ``TendrilPartial``, the ``ssl.wrap_socket()`` call can be used as
a socket wrapper directly, enabling an SSL connection to be set up
easily.

Of course, it may be necessary to perform multiple "wrapping"
activities on a connection, such as setting socket options followed by
wrapping the socket in an SSL connection.  For this case, Tendril
provides the ``WrapperChain``; it can be initialized in the same way
that ``TendrilPartial`` is, but additional wrappers can be added by
calling the ``chain()`` method; when called, the ``WrapperChain``
object will call each wrapper in the order defined, returning the
final wrapped socket in the end.
"""

from application import *
from connection import *
from framers import *
from manager import *
from utils import *


__all__ = (application.__all__ + connection.__all__ + framers.__all__ +
           manager.__all__ + utils.__all__)
