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
from gevent import socket
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

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'recvfrom.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_creator(self, mock_UDPTendril, mock_track_tendril,
                              mock_socket):
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'recvfrom.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    @mock.patch.object(udp.UDPTendrilManager, 'recv_bufsize', 8192)
    def test_listener_creator_recv_bufsize(self, mock_UDPTendril,
                                           mock_track_tendril, mock_socket):
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.recvfrom(8192),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'recvfrom.side_effect': gevent.GreenletExit(),
        'getsockname.return_value': ('127.0.0.1', 8080),
        'close.side_effect': socket.error(),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_killed(self, mock_UDPTendril, mock_track_tendril,
                             mock_socket):
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True

        with self.assertRaises(gevent.GreenletExit):
            manager.listener(acceptor, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'recvfrom.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_wrapper(self, mock_UDPTendril, mock_track_tendril,
                              mock_socket):
        wrapped_sock = mock.Mock(**{
            'recvfrom.side_effect': TestException(),
        })
        wrapper = mock.Mock(return_value=wrapped_sock)
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, wrapper)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
        ])
        wrapper.assert_called_once_with(mock_socket.return_value)
        wrapped_sock.assert_has_calls([
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_noacceptor(self, mock_UDPTendril, mock_track_tendril,
                                 mock_socket):
        msgs = ['msg1', 'msg2', 'msg3']
        mock_socket.return_value.recvfrom.side_effect = [
            (msgs[0], ('127.0.0.2', 8082)),
            (msgs[1], ('127.0.0.3', 8083)),
            (msgs[2], ('127.0.0.4', 8084)),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
        ]
        tend = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True
        manager.tendrils[(('127.0.0.1', 8080), ('127.0.0.3', 8083))] = tend

        with self.assertRaises(TestException):
            manager.listener(None, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(mock_track_tendril.called)
        tend._recv_frameify.assert_called_once_with('msg2')

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_recv_frameify_error(self, mock_UDPTendril,
                                          mock_track_tendril, mock_socket):
        mock_socket.return_value.recvfrom.side_effect = [
            ('frame', ('127.0.0.3', 8083)),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
        ]
        tend = mock.Mock(**{'_recv_frameify.side_effect': TestException()})
        manager = udp.UDPTendrilManager()
        manager.running = True
        manager.tendrils[(('127.0.0.1', 8080), ('127.0.0.3', 8083))] = tend

        with self.assertRaises(TestException):
            manager.listener(None, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_UDPTendril.called)
        self.assertFalse(mock_track_tendril.called)
        tend._recv_frameify.assert_called_once_with('frame')
        tend.close.assert_called_once_with()
        self.assertEqual(tend.closed.call_count, 1)

        args = tend.closed.call_args[0]
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], TestException)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_acceptor(self, mock_UDPTendril, mock_track_tendril,
                               mock_socket):
        msgs = ['msg1', 'msg2', 'msg3']
        mock_socket.return_value.recvfrom.side_effect = [
            (msgs[0], ('127.0.0.2', 8082)),
            (msgs[1], ('127.0.0.3', 8083)),
            (msgs[2], ('127.0.0.4', 8084)),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
        ]
        tendrils = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_UDPTendril.side_effect = [tendrils[0], tendrils[2]]
        acceptor = mock.Mock()
        manager = udp.UDPTendrilManager()
        manager.running = True
        manager.tendrils[(('127.0.0.1', 8080),
                          ('127.0.0.3', 8083))] = tendrils[1]

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_UDPTendril.assert_has_calls([
            mock.call(manager, ('127.0.0.1', 8080), ('127.0.0.2', 8082)),
            mock.call(manager, ('127.0.0.1', 8080), ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[2]),
        ])
        mock_track_tendril.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[2]),
        ])
        tendrils[0]._recv_frameify.assert_called_once_with('msg1')
        tendrils[1]._recv_frameify.assert_called_once_with('msg2')
        tendrils[2]._recv_frameify.assert_called_once_with('msg3')

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(udp, 'UDPTendril', return_value=mock.Mock())
    def test_listener_rejector(self, mock_UDPTendril, mock_track_tendril,
                               mock_socket):
        mock_socket.return_value.recvfrom.side_effect = [
            ('msg1', ('127.0.0.2', 8082)),
            ('msg2', ('127.0.0.3', 8083)),
            ('msg3', ('127.0.0.4', 8084)),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
        ]
        tendrils = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_UDPTendril.side_effect = tendrils[:]
        acceptor = mock.Mock(side_effect=application.RejectConnection())
        manager = udp.UDPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_DGRAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.recvfrom(4096),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_UDPTendril.assert_has_calls([
            mock.call(manager, ('127.0.0.1', 8080), ('127.0.0.2', 8082)),
            mock.call(manager, ('127.0.0.1', 8080), ('127.0.0.3', 8083)),
            mock.call(manager, ('127.0.0.1', 8080), ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[1]),
            mock.call(tendrils[2]),
        ])
        self.assertFalse(mock_track_tendril.called)
        self.assertFalse(tendrils[0]._recv_frameify.called)
        self.assertFalse(tendrils[1]._recv_frameify.called)
        self.assertFalse(tendrils[2]._recv_frameify.called)

    def test_sock_getter_notrunning(self):
        manager = udp.UDPTendrilManager()
        manager._sock = 'socket'
        manager._sock_event = mock.Mock()

        result = manager.sock

        self.assertEqual(result, None)
        self.assertFalse(manager._sock_event.wait.called)

    def test_sock_getter(self):
        manager = udp.UDPTendrilManager()
        manager.running = True
        manager._sock = 'socket'
        manager._sock_event = mock.Mock()

        result = manager.sock

        self.assertEqual(result, 'socket')
        manager._sock_event.wait.assert_called_once_with()
