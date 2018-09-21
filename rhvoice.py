#!/usr/bin/env python3

import queue
import shutil
import subprocess
import threading
import wave
from contextlib import contextmanager
from ctypes import string_at

if __name__ == '__main__':
    import rhvoice_proxy
else:
    from rhvoice_proxy import rhvoice_proxy


class WaveWrite(wave.Wave_write):
    def _ensure_header_written(self, _):
        pass

    def _patchheader(self):
        pass


class FakeFile(queue.Queue):
    def __init__(self):
        super().__init__()
        self._open = True

    @staticmethod
    def tell():
        return 0

    def write(self, data):
        if data:
            self.put_nowait(data)

    def read(self, *_):
        if not self._open:
            return b''
        if self.qsize() > 1:
            data = b''
            while self.qsize():
                data_p = self.get()
                data += data_p
                if not data_p:
                    self._open = False
        else:
            data = self.get()
            if not data:
                self._open = False
        return data

    def end(self):
        if self._open:
            self.put_nowait(b'')

    def close(self):
        pass

    def flush(self):
        pass


def _cmd_init():
    base_cmd = {
        'mp3': [['lame', '-htv', '--silent', '-', '-'], 'lame', 'lame'],
        'opus': [['opusenc', '--quiet', '--discard-comments', '--ignorelength', '-', '-'], 'opusenc', 'opus-tools']
    }
    cmd = {}
    for key, val in base_cmd.items():
        if shutil.which(val[1]):
            cmd[key] = val[0]
        else:
            print('Disable {} support - {} not found. Use apt install {}'.format(key, val[1], val[2]))
    return cmd


class TTS(threading.Thread):
    BUFF_SIZE = 1024
    SAMPLE_SIZE = 2

    def __init__(self, lib_path=None, data_path=None, resources=None):
        super().__init__()
        self._CMD = _cmd_init()
        self._wait = threading.Event()
        self._queue = queue.Queue()
        self._sample_rate = 24000
        self._format = 'wav'
        rhvoice_proxy.load_tts_library(lib_path)
        api = rhvoice_proxy.__version__
        ver = rhvoice_proxy.get_rhvoice_version()
        if api != ver:
            print('Warning! API version ({}) different of library version ({})'.format(api, ver))
        self._engine = rhvoice_proxy.get_engine(self._speech_callback, self._sr_callback, resources, data_path)
        self._popen = None
        self._file = None
        self._wave = None
        self._work = True
        self.start()

    def _popen_create(self):
        self._popen = subprocess.Popen(
            self._CMD.get(self._format),
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE
        )

    def _start_stream(self):
        self._wave_close()
        if self._file:
            self._file = None
        if self._popen:
            self._popen.kill()
            self._popen = None
        if self._format in self._CMD:
            self._popen_create()
            target = self._popen.stdin
        else:
            self._file = FakeFile()
            target = self._file

        self._wave = WaveWrite(target)
        self._wave.setnchannels(1)
        self._wave.setsampwidth(self.SAMPLE_SIZE)
        self._wave.setframerate(self._sample_rate)

    def _wave_close(self):
        if self._wave:
            self._wave.close()
            self._wave = None

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join(timeout)

    def _speech_callback(self, samples, count, *_):
        self._wave.writeframesraw(string_at(samples, count * self.SAMPLE_SIZE))
        return self._work

    def _sr_callback(self, rate, *_):
        self._sample_rate = rate

        self._start_stream()
        # noinspection PyProtectedMember
        self._wave._write_header(0xFFFFFFF)  # Задаем 'бесконечную' длину файла
        self._wait.set()
        return True

    @contextmanager
    def say(self, text, voice='anna', format_='mp3', buff=1024):
        if format_ != 'wav' and format_ not in self._CMD:
            raise RuntimeError('Unsupported format: {}'.format(format_))
        self._queue.put_nowait([text, voice, format_])
        self._wait.wait(3600)
        self._wait.clear()
        yield self._iter_me(buff)

    def to_file(self, filename, text, voice='anna', format_='mp3'):
        with open(filename, 'wb') as fp:
            with self.say(text, voice, format_) as read:
                for chunk in read:
                    fp.write(chunk)

    def _iter_me(self, buff):
        while True:
            chunk = self._popen.stdout.read(buff) if self._popen else self._file.read()
            if not chunk:
                break
            yield chunk

    def _generate(self, text, voice, format_):
        self._format = format_
        rhvoice_proxy.speak_generate(text, rhvoice_proxy.get_synth_params(voice), self._engine)
        self._wave_close()
        if self._file:
            self._file.end()
        if self._popen:
            self._popen.stdin.close()
            try:
                self._popen.wait(5)
            except subprocess.TimeoutExpired:
                pass

    def run(self):
        while True:
            data = self._queue.get()
            if data is None:
                break
            self._generate(*data)


def main():
    import time
    names = ['wav.wav', 'mp3.mp3', 'opus.ogg', 'wav.wav']
    text = 'Я умею сохранять свой голос в {}'
    voice = 'anna'
    w_time = time.time()
    tts = TTS()
    print('Init time: {}'.format(time.time() - w_time))
    print()
    for name in names:
        format_ = name.split('.', 1)[0]
        w_time = time.time()
        tts.to_file(name, text.format(format_), voice, format_)
        w_time = time.time() - w_time
        print('File {} created in {} sec.'.format(name, w_time))


if __name__ == '__main__':
    main()
