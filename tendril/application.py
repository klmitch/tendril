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


class ApplicationState(object):
    """
    Base class for tracking application state.  Application state
    classes are responsible for implementing the base methods
    documented here.
    """

    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def close(self, tend):
        """
        Called to notify the application that the connection has been
        closed.  The Tendril object may be consulted for any error
        conditions that may have resulted in the closure.
        """

        pass

    @abc.abstractmethod
    def recv_frame(self, tend, frame):
        """
        Called to pass received frames to the application.
        """

        pass
