#!/usr/bin/env python3

import multiprocessing
import queue
import shutil
import subprocess
import threading
import time
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


class BaseTTS:
    BUFF_SIZE = 1024
    SAMPLE_SIZE = 2

    def __init__(self, cmd, lib_path=None, data_path=None, resources=None):
        self._CMD = cmd
        self._params = (lib_path, data_path, resources)
        self._wait = threading.Event()
        self._queue = queue.Queue()
        self._sample_rate = 24000
        self._format = 'wav'
        self._engine = None
        self._popen = None
        self._file = None
        self._wave = None
        self._work = True

    def _engine_init(self):
        self._engine = rhvoice_proxy.Engine(self._params[0])
        self._engine.init(self._speech_callback, self._sr_callback, self._params[2], self._params[1])

    def _popen_create(self):
        self._popen = subprocess.Popen(
            self._CMD.get(self._format),
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE
        )

    def _select_target(self):
        if self._format in self._CMD:
            self._popen_create()
            return self._popen.stdin
        else:
            self._file = FakeFile()
            return self._file

    def _start_stream(self):
        self._wave_close()
        if self._file:
            self._file = None
        if self._popen:
            self._popen.kill()
            self._popen = None

        self._wave = WaveWrite(self._select_target())
        self._wave.setnchannels(1)
        self._wave.setsampwidth(self.SAMPLE_SIZE)
        self._wave.setframerate(self._sample_rate)

    def _wave_close(self):
        if self._wave:
            self._wave.close()
            self._wave = None

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
        self._engine.set_voice(voice)
        self._engine.generate(text)
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
        self._engine_init()
        while True:
            data = self._queue.get()
            if data is None:
                break
            self._generate(*data)


class OneTTS(BaseTTS, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        BaseTTS.__init__(self, *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join()


class _InOut(threading.Thread):
    BUFF = 1024

    def __init__(self, in_, out_):
        super().__init__()
        self._in = in_
        self._out = out_
        self.start()

    def run(self):
        while True:
            chunk = self._in.read(self.BUFF)
            self._out.put_nowait(chunk)
            if not chunk:
                break


class ProcessTTS(BaseTTS, multiprocessing.Process):
    TIMEOUT = 1

    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self)
        BaseTTS.__init__(self, *args, **kwargs)
        self._wait = multiprocessing.Event()
        self._queue = multiprocessing.Queue()
        self._processing = multiprocessing.Event()
        self._reading = multiprocessing.Event()
        self._processing.set()
        self._reading.set()
        self._stream = multiprocessing.Queue()
        self._in_out = None
        self.start()

    def _clear_old(self):  # Удаляем старые данные, если есть
        if self._in_out:
            self._in_out.join()
        while self._stream.qsize():
            try:
                self._stream.get_nowait()
            except queue.Empty:
                break

    def _select_target(self):
        self._clear_old()
        if self._format in self._CMD:
            self._popen_create()
            self._in_out = _InOut(self._popen.stdout, self._stream)
            return self._popen.stdin
        else:
            self._file = FakeFile()
            self._in_out = _InOut(self._file, self._stream)
            return self._file

    def busy(self):
        return not (self._processing.is_set() and self._reading.is_set())

    def set_busy(self):
        self._processing.clear()
        self._reading.clear()

    def _clear_busy(self):
        self._reading.set()
        self._processing.set()

    def _generate(self, *args):
        try:
            super()._generate(*args)
        finally:
            # Wait while client reading data
            while not self._reading.is_set():
                current_size = self._stream.qsize()
                self._reading.wait(self.TIMEOUT)
                if current_size == self._stream.qsize():
                    # Don't reading data? Client disconnected - set process as free
                    break
            self._clear_busy()

    def _iter_me(self, buff):
        try:
            while True:
                chunk = self._stream.get()
                if not chunk:
                    break
                yield chunk
        finally:
            self._reading.set()

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join()


class MultiTTS:
    TIMEOUT = 30

    def __init__(self, count, *args, **kwargs):
        self._workers = tuple([ProcessTTS(*args, **kwargs) for _ in range(count)])
        self._lock = threading.Lock()
        self._work = True

    def say(self, text, voice='anna', format_='mp3', buff=1024):
        self._lock.acquire()
        end_time = time.perf_counter() + self.TIMEOUT
        try:
            while True:
                for worker in self._workers:
                    if not worker.busy():
                        worker.set_busy()
                        return worker.say(text, voice, format_, buff)
                time.sleep(0.05)
                if time.perf_counter() > end_time:
                    raise RuntimeError('Still busy')
        finally:
            self._lock.release()

    def join(self, *_):
        if not self._work:
            return
        self._work = False
        _ = [x.join() for x in self._workers]


def _test_engine(lib_path, data_path, resources):
    test = rhvoice_proxy.Engine(lib_path)
    test.init(data_path=data_path, resources=resources)
    api = rhvoice_proxy.__version__
    if api != test.version:
        print('Warning! API version ({}) different of library version ({})'.format(api, test.version))
    return {key for key in test.voices}


def TTS(cmd=None, lib_path=None, data_path=None, resources=None, threads=1):
    threads = threads if threads > 0 else 1
    cmd = cmd or _cmd_init()
    voices = _test_engine(lib_path, data_path, resources)
    if threads == 1:
        return OneTTS(cmd, lib_path, data_path, resources), voices
    else:
        return MultiTTS(threads, cmd, lib_path, data_path, resources), voices


def main():
    names = ['wav.wav', 'mp3.mp3', 'opus.ogg', 'wav.wav']
    text = 'Я умею сохранять свой голос в {}'
    voice = 'anna'
    w_time = time.time()
    (tts, _) = TTS()
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
