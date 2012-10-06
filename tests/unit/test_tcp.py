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

import socket
import unittest

import gevent
from gevent import coros
from gevent import event
import mock

from tendril import framers
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

    @mock.patch('gevent.spawn')
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

    @mock.patch('tendril.connection.Tendril.close')
    @mock.patch.object(tcp.TCPTendril, '_recv_frameify')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    @mock.patch('gevent.sleep')
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

    @mock.patch('tendril.connection.Tendril.close')
    @mock.patch.object(tcp.TCPTendril, '_recv_frameify')
    @mock.patch.object(tcp.TCPTendril, 'closed')
    @mock.patch('gevent.sleep')
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
