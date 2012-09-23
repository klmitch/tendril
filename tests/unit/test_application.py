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

import unittest

import mock

from tendril import application


class ApplicationForTest(application.Application):
    def recv_frame(self, frame):
        pass


class TestApplication(unittest.TestCase):
    def test_init(self):
        app = ApplicationForTest('parent')

        self.assertEqual(app.parent, 'parent')

    def test_close(self):
        app = ApplicationForTest(mock.Mock())
        app.close()

        app.parent.close.assert_called_once_with()

    def test_send_frame(self):
        app = ApplicationForTest(mock.Mock())
        app.send_frame('frame')

        app.parent.send_frame.assert_called_once_with('frame')
