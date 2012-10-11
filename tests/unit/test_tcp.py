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
from gevent import coros
from gevent import event
from gevent import socket
import mock

from tendril import application
from tendril import connection
from tendril import framers
from tendril import manager
from tendril import tcp


class TestException(Exception):
    pass


class TestTCPTendril(unittest.TestCase):
    def setUp(self):
        self.sock = mock.Mock(**{
            'getsockname.return_value': ('127.0.0.1', 8080),
            'getpeername.return_value': ('127.0.0.2', 8880),
        })

    def test_init_withremote(self):
        tend = tcp.TCPTendril('manager', self.sock, ('127.0.0.2', 8880))

        self.assertEqual(tend.local_addr, ('127.0.0.1', 8080))
        self.assertEqual(tend.remote_addr, ('127.0.0.2', 8880))
        self.assertIsInstance(tend._recv_framer, framers.LineFramer)
        self.assertIsInstance(tend._send_framer, framers.LineFramer)
        self.assertEqual(id(tend._sock), id(self.sock))
        self.assertIsInstance(tend._sendbuf_event, event.Event)
        self.assertEqual(tend._sendbuf, '')
        self.assertEqual(tend._recv_thread, None)
        self.assertEqual(tend._send_thread, None)
        self.assertEqual(tend._recv_lock, None)
        self.assertEqual(tend._send_lock, None)
        self.sock.getsockname.assert_called_once_with()
        self.assertFalse(self.sock.getpeername.called)

    def test_init_noremote(self):
        tend = tcp.TCPTendril('manager', self.sock)

        self.assertEqual(tend.local_addr, ('127.0.0.1', 8080))
        self.assertEqual(tend.remote_addr, ('127.0.0.2', 8880))
        self.assertIsInstance(tend._recv_framer, framers.LineFramer)
        self.assertIsInstance(tend._send_framer, framers.LineFramer)
        self.assertEqual(id(tend._sock), id(self.sock))
        self.assertIsInstance(tend._sendbuf_event, event.Event)
        self.assertEqual(tend._sendbuf, '')
        self.assertEqual(tend._recv_thread, None)
        self.assertEqual(tend._send_thread, None)
        self.assertEqual(tend._recv_lock, None)
        self.assertEqual(tend._send_lock, None)
        self.sock.getsockname.assert_called_once_with()
        self.sock.getpeername.assert_called_once_with()

    @mock.patch.object(gevent, 'spawn')
    def test_start(self, mock_spawn):
        recv_thread = mock.Mock()
        send_thread = mock.Mock()
        mock_spawn.side_effect = [recv_thread, send_thread]

        tend = tcp.TCPTendril('manager', self.sock)
        tend._start()

        self.assertIsInstance(tend._recv_lock, coros.Semaphore)
        self.assertIsInstance(tend._send_lock, coros.Semaphore)
        mock_spawn.assert_has_calls([mock.call(tend._recv),
                                     mock.call(tend._send)])
        self.assertEqual(id(tend._recv_thread), id(recv_thread))
        self.assertEqual(id(tend._send_thread), id(send_thread))
        recv_thread.link.assert_called_once_with(tend._thread_error)
        send_thread.link.assert_called_once_with(tend._thread_error)

    @mock.patch.object(connection.Tendril, 'close')
    @mock.patch.object(tcp.TCPTendril, '_recv_frameify')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    @mock.patch.object(gevent, 'sleep')
    def test_recv(self, mock_sleep, mock_closed, mock_recv_frameify,
                  mock_close):
        self.sock.recv.side_effect = ['frame 1', 'frame 2', '']
        tend = tcp.TCPTendril('manager', self.sock)
        tend._recv_lock = mock.Mock()
        send_thread = mock.Mock()
        tend._send_thread = send_thread

        with self.assertRaises(gevent.GreenletExit):
            tend._recv()

        self.assertEqual(tend._recv_lock.method_calls, [
            mock.call.release(), mock.call.acquire(),
            mock.call.release(), mock.call.acquire(),
            mock.call.release(), mock.call.acquire(),
        ])
        mock_sleep.assert_has_calls([mock.call(), mock.call(), mock.call()])
        self.sock.recv.assert_has_calls([mock.call(4096), mock.call(4096),
                                         mock.call(4096)])
        send_thread.kill.assert_called_once_with()
        self.assertEqual(tend._send_thread, None)
        self.sock.close.assert_called_once_with()
        self.assertEqual(tend._sock, None)
        mock_close.assert_called_once_with()
        mock_closed.assert_called_once_with()
        mock_recv_frameify.assert_has_calls([mock.call('frame 1'),
                                             mock.call('frame 2')])

    @mock.patch.object(connection.Tendril, 'close')
    @mock.patch.object(tcp.TCPTendril, '_recv_frameify')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    @mock.patch.object(gevent, 'sleep')
    def test_recv_altbufsize(self, mock_sleep, mock_closed, mock_recv_frameify,
                             mock_close):
        self.sock.recv.side_effect = ['frame 1', 'frame 2', '']
        tend = tcp.TCPTendril('manager', self.sock)
        tend.recv_bufsize = 1024
        tend._recv_lock = mock.Mock()
        send_thread = mock.Mock()
        tend._send_thread = send_thread

        with self.assertRaises(gevent.GreenletExit):
            tend._recv()

        self.assertEqual(tend._recv_lock.method_calls, [
            mock.call.release(), mock.call.acquire(),
            mock.call.release(), mock.call.acquire(),
            mock.call.release(), mock.call.acquire(),
        ])
        mock_sleep.assert_has_calls([mock.call(), mock.call(), mock.call()])
        self.sock.recv.assert_has_calls([mock.call(1024), mock.call(1024),
                                         mock.call(1024)])
        send_thread.kill.assert_called_once_with()
        self.assertEqual(tend._send_thread, None)
        self.sock.close.assert_called_once_with()
        self.assertEqual(tend._sock, None)
        mock_close.assert_called_once_with()
        mock_closed.assert_called_once_with()
        mock_recv_frameify.assert_has_calls([mock.call('frame 1'),
                                             mock.call('frame 2')])

    def test_send(self):
        self.sock.send.side_effect = [7, 7]
        tend = tcp.TCPTendril('manager', self.sock)
        self.sock.reset_mock()
        tend._sendbuf = 'frame 1frame 2'
        tend._send_lock = mock.Mock()
        tend._sendbuf_event = mock.Mock(**{
            'clear.side_effect': gevent.GreenletExit,
        })

        with self.assertRaises(gevent.GreenletExit):
            tend._send()

        self.assertEqual(tend._send_lock.method_calls, [
            mock.call.release(), mock.call.acquire(),
        ])
        self.assertEqual(tend._sendbuf_event.method_calls, [
            mock.call.wait(), mock.call.clear(),
        ])
        self.assertEqual(tend._sendbuf, '')
        self.sock.send.assert_has_calls([mock.call('frame 1frame 2'),
                                         mock.call('frame 2')])

    @mock.patch.object(tcp.TCPTendril, 'close')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    def test_thread_error_successful(self, mock_closed, mock_close):
        thread = mock.Mock(**{'successful.return_value': True})
        tend = tcp.TCPTendril('manager', self.sock)
        tend._send_thread = mock.Mock()
        tend._recv_thread = mock.Mock()

        tend._thread_error(thread)

        mock_close.assert_called_once_with()
        self.assertEqual(mock_closed.call_count, 1)

        args = mock_closed.call_args[0]
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], socket.error)
        self.assertEqual(args[0][0], 'thread exited prematurely')

        # Ensure we didn't overwrite the threads
        self.assertNotEqual(tend._send_thread, None)
        self.assertNotEqual(tend._recv_thread, None)

    @mock.patch.object(tcp.TCPTendril, 'close')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    def test_thread_error_greenletexit(self, mock_closed, mock_close):
        thread = mock.Mock(**{
            'successful.return_value': False,
            'exception': gevent.GreenletExit(),
        })
        tend = tcp.TCPTendril('manager', self.sock)
        tend._send_thread = mock.Mock()
        tend._recv_thread = mock.Mock()

        tend._thread_error(thread)

        mock_close.assert_called_once_with()
        self.assertFalse(mock_closed.called)

        # Ensure we didn't overwrite the threads
        self.assertNotEqual(tend._send_thread, None)
        self.assertNotEqual(tend._recv_thread, None)

    @mock.patch.object(tcp.TCPTendril, 'close')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    def test_thread_error_exception(self, mock_closed, mock_close):
        thread = mock.Mock(**{
            'successful.return_value': False,
            'exception': TestException(),
        })
        tend = tcp.TCPTendril('manager', self.sock)
        tend._send_thread = mock.Mock()
        tend._recv_thread = mock.Mock()

        tend._thread_error(thread)

        mock_close.assert_called_once_with()
        self.assertEqual(mock_closed.call_count, 1)

        args = mock_closed.call_args[0]
        self.assertEqual(len(args), 1)
        self.assertEqual(id(args[0]), id(thread.exception))

        # Ensure we didn't overwrite the threads
        self.assertNotEqual(tend._send_thread, None)
        self.assertNotEqual(tend._recv_thread, None)

    @mock.patch.object(tcp.TCPTendril, 'close')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    def test_thread_error_sendthread(self, _mock_closed, _mock_close):
        thread = mock.Mock(**{'successful.return_value': True})
        tend = tcp.TCPTendril('manager', self.sock)
        tend._send_thread = thread
        tend._recv_thread = mock.Mock()

        tend._thread_error(thread)

        self.assertEqual(tend._send_thread, None)
        self.assertNotEqual(tend._recv_thread, None)

    @mock.patch.object(tcp.TCPTendril, 'close')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    def test_thread_error_recvthread(self, _mock_closed, _mock_close):
        thread = mock.Mock(**{'successful.return_value': True})
        tend = tcp.TCPTendril('manager', self.sock)
        tend._send_thread = mock.Mock()
        tend._recv_thread = thread

        tend._thread_error(thread)

        self.assertNotEqual(tend._send_thread, None)
        self.assertEqual(tend._recv_thread, None)

    def test_wrap_nolock(self):
        wrapper = mock.Mock()
        tend = tcp.TCPTendril('manager', self.sock)
        tend._recv_lock = mock.Mock()
        tend._send_lock = mock.Mock()

        tend.wrap(wrapper)

        self.assertNotEqual(id(tend._sock), id(self.sock))
        wrapper.assert_called_once_with(self.sock)
        self.assertEqual(tend._recv_lock.mock_calls, [])
        self.assertEqual(tend._send_lock.mock_calls, [])

    def test_wrap_withlock(self):
        wrapper = mock.Mock()
        tend = tcp.TCPTendril('manager', self.sock)
        tend._recv_thread = mock.Mock()
        tend._send_thread = mock.Mock()
        tend._recv_lock = mock.Mock()
        tend._send_lock = mock.Mock()

        tend.wrap(wrapper)

        self.assertNotEqual(id(tend._sock), id(self.sock))
        wrapper.assert_called_once_with(self.sock)
        tend._recv_lock.assert_has_calls(
            [mock.call.acquire(), mock.call.release()])
        tend._send_lock.assert_has_calls(
            [mock.call.acquire(), mock.call.release()])

    def test_sock(self):
        tend = tcp.TCPTendril('manager', self.sock)

        self.assertEqual(id(tend.sock), id(self.sock))

    @mock.patch.object(connection.Tendril, '_send_streamify',
                       return_value='frame1:frame2')
    def test_send_frame(self, mock_send_streamify):
        tend = tcp.TCPTendril('manager', self.sock)
        tend._sendbuf_event = mock.Mock()

        tend.send_frame('a frame')

        mock_send_streamify.assert_called_once_with('a frame')
        tend._sendbuf_event.assert_has_calls([mock.call.set()])

    @mock.patch.object(connection.Tendril, 'close')
    def test_close_nothreads_nosock(self, mock_close):
        tend = tcp.TCPTendril('manager', self.sock)
        tend._sock = None

        tend.close()

        mock_close.assert_called_once_with()

    @mock.patch.object(connection.Tendril, 'close')
    def test_close_nothreads(self, mock_close):
        tend = tcp.TCPTendril('manager', self.sock)

        tend.close()

        mock_close.assert_called_once_with()
        self.assertEqual(tend._sock, None)
        self.sock.close.assert_called_once_with()

    @mock.patch.object(connection.Tendril, 'close')
    def test_close_threads(self, mock_close):
        tend = tcp.TCPTendril('manager', self.sock)
        recv_thread = mock.Mock()
        tend._recv_thread = recv_thread
        send_thread = mock.Mock()
        tend._send_thread = send_thread

        tend.close()

        mock_close.assert_called_once_with()
        self.assertEqual(tend._sock, None)
        self.assertEqual(tend._recv_thread, None)
        self.assertEqual(tend._send_thread, None)
        self.sock.close.assert_called_once_with()
        recv_thread.kill.assert_called_once_with()
        send_thread.kill.assert_called_once_with()


@mock.patch.dict(manager.TendrilManager._managers)
class TestTCPTendrilManager(unittest.TestCase):
    @mock.patch.object(socket, 'socket', return_value=mock.Mock())
    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_connect_basic(self, mock_TCPTendril, mock_track_tendril,
                           mock_connect, mock_socket):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()

        tend = manager.connect(('127.0.0.1', 8080), acceptor)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.connect(('127.0.0.1', 8080)),
        ])
        mock_TCPTendril.assert_called_once_with(manager,
                                                mock_socket.return_value)
        acceptor.assert_called_once_with(mock_TCPTendril.return_value)
        mock_track_tendril.assert_called_once_with(
            mock_TCPTendril.return_value)
        mock_TCPTendril.return_value._start.assert_called_once_with()
        self.assertEqual(id(tend), id(mock_TCPTendril.return_value))

    @mock.patch.object(socket, 'socket', return_value=mock.Mock())
    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_connect_wrapper(self, mock_TCPTendril, mock_track_tendril,
                             mock_connect, mock_socket):
        wrapped_sock = mock.Mock()
        wrapper = mock.Mock(return_value=wrapped_sock)
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager(('127.0.0.2', 8880))

        tend = manager.connect(('127.0.0.1', 8080), acceptor, wrapper)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             wrapper)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('127.0.0.2', 8880)),
            mock.call.connect(('127.0.0.1', 8080)),
        ])
        wrapper.assert_called_once_with(mock_socket.return_value)
        mock_TCPTendril.assert_called_once_with(manager, wrapped_sock)
        acceptor.assert_called_once_with(mock_TCPTendril.return_value)
        mock_track_tendril.assert_called_once_with(
            mock_TCPTendril.return_value)
        mock_TCPTendril.return_value._start.assert_called_once_with()
        self.assertEqual(id(tend), id(mock_TCPTendril.return_value))

    @mock.patch.object(socket, 'socket', return_value=mock.Mock())
    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_connect_failure(self, mock_TCPTendril, mock_track_tendril,
                             mock_connect, mock_socket):
        acceptor = mock.Mock(side_effect=TestException())
        manager = tcp.TCPTendrilManager()

        with self.assertRaises(TestException):
            tend = manager.connect(('127.0.0.1', 8080), acceptor)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.connect(('127.0.0.1', 8080)),
            mock.call.close(),
        ])
        mock_TCPTendril.assert_called_once_with(manager,
                                                mock_socket.return_value)
        acceptor.assert_called_once_with(mock_TCPTendril.return_value)
        self.assertFalse(mock_track_tendril.called)
        self.assertFalse(mock_TCPTendril.return_value._start.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'close.side_effect': socket.error(),
    }))
    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_connect_failure_closeerror(self, mock_TCPTendril,
                                        mock_track_tendril, mock_connect,
                                        mock_socket):
        acceptor = mock.Mock(side_effect=TestException())
        manager = tcp.TCPTendrilManager()

        with self.assertRaises(TestException):
            tend = manager.connect(('127.0.0.1', 8080), acceptor)

        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.connect(('127.0.0.1', 8080)),
            mock.call.close(),
        ])
        mock_TCPTendril.assert_called_once_with(manager,
                                                mock_socket.return_value)
        acceptor.assert_called_once_with(mock_TCPTendril.return_value)
        self.assertFalse(mock_track_tendril.called)
        self.assertFalse(mock_TCPTendril.return_value._start.called)

    @mock.patch.object(socket, 'socket', return_value=mock.Mock())
    @mock.patch.object(manager.TendrilManager, 'connect')
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_connect_reject_connection(self, mock_TCPTendril,
                                       mock_track_tendril, mock_connect,
                                       mock_socket):
        acceptor = mock.Mock(side_effect=application.RejectConnection)
        manager = tcp.TCPTendrilManager()

        tend = manager.connect(('127.0.0.1', 8080), acceptor)

        self.assertEqual(tend, None)
        mock_connect.assert_called_once_with(('127.0.0.1', 8080), acceptor,
                                             None)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.bind(('', 0)),
            mock.call.connect(('127.0.0.1', 8080)),
            mock.call.close(),
        ])
        mock_TCPTendril.assert_called_once_with(manager,
                                                mock_socket.return_value)
        acceptor.assert_called_once_with(mock_TCPTendril.return_value)
        self.assertFalse(mock_track_tendril.called)
        self.assertFalse(mock_TCPTendril.return_value._start.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock())
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_noacceptor(self, mock_TCPTendril, mock_track_tendril,
                                 mock_socket, mock_sleep):
        manager = tcp.TCPTendrilManager()

        with self.assertRaises(TestException):
            manager.listener(None, None)

        mock_sleep.assert_called_once_with(600)
        self.assertFalse(mock_socket.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_creator(self, mock_TCPTendril, mock_track_tendril,
                              mock_socket, mock_sleep):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    @mock.patch.object(tcp.TCPTendrilManager, 'backlog', 4096)
    def test_listener_creator_backlog(self, mock_TCPTendril,
                                      mock_track_tendril, mock_socket,
                                      mock_sleep):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(4096),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': gevent.GreenletExit(),
        'getsockname.return_value': ('127.0.0.1', 8080),
        'close.side_effect': socket.error(),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_killed(self, mock_TCPTendril, mock_track_tendril,
                             mock_socket, mock_sleep):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(gevent.GreenletExit):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_wrapper(self, mock_TCPTendril, mock_track_tendril,
                              mock_socket, mock_sleep):
        wrapped_sock = mock.Mock(**{
            'accept.side_effect': TestException(),
        })
        wrapper = mock.Mock(return_value=wrapped_sock)
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, wrapper)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
        ])
        wrapper.assert_called_once_with(mock_socket.return_value)
        wrapped_sock.assert_has_calls([
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
        'listen.side_effect': TestException(),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_nolisten(self, mock_TCPTendril, mock_track_tendril,
                               mock_socket, mock_sleep):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril')
    def test_listener_acceptor(self, mock_TCPTendril, mock_track_tendril,
                               mock_socket, mock_sleep):
        clis = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_socket.return_value.accept.side_effect = [
            (clis[0], ('127.0.0.2', 8082)),
            (clis[1], ('127.0.0.3', 8083)),
            (clis[2], ('127.0.0.4', 8084)),
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
        mock_TCPTendril.side_effect = tendrils[:]
        acceptor = mock.Mock(side_effect=[
            mock.Mock(),
            TestException(),
            mock.Mock(),
        ])
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_TCPTendril.assert_has_calls([
            mock.call(manager, clis[0], ('127.0.0.2', 8082)),
            mock.call(manager, clis[1], ('127.0.0.3', 8083)),
            mock.call(manager, clis[2], ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[1]),
            mock.call(tendrils[2]),
        ])
        self.assertFalse(clis[0].close.called)
        clis[1].close.assert_called_once_with()
        self.assertFalse(clis[2].close.called)
        mock_track_tendril.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[2]),
        ])
        tendrils[0]._start.assert_called_once_with()
        self.assertFalse(tendrils[1]._start.called)
        tendrils[2]._start.assert_called_once_with()

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril')
    def test_listener_acceptor_reject_connection(self, mock_TCPTendril,
                                                 mock_track_tendril,
                                                 mock_socket, mock_sleep):
        clis = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_socket.return_value.accept.side_effect = [
            (clis[0], ('127.0.0.2', 8082)),
            (clis[1], ('127.0.0.3', 8083)),
            (clis[2], ('127.0.0.4', 8084)),
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
        mock_TCPTendril.side_effect = tendrils[:]
        acceptor = mock.Mock(side_effect=application.RejectConnection())
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_TCPTendril.assert_has_calls([
            mock.call(manager, clis[0], ('127.0.0.2', 8082)),
            mock.call(manager, clis[1], ('127.0.0.3', 8083)),
            mock.call(manager, clis[2], ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[1]),
            mock.call(tendrils[2]),
        ])
        clis[0].close.assert_called_once_with()
        clis[1].close.assert_called_once_with()
        clis[2].close.assert_called_once_with()
        self.assertFalse(mock_track_tendril.called)
        self.assertFalse(tendrils[0]._start.called)
        self.assertFalse(tendrils[1]._start.called)
        self.assertFalse(tendrils[2]._start.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
        'close.side_effect': socket.error(),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril')
    def test_listener_acceptor_badclose(self, mock_TCPTendril,
                                        mock_track_tendril, mock_socket,
                                        mock_sleep):
        clis = [
            mock.Mock(**{
                'close.side_effect': socket.error(),
            }),
            mock.Mock(**{
                'close.side_effect': socket.error(),
            }),
            mock.Mock(**{
                'close.side_effect': socket.error(),
            })
        ]
        mock_socket.return_value.accept.side_effect = [
            (clis[0], ('127.0.0.2', 8082)),
            (clis[1], ('127.0.0.3', 8083)),
            (clis[2], ('127.0.0.4', 8084)),
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
        mock_TCPTendril.side_effect = tendrils[:]
        acceptor = mock.Mock(side_effect=[
            mock.Mock(),
            TestException(),
            mock.Mock(),
        ])
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_TCPTendril.assert_has_calls([
            mock.call(manager, clis[0], ('127.0.0.2', 8082)),
            mock.call(manager, clis[1], ('127.0.0.3', 8083)),
            mock.call(manager, clis[2], ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[1]),
            mock.call(tendrils[2]),
        ])
        self.assertFalse(clis[0].close.called)
        clis[1].close.assert_called_once_with()
        self.assertFalse(clis[2].close.called)
        mock_track_tendril.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[2]),
        ])
        tendrils[0]._start.assert_called_once_with()
        self.assertFalse(tendrils[1]._start.called)
        tendrils[2]._start.assert_called_once_with()

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'accept.side_effect': TestException(),
        'getsockname.return_value': ('127.0.0.1', 8080),
        'listen.side_effect': TestException(),
        'close.side_effect': socket.error(),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril', return_value=mock.Mock())
    def test_listener_nolisten_noclose(self, mock_TCPTendril,
                                       mock_track_tendril, mock_socket,
                                       mock_sleep):
        acceptor = mock.Mock()
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        self.assertFalse(mock_TCPTendril.called)
        self.assertFalse(acceptor.called)
        self.assertFalse(mock_track_tendril.called)

    @mock.patch.object(gevent, 'sleep', side_effect=TestException())
    @mock.patch.object(socket, 'socket', return_value=mock.Mock(**{
        'getsockname.return_value': ('127.0.0.1', 8080),
    }))
    @mock.patch.object(manager.TendrilManager, '_track_tendril')
    @mock.patch.object(tcp, 'TCPTendril')
    def test_listener_err_thresh(self, mock_TCPTendril, mock_track_tendril,
                                 mock_socket, mock_sleep):
        clis = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_socket.return_value.accept.side_effect = [
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            TestException(),
            (clis[0], ('127.0.0.2', 8082)),
            (clis[1], ('127.0.0.3', 8083)),
            (clis[2], ('127.0.0.4', 8084)),
            TestException(),
            TestException(),
            TestException(),
        ]
        tendrils = [mock.Mock(), mock.Mock(), mock.Mock()]
        mock_TCPTendril.side_effect = tendrils[:]
        acceptor = mock.Mock(side_effect=[
            mock.Mock(),
            TestException(),
            mock.Mock(),
        ])
        manager = tcp.TCPTendrilManager()
        manager.running = True

        with self.assertRaises(TestException):
            manager.listener(acceptor, None)

        self.assertFalse(mock_sleep.called)
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.assert_has_calls([
            mock.call.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1),
            mock.call.bind(('', 0)),
            mock.call.getsockname(),
            mock.call.listen(1024),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.accept(),
            mock.call.close(),
        ])
        self.assertEqual(manager.local_addr, ('127.0.0.1', 8080))
        mock_TCPTendril.assert_has_calls([
            mock.call(manager, clis[0], ('127.0.0.2', 8082)),
            mock.call(manager, clis[1], ('127.0.0.3', 8083)),
            mock.call(manager, clis[2], ('127.0.0.4', 8084)),
        ])
        acceptor.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[1]),
            mock.call(tendrils[2]),
        ])
        self.assertFalse(clis[0].close.called)
        clis[1].close.assert_called_once_with()
        self.assertFalse(clis[2].close.called)
        mock_track_tendril.assert_has_calls([
            mock.call(tendrils[0]),
            mock.call(tendrils[2]),
        ])
        tendrils[0]._start.assert_called_once_with()
        self.assertFalse(tendrils[1]._start.called)
        tendrils[2]._start.assert_called_once_with()
