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

import gevent
from gevent import event
import mock

from tendril import application
from tendril import connection
from tendril import manager
from tendril import udp


class TestException(Exception):
    pass


class TestUDPTendril(unittest.TestCase):
    @mock.patch.object(connection.Tendril, '_send_streamify',
                       return_value='frame')
    def test_send_frame(self, mock_send_streamify):
        sock = mock.Mock()
        tend = udp.UDPTendril(mock.Mock(sock=sock), 'local_addr',
                              'remote_addr')

        tend.send_frame('a frame')

        mock_send_streamify.assert_called_once_with('a frame')
        sock.sendto.assert_called_once_with('frame', 'remote_addr')

    @mock.patch.object(connection.Tendril, '_send_streamify',
                       return_value='frame')
    def test_send_frame_no_sock(self, mock_send_streamify):
        tend = udp.UDPTendril(mock.Mock(sock=None), 'local_addr',
                              'remote_addr')

        self.assertRaises(ValueError, tend.send_frame, 'a frame')

    @mock.patch.object(connection.Tendril, '_send_streamify',
                       return_value='frame')
    def test_send_frame_bad_sendto(self, mock_send_streamify):
        sock = mock.Mock(**{'sendto.side_effect': TestException()})
        tend = udp.UDPTendril(mock.Mock(sock=sock), 'local_addr',
                              'remote_addr')

        tend.send_frame('a frame')

        mock_send_streamify.assert_called_once_with('a frame')
        sock.sendto.assert_called_once_with('frame', 'remote_addr')

    @mock.patch.object(connection.Tendril, 'close')
    def test_close(self, mock_super_close):
        tend = udp.UDPTendril(mock.Mock(), 'local_addr', 'remote_addr')

        tend.close()

        mock_super_close.assert_called_once_with()


@mock.patch.dict(manager.TendrilManager._managers)
class TestUDPTendrilManager(unittest.TestCase):
    @mock.patch.object(manager.TendrilManager, '__init__')
    def test_init(self, mock_init):
        manager = udp.UDPTendrilManager()

        mock_init.assert_called_once_with(None)
        self.assertEqual(manager._sock, None)
        self.assertIsInstance(manager._sock_event, event.Event)
        self.assertEqual(manager._sock_event.is_set(), False)

    @mock.patch.object(manager.TendrilManager, 'start')
    def test_start(self, mock_start):
        manager = udp.UDPTendrilManager()
        manager._sock = 'sock'
        manager._sock_event = mock.Mock()

        manager.start('acceptor', 'wrapper')

        mock_start.assert_called_once_with('acceptor', 'wrapper')
        self.assertEqual(manager._sock, None)
        manager._sock_event.clear.assert_called_once_with()

    @mock.patch.object(manager.TendrilManager, 'stop')
    def test_stop(self, mock_stop):
        manager = udp.UDPTendrilManager()
        manager._sock = 'sock'
        manager._sock_event = mock.Mock()

        manager.stop('thread')

        mock_stop.assert_called_once_with('thread')
        self.assertEqual(manager._sock, None)
        manager._sock_event.clear.assert_called_once_with()

    @mock.patch.object(manager.TendrilManager, 'shutdown')
    def test_shutdown(self, mock_shutdown):
        manager = udp.UDPTendrilManager()
        manager._sock = 'sock'
        manager._sock_event = mock.Mock()

        manager.shutdown()

        mock_shutdown.assert_called_once_with()
        self.assertEqual(manager._sock, None)
        manager._sock_event.clear.assert_called_once_with()

    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    @mock.patch.object(udp.UDPTendrilManager, 'local_addr', ('0.0.0.0', 8880))
    def test_connect(self, mock_UDPTendril, mock_track_tendril, mock_connect):
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()

        tend = manager.connect(('127.0.0.1', 8080), acceptor)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_UDPTendril.assert_called_once_with(manager, ('0.0.0.0', 8880),
                                                ('127.0.0.1', 8080))
        acceptor.assert_called_once_with(mock_UDPTendril.return_value)
        mock_track_tendril.assert_called_once_with(
            mock_UDPTendril.return_value)
        self.assertEqual(id(tend), id(mock_UDPTendril.return_value))

    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    @mock.patch.object(udp.UDPTendrilManager, 'local_addr', ('0.0.0.0', 8880))
    def test_connect_rejected(self, mock_UDPTendril, mock_track_tendril,
                              mock_connect):
        acceptor = mock.Mock(side_effect=application.RejectConnection())
        manager = udp.UDPTendrilManager()

        tend = manager.connect(('127.0.0.1', 8080), acceptor)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_UDPTendril.assert_called_once_with(manager, ('0.0.0.0', 8880),
                                                ('127.0.0.1', 8080))
        acceptor.assert_called_once_with(mock_UDPTendril.return_value)
        self.assertFalse(mock_track_tendril.called)
        self.assertEqual(tend, None)
