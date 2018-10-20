#!/usr/bin/env python3

import time
import wave
from ctypes import c_short, sizeof, string_at


class SpeechCallback(object):
    sample_size = sizeof(c_short)

    def __init__(self):
        self._sample_rate = 24000

    def __call__(self, samples, count, user_data):
        """Should return False to stop synthesis"""
        return True

    def set_sample_rate(self, rate, *_):
        self._sample_rate = rate
        return True


class DebugCallback(SpeechCallback):
    def __init__(self):
        super().__init__()
        self.counter = 0
        self.datasize = 0
        self.starttime = time.clock()

    def __call__(self, samples, count, user_data):
        self.counter += 1
        size = count * self.sample_size
        self.datasize += size
        kbps = self.datasize / (time.clock() - self.starttime) / 1024
        self.debug(count, size, kbps)
        return True

    def debug(self, count, size, kbps):
        print("speech callback %s time(s) samples: %s, size: %s, %.2f kBps" % (self.counter, count, size, kbps))


class WaveWriteCallback(SpeechCallback):
    """ Callback that writes sound to wave file. """

    def __init__(self):
        super().__init__()
        self.file = None
        self.filename = 'test.wav'

    def set(self, filename):
        self.filename = filename
        self.close()

    def _open(self):
        if self.file:
            self.file.close()
        self.file = wave.open(self.filename, 'wb')
        self.file.setnchannels(1)
        self.file.setsampwidth(self.sample_size)
        self.file.setframerate(self._sample_rate)

    def close(self):
        if self.file:
            self.file.close()
            self.file = None

    def __call__(self, samples, count, user_data):
        """Should return False to stop synthesis"""
        if not self.file:
            self._open()
        self.file.writeframes(string_at(samples, count * self.sample_size))
        return True
