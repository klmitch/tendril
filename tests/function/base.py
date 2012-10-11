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

import time
import unittest

import gevent
import mock

import tendril
from tendril import manager

from tests.function import client
from tests.function import server


class EchoApplicationClient(tendril.Application):
    def __init__(self, parent):
        super(EchoApplicationClient, self).__init__(parent)

        self.received_frames = []

    def recv_frame(self, frame):
        self.received_frames.append(frame)


def start_client(proto, server):
    manager = tendril.get_manager(proto)
    manager.start()

    tend = manager.connect(server, EchoApplicationClient)

    return manager, tend.application


class EchoApplicationServer(tendril.Application):
    def recv_frame(self, frame):
        self.send_frame(frame)


def start_server(proto):
    manager = tendril.get_manager(proto, ('127.0.0.1', 0))
    manager.start(EchoApplicationServer)
    return manager


class TestBasicFunction(unittest.TestCase):
    def setUp(self):
        self.p_managers = mock.patch.object(manager.TendrilManager,
                                            '_managers', {})
        self.p_tendrils = mock.patch.object(manager.TendrilManager,
                                            '_tendrils', {})
        self.p_running_managers = mock.patch.object(manager.TendrilManager,
                                                    '_running_managers', {})

        self.p_managers.start()
        self.p_tendrils.start()
        self.p_running_managers.start()

        self.serv = start_server(self.proto)
        self.cli, self.app = start_client(self.proto, self.serv.local_addr)

    def tearDown(self):
        self.serv.shutdown()
        self.cli.shutdown()

        self.p_running_managers.stop()
        self.p_tendrils.stop()
        self.p_managers.stop()

    def test_proto(self):
        # Send some messages
        self.app.send_frame('frame1')
        self.app.send_frame('frame2')
        self.app.send_frame('frame3')

        # Sleep to give the server a chance to handle them
        end = time.time() + 10
        while time.time() < end and len(self.app.received_frames) < 3:
            gevent.sleep(1)

        # Verify that the client got the messages back
        self.assertEqual(self.app.received_frames,
                         ['frame1', 'frame2', 'frame3'])
