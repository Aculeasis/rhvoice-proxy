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


class FakeFile(queue.Queue):
    def __init__(self):
        super().__init__()
        self._pos = 0
        self._seeking = False
        self._open = True

    def seek(self, pos, *_):
        # Игнорируем попытки wave пропатчить хидер.
        self._seeking = pos != self._pos

    def tell(self, *_):
        return self._pos

    def write(self, data):
        writen = len(data)
        if writen and not self._seeking:
            self.put_nowait(data)
            self._pos += writen
        return writen

    def read(self, *_):
        if not self._open:
            return b''
        if self.qsize():
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
        self._processing = False
        self.start()

    def _popen_open(self):
        self._popen_close()
        self._popen = subprocess.Popen(
            self._CMD.get(self._format),
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE
        )

    def _file_open(self):
        self._file_close()
        self._file = FakeFile()

    def _wave_open(self):
        self._wave_close()
        self._file_open()
        self._wave = wave.Wave_write(self._file)
        self._wave.setnchannels(1)
        self._wave.setsampwidth(self.SAMPLE_SIZE)
        self._wave.setframerate(self._sample_rate)

    def _wave_close(self):
        if self._wave:
            self._wave.close()
            self._wave = None
        self._file_close()
        self._popen_close()

    def _file_close(self):
        if self._file:
            self._file.close()
            self._file = None

    def _popen_close(self):
        if self._popen:
            self._popen.kill()
            self._popen = None

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join(timeout)

    def _speech_callback(self, samples, count, *_):
        if not self._wave:
            self._wave_open()
            # TODO: Посчитать хидер самостоятельно и выкинуть wave
            # noinspection PyProtectedMember
            self._wave._write_header(0xFFFFFFF)  # Задаем 'бесконечную' длинну файла
            self._wave.writeframesraw(string_at(samples, count * self.SAMPLE_SIZE))
            if self._format in self._CMD:
                self._popen_open()
                self._in_out()
            self._wait.set()
        else:
            self._wave.writeframesraw(string_at(samples, count * self.SAMPLE_SIZE))
            if self._popen:
                self._in_out()
        return self._work

    def _in_out(self):
        data = self._file.read()
        if data:
            self._popen.stdin.write(data)
            return True
        return False

    def _sr_callback(self, rate, *_):
        self._sample_rate = rate
        return True

    @contextmanager
    def say(self, text, voice='anna', format_='mp3', buff=1024):
        if format_ != 'wav' and format_ not in self._CMD:
            raise RuntimeError('Unsupported format: {}'.format(format_))
        self._queue.put_nowait([text, voice, format_])
        self._wait.wait(3600)
        self._wait.clear()
        yield self._iter_me(buff)
        self._wave_close()

    def to_file(self, filename, text, voice='anna', format_='mp3'):
        with open(filename, 'wb') as fp:
            with self.say(text, voice, format_) as read:
                for chunk in read:
                    fp.write(chunk)

    def _iter_me(self, buff):
        while True:
            if self._popen:
                chunk = self._popen.stdout.read(buff)
            else:
                chunk = self._file.read()
            if not chunk:
                if self._processing:
                    continue
                else:
                    break
            yield chunk

    def _generate(self, text, voice, format_):
        self._format = format_
        synth_params = rhvoice_proxy.get_synth_params(voice)
        self._processing = True
        rhvoice_proxy.speak_generate(text, synth_params, self._engine)
        if self._wave:
            self._wave.close()
            self._wave = None
        self._file.end()

        if self._popen:
            while self._in_out():
                pass
            self._popen.stdin.close()
            try:
                self._popen.wait(5)
            except subprocess.TimeoutExpired:
                pass
        self._processing = False

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
