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
from tendril import connection
from tendril import framers


class TestException(Exception):
    pass


class TendrilForTest(connection.Tendril):
    proto = 'test'

    def send_frame(self, frame):
        pass

    def close(self):
        super(TendrilForTest, self).close()


class ApplicationForTest(application.Application):
    def recv_frame(self, frame):
        pass


class TestTendril(unittest.TestCase):
    def test_init(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(tend.manager, 'manager')
        self.assertEqual(tend.local_addr, 'local')
        self.assertEqual(tend.remote_addr, 'remote')
        self.assertEqual(tend._application, None)
        self.assertIsInstance(tend._send_framer, framers.IdentityFramer)
        self.assertIsInstance(tend._recv_framer, framers.IdentityFramer)
        self.assertEqual(id(tend._send_framer), id(tend._recv_framer))
        self.assertIsInstance(tend._send_framer_state, framers.FrameState)
        self.assertIsInstance(tend._recv_framer_state, framers.FrameState)

    @mock.patch.object(TendrilForTest, 'default_framer',
                       new=framers.LineFramer)
    def test_init_alt_framer(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(tend.manager, 'manager')
        self.assertEqual(tend.local_addr, 'local')
        self.assertEqual(tend.remote_addr, 'remote')
        self.assertEqual(tend._application, None)
        self.assertIsInstance(tend._send_framer, framers.LineFramer)
        self.assertIsInstance(tend._recv_framer, framers.LineFramer)
        self.assertEqual(id(tend._send_framer), id(tend._recv_framer))
        self.assertIsInstance(tend._send_framer_state, framers.FrameState)
        self.assertIsInstance(tend._recv_framer_state, framers.FrameState)

    def test_wrap(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertRaises(NotImplementedError, tend.wrap, 'wrapper')

    def test_closed_noapp(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        tend.closed('error')

        # Verifying that it doesn't raise an exception

    def test_closed_withapp(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._application = mock.Mock()

        tend.closed('error')

        tend._application.closed.assert_called_once_with('error')

    def test_closed_witherrorapp(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._application = mock.Mock(**{
            'closed.side_effect': TestException()
        })

        tend.closed('error')

        tend._application.closed.assert_called_once_with('error')

    def test_tendril_key(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(tend._tendril_key, ('local', 'remote'))

    def test_send_framer_getter(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(id(tend.send_framer), id(tend._send_framer))

    def test_send_framer_setter_badsubclass(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        send_framer = tend._send_framer

        with self.assertRaises(ValueError):
            tend.send_framer = mock.Mock()

        self.assertEqual(id(send_framer), id(tend._send_framer))

    def test_send_framer_setter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        sub_framer = framers.LineFramer()

        tend.send_framer = sub_framer

        self.assertEqual(id(sub_framer), id(tend._send_framer))

    def test_send_framer_deleter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = 'framer'

        del tend.send_framer

        self.assertIsInstance(tend._send_framer, framers.IdentityFramer)

    @mock.patch.object(TendrilForTest, 'default_framer',
                       new=framers.LineFramer)
    def test_send_framer_deleter_alt_framer(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = 'framer'

        del tend.send_framer

        self.assertIsInstance(tend._send_framer, framers.LineFramer)

    def test_send_framer_state(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(id(tend.send_framer_state),
                         id(tend._send_framer_state))

    def test_recv_framer_getter(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(id(tend.recv_framer), id(tend._recv_framer))

    def test_recv_framer_setter_badsubclass(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        recv_framer = tend._recv_framer

        with self.assertRaises(ValueError):
            tend.recv_framer = mock.Mock()

        self.assertEqual(id(recv_framer), id(tend._recv_framer))

    def test_recv_framer_setter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        sub_framer = framers.LineFramer()

        tend.recv_framer = sub_framer

        self.assertEqual(id(sub_framer), id(tend._recv_framer))

    def test_recv_framer_deleter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._recv_framer = 'framer'

        del tend.recv_framer

        self.assertIsInstance(tend._recv_framer, framers.IdentityFramer)

    @mock.patch.object(TendrilForTest, 'default_framer',
                       new=framers.LineFramer)
    def test_recv_framer_deleter_alt_framer(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._recv_framer = 'framer'

        del tend.recv_framer

        self.assertIsInstance(tend._recv_framer, framers.LineFramer)

    def test_recv_framer_state(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        self.assertEqual(id(tend.recv_framer_state),
                         id(tend._recv_framer_state))

    def test_framers_getter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = 'send'
        tend._recv_framer = 'recv'

        framers = tend.framers

        self.assertIsInstance(framers, connection.TendrilFramers)
        self.assertEqual(framers, ('send', 'recv'))

    def test_framers_setter_tuple(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        send = framers.IdentityFramer()
        recv = framers.IdentityFramer()

        tend.framers = (send, recv)

        self.assertEqual(id(tend._send_framer), id(send))
        self.assertEqual(id(tend._recv_framer), id(recv))

    def test_framers_setter_badtuple(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        framer = framers.IdentityFramer()

        with self.assertRaises(ValueError):
            tend.framers = (framer, framer, framer)
        with self.assertRaises(ValueError):
            tend.framers = (framer,)

        self.assertNotEqual(id(tend._send_framer), id(framer))
        self.assertNotEqual(id(tend._recv_framer), id(framer))

    def test_framers_setter_tuple_badframers(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        framer = framers.IdentityFramer()

        with self.assertRaises(ValueError):
            tend.framers = ('send', framer)
        with self.assertRaises(ValueError):
            tend.framers = (framer, 'recv')

        self.assertNotEqual(id(tend._send_framer), id(framer))
        self.assertNotEqual(id(tend._recv_framer), id(framer))

    def test_framers_setter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        framer = framers.IdentityFramer()

        tend.framers = framer

        self.assertEqual(id(tend._send_framer), id(framer))
        self.assertEqual(id(tend._recv_framer), id(framer))

    def test_framers_setter_badframer(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        framer = mock.Mock()

        with self.assertRaises(ValueError):
            tend.framers = framer

        self.assertNotEqual(id(tend._send_framer), id(framer))
        self.assertNotEqual(id(tend._recv_framer), id(framer))

    def test_framers_deleter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = 'framer'
        tend._recv_framer = 'framer'

        del tend.framers

        self.assertIsInstance(tend._send_framer, framers.IdentityFramer)
        self.assertIsInstance(tend._recv_framer, framers.IdentityFramer)
        self.assertEqual(id(tend._send_framer), id(tend._recv_framer))

    @mock.patch.object(TendrilForTest, 'default_framer',
                       new=framers.LineFramer)
    def test_framers_deleter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = 'framer'
        tend._recv_framer = 'framer'

        del tend.framers

        self.assertIsInstance(tend._send_framer, framers.LineFramer)
        self.assertIsInstance(tend._recv_framer, framers.LineFramer)
        self.assertEqual(id(tend._send_framer), id(tend._recv_framer))

    def test_framer_states(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer_state = 'send'
        tend._recv_framer_state = 'recv'

        states = tend.framer_states

        self.assertIsInstance(states, connection.TendrilFramerStates)
        self.assertEqual(states, ('send', 'recv'))

    def test_application_getter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._application = 'application'

        self.assertEqual(tend.application, 'application')

    def test_application_setter_none(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._application = 'application'

        tend.application = None

        self.assertEqual(tend._application, None)

    def test_application_setter_badapp(self):
        tend = TendrilForTest('manager', 'local', 'remote')

        with self.assertRaises(ValueError):
            tend.application = 'application'

        self.assertEqual(tend._application, None)

    def test_application_setter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        app = ApplicationForTest(tend)
        tend.application = app

        self.assertEqual(id(tend._application), id(app))

    def test_application_deleter(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._application = 'application'

        del tend.application

        self.assertEqual(tend._application, None)

    def test_send_streamify(self):
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._send_framer = mock.Mock(
            **{'streamify.return_value': "streamified"})
        tend._send_framer_state = mock.Mock()

        result = tend._send_streamify('frame')

        tend._send_framer_state._reset.assert_called_once_with(
            tend._send_framer)
        tend._send_framer.streamify.assert_called_once_with(
            tend._send_framer_state, 'frame')
        self.assertEqual(result, 'streamified')

    def test_recv_frameify(self):
        generator = mock.Mock(**{'next.side_effect': ['frame1', 'frame2',
                                                      'frame3', 'frame4',
                                                      StopIteration]})
        tend = TendrilForTest('manager', 'local', 'remote')
        tend._recv_framer_state = mock.Mock()
        tend._recv_framer = mock.Mock(**{'frameify.return_value': generator})
        tend._application = mock.Mock()

        tend._recv_frameify("this is a test")

        tend._recv_framer_state._reset.assert_called_once_with(
            tend._recv_framer)
        tend._recv_framer.frameify.assert_called_once_with(
            tend._recv_framer_state, 'this is a test')
        self.assertEqual(generator.next.call_count, 5)
        tend._application.recv_frame.assert_has_calls([
            mock.call('frame1'),
            mock.call('frame2'),
            mock.call('frame3'),
            mock.call('frame4'),
        ])

    def test_recv_frameify_switch(self):
        class Switcher(object):
            def __init__(inst, tend, framers):
                inst.tendril = tend
                inst.framers = framers
                inst.frames = []

            def recv_frame(inst, frame):
                inst.frames.append(frame)
                if frame in inst.framers:
                    inst.tendril._recv_framer = inst.framers[frame]

        generators = [
            mock.Mock(**{'next.side_effect': ['frame1', 'frame2',
                                              'switch1', 'badframe',
                                              StopIteration],
                         'throw.side_effect': StopIteration}),
            mock.Mock(**{'next.side_effect': ['frame3', 'frame4',
                                              'switch2', 'badframe',
                                              StopIteration],
                         'throw.side_effect': StopIteration}),
            mock.Mock(**{'next.side_effect': ['frame5', 'frame6',
                                              'frame7', 'frame8',
                                              StopIteration],
                         'throw.side_effect': StopIteration}),
        ]

        framers = dict(('switch%d' % i,
                        mock.Mock(**{'frameify.return_value': gen}))
                       for i, gen in enumerate(generators))

        tend = TendrilForTest('manager', 'local', 'remote')
        tend._recv_framer_state = mock.Mock()
        tend._recv_framer = framers['switch0']
        tend._application = Switcher(tend, framers)

        tend._recv_frameify("this is a test")

        tend._recv_framer_state._reset.assert_has_calls([
            mock.call(framers['switch0']),
            mock.call(framers['switch1']),
            mock.call(framers['switch2']),
        ])
        framers['switch0'].frameify.assert_called_once_with(
            tend._recv_framer_state, 'this is a test')
        framers['switch1'].frameify.assert_called_once_with(
            tend._recv_framer_state, '')
        framers['switch2'].frameify.assert_called_once_with(
            tend._recv_framer_state, '')
        self.assertEqual(tend._application.frames, [
            'frame1', 'frame2', 'switch1',
            'frame3', 'frame4', 'switch2',
            'frame5', 'frame6', 'frame7', 'frame8',
        ])

    def test_close(self):
        tend = TendrilForTest(mock.Mock(), 'local', 'remote')

        tend.close()

        tend.manager._untrack_tendril.assert_called_once_with(tend)
