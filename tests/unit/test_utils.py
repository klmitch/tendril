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
from gevent import socket
import mock

from tendril import utils


class TestTendrilPartial(unittest.TestCase):
    def test_init(self):
        partial = utils.TendrilPartial('func', 1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(partial.func, 'func')
        self.assertEqual(partial.args, (1, 2, 3))
        self.assertEqual(partial.kwargs, dict(a=4, b=5, c=6))

    def test_call(self):
        func = mock.Mock(return_value="result")
        partial = utils.TendrilPartial(func, 1, 2, 3, a=4, b=5, c=6)
        result = partial("arg1", "arg2", "arg3")

        self.assertEqual(result, "result")
        func.assert_called_once_with("arg1", "arg2", "arg3", 1, 2, 3,
                                     a=4, b=5, c=6)


class TestWrapperChain(unittest.TestCase):
    def test_init(self):
        chain = utils.WrapperChain()

        self.assertEqual(chain._wrappers, [])

    def test_init_wrapper(self):
        chain = utils.WrapperChain('wrapper')

        self.assertEqual(chain._wrappers, ['wrapper'])

    @mock.patch.object(utils, 'TendrilPartial',
                       new=lambda func, *args, **kwargs: (func, args, kwargs))
    def test_init_wrapper_args(self):
        chain = utils.WrapperChain('wrapper', 1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(chain._wrappers, [
            ('wrapper', (1, 2, 3), dict(a=4, b=5, c=6)),
        ])

    @mock.patch.object(utils, 'TendrilPartial',
                       new=lambda func, *args, **kwargs: (func, args, kwargs))
    def test_chain(self):
        # chain() has already been tested during the tests of
        # __init__() above, so we need merely do one last double-check
        # and test the convenience return
        chain = utils.WrapperChain()

        result = chain.chain('wrapper', 1, 2, 3, a=4, b=5, c=6)

        self.assertEqual(id(chain), id(result))
        self.assertEqual(chain._wrappers, [
            ('wrapper', (1, 2, 3), dict(a=4, b=5, c=6)),
        ])

    def test_call(self):
        chain = utils.WrapperChain(mock.Mock(return_value="sock2"))\
            .chain(mock.Mock(return_value="sock3"))\
            .chain(mock.Mock(return_value="sock4"))

        result = chain("sock1")

        self.assertEqual(result, "sock4")
        chain._wrappers[0].assert_called_once_with("sock1")
        chain._wrappers[1].assert_called_once_with("sock2")
        chain._wrappers[2].assert_called_once_with("sock3")


class TestAddrInfo(unittest.TestCase):
    def test_accept_unix(self):
        result = utils.addr_info('unixaddr')

        self.assertEqual(result, socket.AF_UNIX)

    def test_reject_nonseq(self):
        self.assertRaises(ValueError, utils.addr_info, mock.Mock())

    def test_reject_short(self):
        self.assertRaises(ValueError, utils.addr_info, ('127.0.0.1',))

    def test_reject_badport(self):
        self.assertRaises(ValueError, utils.addr_info, ('127.0.0.1', -1))
        self.assertRaises(ValueError, utils.addr_info, ('127.0.0.1', 65536))

    def test_accept_empty(self):
        result = utils.addr_info(('', 8080))

        self.assertEqual(result, socket.AF_INET)

    def test_reject_empty_too_many_fields(self):
        self.assertRaises(ValueError, utils.addr_info, ('', 8080, 0))

    def test_accept_ipv6(self):
        result = utils.addr_info(('::1', 8080))

        self.assertEqual(result, socket.AF_INET6)

    def test_accept_ipv6_flowinfo(self):
        result = utils.addr_info(('::1', 8080, 0))

        self.assertEqual(result, socket.AF_INET6)

    def test_accept_ipv6_scopeid(self):
        result = utils.addr_info(('::1', 8080, 0, 0))

        self.assertEqual(result, socket.AF_INET6)

    def test_reject_ipv6_too_many_fields(self):
        self.assertRaises(ValueError, utils.addr_info, ('::1', 8080, 0, 0, 0))

    def test_accept_ipv4(self):
        result = utils.addr_info(('127.0.0.1', 8080))

        self.assertEqual(result, socket.AF_INET)

    def test_reject_ipv4_too_many_fields(self):
        self.assertRaises(ValueError, utils.addr_info, ('127.0.0.1', 8080, 0))

    def test_reject_unknown(self):
        self.assertRaises(ValueError, utils.addr_info, ('unknown', 8080))


class TestException(Exception):
    pass


class TestSocketCloser(unittest.TestCase):
    def test_init(self):
        closer = utils.SocketCloser('sock')

        self.assertEqual(closer.sock, 'sock')
        self.assertEqual(closer.err_thresh, 0)
        self.assertEqual(closer.errors, None)
        self.assertEqual(closer.ignore, frozenset())

    def test_init_err_thresh(self):
        closer = utils.SocketCloser('sock', 10)

        self.assertEqual(closer.sock, 'sock')
        self.assertEqual(closer.err_thresh, 10)
        self.assertEqual(closer.errors, 0)
        self.assertEqual(closer.ignore, frozenset())

    def test_init_ignore(self):
        closer = utils.SocketCloser('sock', ignore=[TestException])

        self.assertEqual(closer.sock, 'sock')
        self.assertEqual(closer.err_thresh, 0)
        self.assertEqual(closer.errors, None)
        self.assertEqual(closer.ignore, frozenset([TestException]))

    def test_enter(self):
        closer = utils.SocketCloser('sock')
        result = closer.__enter__()

        self.assertEqual(closer, result)

    def test_exit_noerror(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock)

        result = closer.__exit__(None, None, None)

        self.assertEqual(result, None)
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, None)

    def test_exit_error(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, None)

    def test_exit_ignore(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, ignore=[TestException])

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, True)
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, None)

    def test_exit_kill(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock)

        result = closer.__exit__(gevent.GreenletExit, gevent.GreenletExit(),
                                 [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, None)

    def test_exit_closeerror(self):
        sock = mock.Mock(**{'close.side_effect': socket.error()})
        closer = utils.SocketCloser(sock)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, None)

    def test_exit_noerror_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 10)
        closer.errors = 5

        result = closer.__exit__(None, None, None)

        self.assertEqual(result, None)
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 4)

    def test_exit_error_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 1)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, True)
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 1)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 1)

    def test_exit_kill_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 10)

        result = closer.__exit__(gevent.GreenletExit, gevent.GreenletExit(),
                                 [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 0)

    def test_exit_closeerror_thresh(self):
        sock = mock.Mock(**{'close.side_effect': socket.error()})
        closer = utils.SocketCloser(sock, 1)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, True)
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 1)

        result = closer.__exit__(TestException, TestException('foo'), [])

        self.assertEqual(result, None)
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 1)

    def test_together_noerror(self):
        sock = mock.Mock()

        with utils.SocketCloser(sock):
            sock.make_call()

        sock.make_call.assert_called_once_with()
        self.assertFalse(sock.close.called)

    def test_together_error(self):
        sock = mock.Mock()

        with self.assertRaises(TestException):
            with utils.SocketCloser(sock):
                sock.make_call()
                raise TestException('spam')

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()

    def test_together_kill(self):
        sock = mock.Mock()

        with self.assertRaises(gevent.GreenletExit):
            with utils.SocketCloser(sock):
                sock.make_call()
                raise gevent.GreenletExit()

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()

    def test_together_closeerror(self):
        sock = mock.Mock(**{'close.side_effect': socket.error()})

        with self.assertRaises(TestException):
            with utils.SocketCloser(sock):
                sock.make_call()
                raise TestException('spam')

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()

    def test_together_noerror_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 10)
        closer.errors = 5

        with closer:
            sock.make_call()

        sock.make_call.assert_called_once_with()
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 4)

    def test_together_error_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 1)

        with closer:
            sock.make_call()
            raise TestException('spam')

        sock.make_call.assert_called_once_with()
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 1)

        sock.reset_mock()

        with self.assertRaises(TestException):
            with closer:
                sock.make_call()
                raise TestException('spam')

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 1)

    def test_together_kill_thresh(self):
        sock = mock.Mock()
        closer = utils.SocketCloser(sock, 10)

        with self.assertRaises(gevent.GreenletExit):
            with closer:
                sock.make_call()
                raise gevent.GreenletExit()

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 0)

    def test_together_closeerror_thresh(self):
        sock = mock.Mock(**{'close.side_effect': socket.error()})
        closer = utils.SocketCloser(sock, 1)

        with closer:
            sock.make_call()
            raise TestException('spam')

        sock.make_call.assert_called_once_with()
        self.assertFalse(sock.close.called)
        self.assertEqual(closer.errors, 1)

        sock.reset_mock()

        with self.assertRaises(TestException):
            with closer:
                sock.make_call()
                raise TestException('spam')

        sock.make_call.assert_called_once_with()
        sock.close.assert_called_once_with()
        self.assertEqual(closer.errors, 1)
