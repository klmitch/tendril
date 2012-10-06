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

import inspect
import unittest

import mock

from tendril import framers


class TestFrameState(unittest.TestCase):
    def test_init(self):
        state = framers.FrameState()

        self.assertEqual(state.recv_buf, '')
        self.assertEqual(state.send_buf, [])
        self.assertEqual(state._other, {})
        self.assertEqual(state._framer_id, None)

    def test_getattr(self):
        state = framers.FrameState()
        state._other.update(a=1, _b=2)

        self.assertEqual(state.recv_buf, '')
        self.assertEqual(state.send_buf, [])
        self.assertEqual(state.a, 1)
        with self.assertRaises(AttributeError):
            dummy = state.b
        with self.assertRaises(AttributeError):
            dummy = state._b

    def test_setattr(self):
        state = framers.FrameState()

        state.recv_buf = 'foobar'
        state.send_buf = [1, 2, 3]
        state._framer_id = 'foo'
        state.a = 1

        self.assertEqual(state.recv_buf, 'foobar')
        self.assertEqual(state.send_buf, [1, 2, 3])
        self.assertEqual(state._framer_id, 'foo')
        self.assertEqual(state._other, dict(a=1))

    def test_delattr(self):
        state = framers.FrameState()
        state._other.update(a=1, _b=2)

        with self.assertRaises(AttributeError):
            del state.recv_buf
        with self.assertRaises(AttributeError):
            del state.send_buf
        with self.assertRaises(AttributeError):
            del state._b
        del state.a
        self.assertEqual(state._other, dict(_b=2))
        with self.assertRaises(AttributeError):
            del state.a

    def test_reset(self):
        state = framers.FrameState()
        state.recv_buf = 'foobar'
        state.send_buf = [1, 2, 3]
        state._other.update(a=1, b=2, c=3)

        mock_framer = mock.Mock()
        state._reset(mock_framer)

        self.assertEqual(state.recv_buf, 'foobar')
        self.assertEqual(state.send_buf, [1, 2, 3])
        self.assertEqual(state._other, {})
        self.assertEqual(state._framer_id, id(mock_framer))
        mock_framer.init_state.assert_called_once_with(state)

        state.recv_buf += 'baz'
        state.send_buf.append(4)
        state.a = 3
        state.b = 2
        state.c = 1

        mock_framer.reset_mock()
        state._reset(mock_framer)

        self.assertEqual(state.recv_buf, 'foobarbaz')
        self.assertEqual(state.send_buf, [1, 2, 3, 4])
        self.assertEqual(state._other, dict(a=3, b=2, c=1))
        self.assertEqual(state._framer_id, id(mock_framer))
        self.assertFalse(mock_framer.init_state.called)


class TestFramer(unittest.TestCase):
    framer_class = framers.Framer
    clear_state = {}

    def test_has_all_methods(self):
        self.assertTrue(hasattr(self.framer_class, 'init_state'))
        self.assertTrue(callable(self.framer_class.init_state))
        self.assertTrue(hasattr(self.framer_class, 'frameify'))
        self.assertTrue(callable(self.framer_class.frameify))
        self.assertTrue(hasattr(self.framer_class, 'streamify'))
        self.assertTrue(callable(self.framer_class.streamify))

    def test_framify_is_generator(self):
        self.assertTrue(inspect.isgeneratorfunction(
            self.framer_class.frameify))

    def check_init_state(self, *args, **kwargs):
        # Instantiate the framer...
        f = self.framer_class(*args, **kwargs)

        # Get a frame state
        state = framers.FrameState()
        state._reset(f)

        # Confirm the state is correct
        self.assertEqual(state.recv_buf, '')
        self.assertEqual(state.send_buf, [])
        self.assertEqual(state._other, self.clear_state)

    def check_interrupt(self, stream, frame, rest, *args, **kwargs):
        # Instantiate the framer...
        f = self.framer_class(*args, **kwargs)

        # Also need a frame state
        state = framers.FrameState()
        state._reset(f)

        # Set up the generator
        gen = f.frameify(state, stream)

        # Get one frame
        fr1 = gen.next()

        self.assertEqual(fr1, frame)

        # Interrupt the framer
        with self.assertRaises(StopIteration):
            gen.throw(framers.FrameSwitch())

        self.assertEqual(state.recv_buf, rest)

    def check_composition(self, frames, *args, **kwargs):
        # Instantiate the framer...
        f = self.framer_class(*args, **kwargs)

        # Also need a frame state
        state = framers.FrameState()
        state._reset(f)

        # Convert the incoming frames into a stream
        stream = ''
        for frame in frames:
            stream += f.streamify(state, frame)

        # Now go the other way
        gen = f.frameify(state, stream)
        self.assertTrue(inspect.isgenerator(gen))
        results = list(gen)

        # Confirm that the state has been reset
        self.assertEqual(state.recv_buf, '')
        self.assertEqual(state.send_buf, [])
        self.assertEqual(state._other, self.clear_state)
        self.assertEqual(frames, results)


class TestIdentityFramer(TestFramer):
    framer_class = framers.IdentityFramer

    def test_init_state(self):
        self.check_init_state()

    def test_frameify(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'this is a test')

        self.assertEqual(list(result), ['this is a test'])
        self.assertEqual(s.recv_buf, '')

    def test_frameify_buffered(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = 'this is '

        result = f.frameify(s, 'a test')

        self.assertEqual(list(result), ['this is a test'])
        self.assertEqual(s.recv_buf, '')

    def test_frameify_interrupt(self):
        self.check_interrupt('this is a test', 'this is a test', '')

    def test_streamify(self):
        f = self.framer_class()

        result = f.streamify(None, 'this is a test')

        self.assertEqual(result, 'this is a test')

    def test_composition(self):
        self.check_composition(['this is a test'])


class TestChunkFramer(TestFramer):
    framer_class = framers.ChunkFramer
    clear_state = dict(chunk_remaining=20)

    def test_init(self):
        f = self.framer_class(255)

        self.assertEqual(f.chunk_len, 255)

    def test_init_state(self):
        self.check_init_state(20)

    def test_frameify(self):
        f = self.framer_class(10)
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, '1234567890')

        self.assertEqual(list(result), ['1234567890'])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, dict(chunk_remaining=0))

    def test_frameify_complete(self):
        f = self.framer_class(5)
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, '1234567890')

        self.assertEqual(list(result), ['12345'])
        self.assertEqual(s.recv_buf, '67890')
        self.assertEqual(s._other, dict(chunk_remaining=0))

    def test_frameify_buffered(self):
        f = self.framer_class(20)
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = '12345'

        result = f.frameify(s, '67890')

        self.assertEqual(list(result), ['1234567890'])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, dict(chunk_remaining=10))

    def test_frameify_buffering(self):
        f = self.framer_class(0)
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = '12345'

        result = f.frameify(s, '67890')

        self.assertEqual(list(result), [])
        self.assertEqual(s.recv_buf, '1234567890')
        self.assertEqual(s._other, dict(chunk_remaining=0))

    @mock.patch.dict(clear_state, chunk_remaining=0)
    def test_frameify_interrupt(self):
        self.check_interrupt('1234567890', '12345', '67890', 5)

    @mock.patch.dict(clear_state, chunk_remaining=0)
    def test_composition(self):
        self.check_composition(['1234567890'], 10)


class TestLineFramer(TestFramer):
    framer_class = framers.LineFramer

    def test_init(self):
        f1 = self.framer_class()
        f2 = self.framer_class(False)

        self.assertEqual(f1.carriage_return, True)
        self.assertEqual(f2.carriage_return, False)
        self.assertEqual(f1.line_end, '\r\n')
        self.assertEqual(f2.line_end, '\n')

    def test_frameify(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'frame1\nframe2\r\n')

        self.assertEqual(list(result), ['frame1', 'frame2'])
        self.assertEqual(s.recv_buf, '')

    def test_frameify_nocr(self):
        f = self.framer_class(False)
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'frame1\nframe2\r\n')

        self.assertEqual(list(result), ['frame1', 'frame2\r'])
        self.assertEqual(s.recv_buf, '')

    def test_frameify_buffered(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = 'this is '

        result = f.frameify(s, 'frame1\nframe2')

        self.assertEqual(list(result), ['this is frame1'])
        self.assertEqual(s.recv_buf, 'frame2')

    def test_frameify_interrupt(self):
        self.check_interrupt('frame1\nframe2\n', 'frame1', 'frame2\n')

    def test_streamify(self):
        f = self.framer_class()

        result = f.streamify(None, 'this is a test')

        self.assertEqual(result, 'this is a test\r\n')

    def test_streamify_nocr(self):
        f = self.framer_class(False)

        result = f.streamify(None, 'this is a test')

        self.assertEqual(result, 'this is a test\n')

    def test_composition(self):
        self.check_composition(['frame1', 'frame2', 'frame3', 'frame4'])

    def test_composition_nocr(self):
        self.check_composition(['frame1', 'frame2', 'frame3', 'frame4'])


class TestStructFramer(TestFramer):
    framer_class = framers.StructFramer
    clear_state = dict(frame_len=None)

    def make_frame(self, text, length=None):
        return chr(len(text) if length is None else length) + text

    def test_init(self):
        self.assertRaises(ValueError, self.framer_class, 'z')
        self.assertRaises(ValueError, self.framer_class, 'ii')
        self.assertRaises(ValueError, self.framer_class, '!')

        f = self.framer_class('!B')

        self.assertEqual(f.fmt.format, '!B')

    def test_init_state(self):
        self.check_init_state('!B')

    def test_frameify(self):
        f = self.framer_class('!B')
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, ''.join([
            self.make_frame('frame1'),
            self.make_frame('frame2'),
        ]))

        self.assertEqual(list(result), ['frame1', 'frame2'])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_buffered(self):
        f = self.framer_class('!B')
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = self.make_frame('sp', 5)

        result = f.frameify(s, ''.join(['am1', self.make_frame('sp', 5)]))

        self.assertEqual(list(result), ['spam1'])
        self.assertEqual(s.recv_buf, 'sp')
        self.assertEqual(s._other, dict(frame_len=5))

    def test_frameify_buffered_len(self):
        f = self.framer_class('<i')
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, self.make_frame('\0', 4))

        self.assertEqual(list(result), [])
        self.assertEqual(s.recv_buf, self.make_frame('\0', 4))
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_interrupt(self):
        self.check_interrupt(''.join([
            self.make_frame('frame1'),
            self.make_frame('frame2'),
        ]), 'frame1', self.make_frame('frame2'), '!B')

    def test_streamify_byte(self):
        f = self.framer_class('!B')

        result = f.streamify(None, 'this is a test')

        self.assertEqual(result, self.make_frame('this is a test'))

    def test_streamify_int(self):
        f = self.framer_class('>i')

        result = f.streamify(None, 'this is a test')

        self.assertEqual(result, '\0\0\0' + self.make_frame('this is a test'))

    def test_composition(self):
        self.check_composition(['frame1', 'frame2', 'frame3', 'frame4'], '!B')


class TestStuffingFramer(TestFramer):
    framer_class = framers.StuffingFramer
    clear_state = dict(frame_start=False)

    def test_init(self):
        self.assertRaises(ValueError, self.framer_class, begin='aa')
        self.assertRaises(ValueError, self.framer_class, end='aa')
        self.assertRaises(ValueError, self.framer_class, nop='aa')
        self.assertRaises(ValueError, self.framer_class, begin='a', nop='a')
        self.assertRaises(ValueError, self.framer_class, end='a', nop='a')
        self.assertRaises(ValueError, self.framer_class, begin='a', end='a')

        f = self.framer_class('aaa', begin='a', end='b', nop='c')

        self.assertEqual(f.prefix, 'aaa')
        self.assertEqual(f.begin, 'a')
        self.assertEqual(f.end, 'b')
        self.assertEqual(f.nop, 'c')

    def test_init_state(self):
        self.check_init_state()

    def test_frameify(self):
        f = self.framer_class(prefix='zzz', begin='z', end='w', nop='a')
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'zzzzthis is a testzzzwzzzzdid it work?zzzw')

        self.assertEqual(list(result), ['this is a test', 'did it work?'])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_nop(self):
        f = self.framer_class(prefix='zzz', begin='z', end='w', nop='a')
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'zzzzthis is a zzzazzzzw')

        self.assertEqual(list(result), ['this is a zzzz'])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_buffered_nostart(self):
        f = self.framer_class(prefix='zzz', begin='z', end='w', nop='a')
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = 'zzz'

        result = f.frameify(s, 'zthis is a testzzzwzzz')

        self.assertEqual(list(result), ['this is a test'])
        self.assertEqual(s.recv_buf, 'zzz')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_buffered_noend(self):
        f = self.framer_class(prefix='zzz', begin='z', end='w', nop='a')
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, 'zzzzthis is a testzzzwzzzzdid it work?zzz')

        self.assertEqual(list(result), ['this is a test'])
        self.assertEqual(s.recv_buf, 'did it work?zzz')
        self.assertEqual(s._other, dict(frame_start=True))

    def test_frameify_interrupt(self):
        self.check_interrupt('zzzzthis is a testzzzwzzzzdid it work?zzzw',
                             'this is a test', 'zzzzdid it work?zzzw',
                             prefix='zzz', begin='z', end='w', nop='a')

    def test_streamify(self):
        f = self.framer_class(prefix='zzz', begin='z', end='w', nop='a')

        result = f.streamify(None, 'this is a zzzz so I wonder zzzzzzzzzzz '
                             'if it worked')

        self.assertEqual(result, 'zzzzthis is a zzzaz so I wonder '
                         'zzzazzzazzzazz if it workedzzzw')

    def test_composition(self):
        self.check_composition([
            'test one',
            'test zzzzzzzzzzzw two',
            'zzzz test three zzzw',
        ])


class TestCOBSFramer(TestFramer):
    framer_class = framers.COBSFramer

    def test_init(self):
        f1 = self.framer_class()
        f2 = self.framer_class(True)

        self.assertEqual(f1.zpe, False)
        self.assertEqual(f2.zpe, True)

    def test_frameify(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, '\x01\x01\x00'
                            '\x03\x11\x22\x02\x33\x00'
                            '\x02\x11\x01\x01\x01\x00'
                            '\xff' + ''.join(chr(i) for i in range(1, 255)) +
                            '\x02\xff\x00')

        self.assertEqual(list(result), [
            '\x00',
            '\x11\x22\x00\x33',
            '\x11\x00\x00\x00',
            ''.join(chr(i) for i in range(1, 256)),
        ])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_buffered(self):
        f = self.framer_class()
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = '\xff' + ''.join(chr(i) for i in range(1, 255))

        result = f.frameify(s, '\x02\xff\x00\x01\x01')

        self.assertEqual(list(result), [
            ''.join(chr(i) for i in range(1, 256)),
        ])
        self.assertEqual(s.recv_buf, '\x01\x01')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_interrupt(self):
        self.check_interrupt('\x01\x01\x00\x03\x11\x22\x02\x33\x00',
                             '\x00', '\x03\x11\x22\x02\x33\x00')

    def test_frameify_zpe(self):
        f = self.framer_class(True)
        s = framers.FrameState()
        s._reset(f)

        result = f.frameify(s, '\xe1\x00'
                            '\x03\x11\x22\x02\x33\x00'
                            '\xe2\x11\xe1\x00'
                            '\xe0' + ''.join(chr(i) for i in range(1, 224)) +
                            '\x21' + ''.join(chr(i) for i in range(224, 256)) +
                            '\x00')

        self.assertEqual(list(result), [
            '\x00',
            '\x11\x22\x00\x33',
            '\x11\x00\x00\x00',
            ''.join(chr(i) for i in range(1, 256)),
        ])
        self.assertEqual(s.recv_buf, '')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_zpe_buffered(self):
        f = self.framer_class(True)
        s = framers.FrameState()
        s._reset(f)
        s.recv_buf = '\xe0' + ''.join(chr(i) for i in range(1, 224))

        result = f.frameify(s, '\x21' +
                            ''.join(chr(i) for i in range(224, 256)) +
                            '\x00\xe1')

        self.assertEqual(list(result), [
            ''.join(chr(i) for i in range(1, 256)),
        ])
        self.assertEqual(s.recv_buf, '\xe1')
        self.assertEqual(s._other, self.clear_state)

    def test_frameify_zpe_interrupt(self):
        self.check_interrupt('\xe1\x00\x03\x11\x22\x02\x33\x00',
                             '\x00', '\x03\x11\x22\x02\x33\x00', True)

    def test_streamify(self):
        f = self.framer_class()

        result = f.streamify(None, '\x00')

        self.assertEqual(result, '\x01\x01\x00')

        result = f.streamify(None, '\x11\x22\x00\x33')

        self.assertEqual(result, '\x03\x11\x22\x02\x33\x00')

        result = f.streamify(None, '\x11\x00\x00\x00')

        self.assertEqual(result, '\x02\x11\x01\x01\x01\x00')

        result = f.streamify(None, ''.join(chr(i) for i in range(1, 256)))

        self.assertEqual(result, '\xff' +
                         ''.join(chr(i) for i in range(1, 255)) +
                         '\x02\xff\x00')

    def test_streamify_zpe(self):
        f = self.framer_class(True)

        result = f.streamify(None, '\x00')

        self.assertEqual(result, '\xe1\x00')

        result = f.streamify(None, '\x11\x22\x00\x33')

        self.assertEqual(result, '\x03\x11\x22\x02\x33\x00')

        result = f.streamify(None, '\x11\x00\x00\x00')

        self.assertEqual(result, '\xe2\x11\xe1\x00')

        result = f.streamify(None, ''.join(chr(i) for i in range(1, 256)))

        self.assertEqual(result, '\xe0' +
                         ''.join(chr(i) for i in range(1, 224)) + '\x21' +
                         ''.join(chr(i) for i in range(224, 256)) + '\x00')

    def test_composition(self):
        self.check_composition([
            '\x00',
            '\x11\x22\x00\x33',
            '\x11\x00\x00\x00',
            ''.join(chr(i) for i in range(1, 256)),
        ])

    def test_composition_zpe(self):
        self.check_composition([
            '\x00',
            '\x11\x22\x00\x33',
            '\x11\x00\x00\x00',
            ''.join(chr(i) for i in range(1, 256)),
        ], True)
