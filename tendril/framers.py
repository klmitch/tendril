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
import struct


__all__ = ["FrameSwitch",
           "Framer",
           "IdentityFramer", "ChunkFramer", "LineFramer", "StructFramer",
           "StuffingFramer", "COBSFramer"]


class FrameSwitch(BaseException):
    """
    Sentinel exception used to inform the framer that it should hand
    back any remaining data.
    """

    pass


class FrameState(object):
    """
    Maintain state for framers.  The ``recv_buf`` and ``send_buf``
    attributes will always be present; framers will be given an
    opportunity to initialize other state attributes as necessary.
    Framers may use any attribute name except attributes beginning
    with '_'.
    """

    def __init__(self):
        """
        Initialize the FramerState object.  The ``recv_buf`` attribute
        will be initialized to the empty string, and the ``send_buf``
        attribute will be initialized to an empty list.
        """

        self.recv_buf = ''
        self.send_buf = []

        self._other = {}
        self._framer_id = None

    def __getattr__(self, name):
        """
        Retrieve a state attribute.
        """

        # Special treatment for internal attributes
        if name[0] == '_':
            raise AttributeError('%r object has no attribute %r' %
                                 (self.__class__.__name__, name))

        try:
            return self._other[name]
        except KeyError:
            raise AttributeError('%r object has no attribute %r' %
                                 (self.__class__.__name__, name))

    def __setattr__(self, name, value):
        """
        Set a state attribute.
        """

        # Special treatment for recv_buf and internal attributes
        if name in ('recv_buf', 'send_buf') or name[0] == '_':
            return super(FrameState, self).__setattr__(name, value)

        self._other[name] = value

    def __delattr__(self, name):
        """
        Delete a state attribute.
        """

        # Special treatment for recv_buf and internal attributes
        if name in ('recv_buf', 'send_buf') or name[0] == '_':
            raise AttributeError('%r object has no attribute %r' %
                                 (self.__class__.__name__, name))

        try:
            del self._other[name]
        except KeyError:
            raise AttributeError('%r object has no attribute %r' %
                                 (self.__class__.__name__, name))

    def _reset(self, framer):
        """
        Reset the state for the framer.  It is safe to call this
        method multiple times with the same framer; the ID of the
        framer object will be saved and the state only reset if the
        IDs are different.  After resetting the state, the framer's
        ``init_state()`` method will be called.
        """

        # Do nothing if we're already properly initialized
        if id(framer) == self._framer_id:
            return

        # Reset the state
        self._other = {}

        # Initialize the state and save the framer ID
        framer.init_state(self)
        self._framer_id = id(framer)


class Framer(object):
    """
    Abstract base class for all framers.  A framer is used by a stream
    transport, such as TCP, to chop the stream up into individual
    frames.  The ``buffer`` attribute will contain any partial frame
    data.
    """

    __metaclass__ = abc.ABCMeta

    def init_state(self, state):
        """Initialize the framer state."""

        pass

    @abc.abstractmethod
    def frameify(self, state, data):
        """
        Split data into individual frames.  Must buffer any
        unprocessed data in the ``state.recv_buf`` variable.  Each
        frame must be yielded as soon as it is carved out of the
        stream.

        The yield statement may throw a FrameSwitch exception, in
        which case any remaining unprocessed data must be immediately
        placed on the buffer and the generator exited.  This is used
        if the framer is changed.
        """

        yield

    @abc.abstractmethod
    def streamify(self, state, frame):
        """
        Convert a frame into stream data.  Returns the data.
        """

        pass


class IdentityFramer(Framer):
    """
    A framer for datagram transports, such as UDP.
    """

    def frameify(self, state, data):
        """Yield the data as a single frame."""

        try:
            yield state.recv_buf + data
        except FrameSwitch:
            pass
        finally:
            state.recv_buf = ''

    def streamify(self, state, frame):
        """Return the frame as data."""

        return frame


class ChunkFramer(IdentityFramer):
    """
    A framer for short-term streaming.  Once initialized with a given
    length, it yields received data as if it were a frame; however,
    once all the specified data has been accumulated, the remainder is
    pushed onto the receive buffer.
    """

    def __init__(self, chunk_len):
        """
        Initialize the ChunkFramer.

        :param chunk_len: The amount of data to pass through.
        """

        super(ChunkFramer, self).__init__()

        self.chunk_len = chunk_len

    def init_state(self, state):
        """Initialize the framer state."""

        state.chunk_remaining = self.chunk_len

    def frameify(self, state, data):
        """Yield chunk data as a single frame, and buffer the rest."""

        # If we've pulled in all the chunk data, buffer the data
        if state.chunk_remaining <= 0:
            state.recv_buf += data
            return

        # Pull in any partially-processed data
        data = state.recv_buf + data

        # Determine how much belongs to the chunk
        if len(data) <= state.chunk_remaining:
            chunk = data
            data = ''
        else:
            # Pull out only what's part of the chunk
            chunk = data[:state.chunk_remaining]
            data = data[state.chunk_remaining:]

        # Update the state
        state.recv_buf = data
        state.chunk_remaining -= len(chunk)

        # Yield the chunk
        try:
            yield chunk
        except FrameSwitch:
            pass


class LineFramer(Framer):
    """
    A line-oriented framer.  Frames are separated by newlines or by
    carriage return/newline pairs.  The line endings are stripped off.
    """

    def __init__(self, carriage_return=True):
        """
        Initialize the LineFramer.

        :param carriage_return: If ``True`` (the default), accept
                                carriage return/newline pairs as line
                                separators.  Also causes carriage
                                returns to be emitted.  If ``False``,
                                carriage returns are not stripped from
                                input and not emitted on output.
        """

        super(LineFramer, self).__init__()

        self.carriage_return = carriage_return
        self.line_end = '\r\n' if carriage_return else '\n'

    def frameify(self, state, data):
        """Split data into a sequence of lines."""

        # Pull in any partially-processed data
        data = state.recv_buf + data

        # Loop over the data
        while data:
            line, sep, rest = data.partition('\n')

            # Did we have a whole line?
            if sep != '\n':
                break

            # OK, update the data...
            data = rest

            # Now, strip off carriage return, if there is one
            if self.carriage_return and line[-1] == '\r':
                line = line[:-1]

            # Yield the line
            try:
                yield line
            except FrameSwitch:
                break

        # Put any remaining data back into the buffer
        state.recv_buf = data

    def streamify(self, state, frame):
        """Prepare frame for output as line-oriented data."""

        return '%s%s' % (frame, self.line_end)


class StructFramer(Framer):
    """
    A struct-oriented framer.  Uses the Python struct module to
    compose together a string length followed by the appropriate
    string.  Initialize with a string containing a single struct
    conversion string for integers.  The resulting packet will consist
    of the integer length of the frame, encoded in that format,
    followed by the frame itself.
    """

    def __init__(self, fmt):
        """
        Initialize the StructFramer.

        :param fmt: The struct-compliant format string for the integer
                    length of the frame.
        """

        # Sanity-check the fmt
        fmt_chr = None
        for c in fmt:
            if c in ('@', '=', '<', '>', '!', 'x'):
                # Modifiers and pads we can ignore
                continue

            if c in ('b', 'B', 'h', 'H', 'i', 'I', 'l', 'L', 'q', 'Q'):
                if fmt_chr:
                    raise ValueError("too many specifiers in format")
                fmt_chr = c
                continue

            # Invalid specifier
            raise ValueError("unrecognized specifier in format")

        if not fmt_chr:
            raise ValueError("no recognized specifier in format")

        super(StructFramer, self).__init__()

        self.fmt = struct.Struct(fmt)

    def init_state(self, state):
        """Initialize the framer state."""

        state.frame_len = None

    def frameify(self, state, data):
        """Split data into a sequence of frames."""

        # Pull in any partially-processed data
        data = state.recv_buf + data

        # Loop over the data
        while data:
            if state.frame_len is None:
                # Try to grab a frame length from the data
                if len(data) < self.fmt.size:
                    # Not enough data; try back later
                    break

                # Extract the length
                state.frame_len = self.fmt.unpack(data[:self.fmt.size])[0]
                data = data[self.fmt.size:]

            # Now that we have the frame length, extract the frame
            if len(data) < state.frame_len:
                # Not enough data; try back later
                break

            # OK, we have a full frame...
            frame = data[:state.frame_len]
            data = data[state.frame_len:]
            state.frame_len = None

            # Yield the frame
            try:
                yield frame
            except FrameSwitch:
                break

        # Put any remaining data back into the buffer
        state.recv_buf = data

    def streamify(self, state, frame):
        """Prepare frame for output as a length/frame stream."""

        return '%s%s' % (self.fmt.pack(len(frame)), frame)


class StuffingFramer(Framer):
    """
    A byte-stuffing framer.  Uses a technique of byte stuffing for
    separating frames.  In this technique, a sequence of bytes of a
    given length is used as a marker of the beginning of the frame,
    and another of the end of the frame.  Should the sequence appear
    inside the frame, an extra, throw-away byte is stuffed in to
    ensure the sequence does not match the begin-frame sequence.  One
    advantage of byte-stuffing is that it is easily possible to find
    the beginning of the next frame in the stream even if
    synchronization is momentarily lost.
    """

    def __init__(self, prefix='\xff' * 4, begin='\xff', end='\xfe', nop='\0'):
        """
        Initialize the StuffingFramer.

        :param prefix: A sequence of bytes which prefixes the
                       begin-frame and end-frame bytes.
        :param begin: A single byte which, when following the prefix
                      sequence, indicates the beginning of a frame.
        :param end: A single byte which, when following the prefix
                    sequence, indicates the end of a frame.
        :param nop: A single byte which, when following the prefix
                    sequence, is thrown away.  Used to interrupt
                    sequences internal to the frame which could be
                    interpreted as the beginning or ending of the
                    frame.
        """

        # Do a little sanity-checking
        if len(begin) != 1 or len(end) != 1 or len(nop) != 1:
            raise ValueError("begin, end, and nop must be length 1")
        elif nop == begin or nop == end:
            raise ValueError("nop must be distinct from begin and end")
        elif begin == end:
            raise ValueError("begin and end must be distinct")

        super(StuffingFramer, self).__init__()

        self.prefix = prefix
        self.begin = begin
        self.end = end
        self.nop = nop

    def init_state(self, state):
        """Initialize the framer state."""

        state.frame_start = False

    def frameify(self, state, data):
        """Split data into a sequence of frames."""

        # Pull in any partially-processed data
        data = state.recv_buf + data

        # Loop over the data
        while data:
            if not state.frame_start:
                try:
                    idx = data.index(self.prefix + self.begin)
                except ValueError:
                    # Can't find the start of a frame...
                    break

                # Advance data to the beginning of the frame (just
                # after the marker)
                data = data[idx + len(self.prefix) + 1:]
                state.frame_start = True

            # Now that data is sitting at the frame start, let's find
            # the frame ending
            try:
                idx = data.index(self.prefix + self.end)
            except ValueError:
                # Can't find the end of the frame...
                break

            # OK, extract the frame and advance the data
            frame = data[:idx]
            data = data[idx + len(self.prefix) + 1:]
            state.frame_start = (self.begin == self.end)

            # Now we need to unstuff the frame
            frame = self.prefix.join(frame.split(self.prefix + self.nop))

            # Yield the frame
            try:
                yield frame
            except FrameSwitch:
                break

        # Put any remaining data back into the buffer
        state.recv_buf = data

    def streamify(self, state, frame):
        """Prepare frame for output as a byte-stuffed stream."""

        # Split the frame apart for stuffing...
        pieces = frame.split(self.prefix)

        return '%s%s%s%s%s' % (self.prefix, self.begin,
                               (self.prefix + self.nop).join(pieces),
                               self.prefix, self.end)


class COBSFramer(Framer):
    """
    A byte-stuffing framer using the Consistent Overhead Byte Stuffing
    algorithm.  In COBS, data is encoded so as to eliminate the zero
    byte, making that byte available to indicate frame boundaries.
    The data itself is broken into blocks of data, each of which ends
    with a zero byte.  A variant that can more efficiently encode
    pairs of zero bytes can be activated by enabling zero pair
    elimination (the ``zpe`` parameter to the constructor).
    """

    _tabs = dict(enc_cobs={}, enc_cobs_zpe={},
                 dec_cobs={}, dec_cobs_zpe={})

    @classmethod
    def _get_tab(cls):
        """Generate and return the COBS table."""

        if not cls._tabs['dec_cobs']:
            # Compute the COBS table for decoding
            cls._tabs['dec_cobs']['\xff'] = (255, '')
            cls._tabs['dec_cobs'].update(dict((chr(l), (l, '\0'))
                                              for l in range(1, 255)))

            # Compute the COBS table for encoding
            cls._tabs['enc_cobs'] = [(255, '\xff'),
                                     dict((l, chr(l))
                                          for l in range(1, 255)),
                                     ]

        return cls._tabs['dec_cobs'], cls._tabs['enc_cobs']

    @classmethod
    def _get_tab_zpe(cls):
        """Generate and return the COBS ZPE table."""

        if not cls._tabs['dec_cobs_zpe']:
            # Compute the COBS ZPE table for decoding
            cls._tabs['dec_cobs_zpe']['\xe0'] = (224, '')
            cls._tabs['dec_cobs_zpe'].update(dict((chr(l), (l, '\0'))
                                                  for l in range(1, 224)))
            cls._tabs['dec_cobs_zpe'].update(dict((chr(l), (l - 224, '\0\0'))
                                                  for l in range(225, 256)))

            # Compute the COBS ZPE table for encoding
            cls._tabs['enc_cobs_zpe'] = [(224, '\xe0'),
                                         dict((l, chr(l))
                                              for l in range(1, 224)),
                                         dict((l - 224, chr(l))
                                              for l in range(225, 256))
                                         ]

        return cls._tabs['dec_cobs_zpe'], cls._tabs['enc_cobs_zpe']

    @staticmethod
    def _decode(frame, tab):
        """Decode a frame with the help of the table."""

        blocks = []

        # Decode each block
        while frame:
            length, endseq = tab[frame[0]]
            blocks.extend([frame[1:length], endseq])
            frame = frame[length:]

        # Remove one (and only one) trailing '\0' as necessary
        if blocks and len(blocks[-1]) > 0:
            blocks[-1] = blocks[-1][:-1]

        # Return the decoded plaintext
        return ''.join(blocks)

    def __init__(self, zpe=False):
        """
        Initialize the COBSFramer.

        :param zpe: If ``True``, enables the zero-pair elimination
                    variant of the COBS algorithm.
        """

        super(COBSFramer, self).__init__()

        self.zpe = zpe

    def frameify(self, state, data):
        """Split data into a sequence of frames."""

        # Pull in any partially-processed data
        data = state.recv_buf + data

        # Loop over the data
        while data:
            frame, sep, rest = data.partition('\0')

            # Did we have a whole frame?
            if sep != '\0':
                break

            # OK, update the data...
            data = rest

            # Now, decode the frame and yield it
            try:
                yield self._decode(frame, self._tables[0])
            except FrameSwitch:
                break

        # Put any remaining data back into the buffer
        state.recv_buf = data

    def streamify(self, state, frame):
        """Prepare frame for output as a COBS-encoded stream."""

        # Get the encoding table
        enc_tab = self._tables[1][:]

        # Need the special un-trailed block length and code
        untrail_len, untrail_code = enc_tab.pop(0)

        # Set up a repository to receive the encoded blocks
        result = []

        # Break the frame into blocks
        blocks = frame.split('\0')

        # Now, walk the block list; done carefully because we need
        # look-ahead in some cases
        skip = False
        for i in range(len(blocks)):
            # Skip handled blocks
            if skip:
                skip = False
                continue

            blk = blocks[i]

            # Encode un-trailed blocks
            while len(blk) >= untrail_len - 1:
                result.append(untrail_code + blk[:untrail_len - 1])
                blk = blk[untrail_len - 1:]

            # Do we care about look-ahead?
            if (len(enc_tab) > 1 and i + 1 < len(blocks) and
                    blocks[i + 1] == '' and len(blk) <= 30):
                # Use the second encoder table
                tab = enc_tab[1]

                # Skip the following empty block
                skip = True
            else:
                # Use the regular encoder table
                tab = enc_tab[0]

            # Encode the block
            result.append(tab[len(blk) + 1] + blk)

        # Stitch together the result blocks
        return ''.join(result) + '\0'

    @property
    def _tables(self):
        """Helper to retrieve the decoding and encoding tables."""

        return self._get_tab_zpe() if self.zpe else self._get_tab()
