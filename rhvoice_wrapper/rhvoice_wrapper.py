#!/usr/bin/env python3

import multiprocessing
import os
import queue
import shutil
import subprocess
import threading
import time
import wave
from contextlib import contextmanager
from ctypes import string_at

try:
    from rhvoice_wrapper import rhvoice_proxy
except ImportError:
    import rhvoice_proxy


class _WaveWrite(wave.Wave_write):
    def _ensure_header_written(self, _):
        pass

    def _patchheader(self):
        pass


class _FakeFile(queue.Queue):
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


class _InOut(threading.Thread):
    BUFF = 1024

    def __init__(self, in_, out_):
        super().__init__()
        self._in = in_
        self._out = out_
        self.start()

    def run(self):
        while True:
            try:
                chunk = self._in.read(self.BUFF)
            except ValueError:
                chunk = b''
            self._out.put_nowait(chunk)
            if not chunk:
                break


class _AudioWorker:
    BUFF_SIZE = 1024
    SAMPLE_SIZE = 2

    def __init__(self, cmd, stream_):
        self._cmd = cmd
        self._stream = stream_
        self._popen = None
        self._file = None
        self._wave = None
        self._in_out = None

        self.qsize = self._stream.qsize
        self.get = self._stream.get

    def start_processing(self, format_, rate=24000):
        self._clear_stream()

        self._file = None
        self._popen = None
        self._in_out = None

        self._wave = _WaveWrite(self._select_target(format_))
        self._wave.setnchannels(1)
        self._wave.setsampwidth(self.SAMPLE_SIZE)
        self._wave.setframerate(rate)
        # noinspection PyProtectedMember
        self._wave._write_header(0xFFFFFFF)  # Задаем 'бесконечную' длину файла

    def processing(self, samples, count):
        self._wave.writeframesraw(string_at(samples, count * self.SAMPLE_SIZE))

    def end_processing(self):
        if self._wave:
            self._wave.close()
        if self._file:
            self._file.end()
        if self._popen:
            self._popen.stdin.close()
            self._popen.stderr.close()
            try:
                self._popen.wait(5)
            except subprocess.TimeoutExpired:
                pass
            self._popen.stdout.close()
            self._popen.kill()
        if self._in_out:
            self._in_out.join()

    def _clear_stream(self):
        while self._stream.qsize():
            try:
                self._stream.get_nowait()
            except queue.Empty:
                break

    def _create_popen(self, format_):
        self._popen = subprocess.Popen(
            self._cmd.get(format_),
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE
        )

    def _select_target(self, format_):
        if format_ in self._cmd:
            self._create_popen(format_)
            self._in_out = _InOut(self._popen.stdout, self._stream)
            return self._popen.stdin
        else:
            self._file = _FakeFile()
            self._in_out = _InOut(self._file, self._stream)
            return self._file


class _BaseTTS:
    def __init__(self, stream_, cmd, **kwargs):
        self._cmd = cmd
        self._kwargs = kwargs
        self._wait = threading.Event()
        self._queue = queue.Queue()
        self._format = 'wav'
        self._engine = None
        self._worker = _AudioWorker(cmd=self._cmd, stream_=stream_)
        self._work = True

    def _engine_init(self):
        self._engine = rhvoice_proxy.Engine(**self._kwargs)
        self._engine.init(self._speech_callback, self._sr_callback, **self._kwargs)

    def _speech_callback(self, samples, count, *_):
        self._worker.processing(samples, count)
        return self._work

    def _sr_callback(self, rate, *_):
        self._worker.start_processing(self._format, rate)
        self._wait.set()
        return True

    @contextmanager
    def say(self, text, voice='anna', format_='mp3', buff=1024):
        if format_ != 'wav' and format_ not in self._cmd:
            raise RuntimeError('Unsupported format: {}'.format(format_))
        self._queue.put_nowait((text, voice, format_))
        self._wait.wait(3600)
        self._wait.clear()
        yield self._iter_me(buff)

    def to_file(self, filename, text, voice='anna', format_='mp3'):
        with open(filename, 'wb') as fp:
            with self.say(text, voice, format_) as read:
                for chunk in read:
                    fp.write(chunk)

    def set_params(self, **kwargs):
        self._queue.put_nowait(kwargs)

    def _iter_me(self, buff):
        while True:
            chunk = self._worker.get()
            if not chunk:
                break
            yield chunk

    def _generate(self, text, voice, format_):
        self._format = format_
        self._engine.set_voice(voice)
        self._engine.generate(text)
        self._worker.end_processing()

    def run(self):
        self._engine_init()
        while True:
            data = self._queue.get()
            if data is None:
                break
            if isinstance(data, dict):
                self._engine.set_params(**data)
            else:
                self._generate(*data)


class OneTTS(_BaseTTS, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        _BaseTTS.__init__(self, queue.Queue(), *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join()


class ProcessTTS(_BaseTTS, multiprocessing.Process):
    TIMEOUT = 1

    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self)
        _BaseTTS.__init__(self, multiprocessing.Queue(), *args, **kwargs)
        self._wait = multiprocessing.Event()
        self._queue = multiprocessing.Queue()
        self._processing = multiprocessing.Event()
        self.reading = multiprocessing.Event()
        self._processing.set()
        self.reading.set()
        self.start()

    def busy(self):
        return not (self._processing.is_set() and self.reading.is_set())

    def set_busy(self):
        self._processing.clear()
        self.reading.clear()

    def _clear_busy(self):
        self.reading.set()
        self._processing.set()

    def _generate(self, *args):
        try:
            super()._generate(*args)
        finally:
            # Wait while client reading data
            while not self.reading.is_set():
                current_size = self._worker.qsize()
                self.reading.wait(self.TIMEOUT)
                if current_size == self._worker.qsize():
                    # Don't reading data? Client disconnected - set process as free
                    break
            self._clear_busy()

    def _iter_me(self, buff):
        try:
            for chunk in super()._iter_me(buff):
                yield chunk
        finally:
            self.reading.set()

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
        self._nowait = False

    def nowait(self, val: bool):
        self._nowait = val

    def to_file(self, filename, text, voice='anna', format_='mp3'):
        return self._caller().to_file(filename, text, voice, format_)

    def say(self, text, voice='anna', format_='mp3', buff=1024):
        return self._caller().say(text, voice, format_, buff)

    def _caller(self):
        self._lock.acquire()
        end_time = time.perf_counter() + self.TIMEOUT
        try:
            while True:
                for worker in self._workers:
                    if not worker.busy():
                        worker.set_busy()
                        if self._nowait:
                            worker.reading.set()
                        return worker
                time.sleep(0.05)
                if time.perf_counter() > end_time:
                    raise RuntimeError('Still busy')
        finally:
            self._lock.release()

    def set_params(self, **kwargs):
        for worker in self._workers:
            worker.set_params(**kwargs)

    def join(self, *_):
        if not self._work:
            return
        self._work = False
        _ = [x.join() for x in self._workers]


class TTS:
    def __init__(self, **kwargs):
        envs = self._get_environs(kwargs)

        self._threads = self._prepare_threads(envs.pop('threads', None))
        self._process = envs.pop('force_process', False) or self._threads > 1

        self._cmd = self._get_cmd(envs.pop('lame_path', None), envs.pop('opus_path', None))
        self._formats = tuple(['wav'] + [key for key in self._cmd])

        self._api = rhvoice_proxy.__version__

        test = rhvoice_proxy.Engine(**envs)
        self._version = test.version
        if self._api != self._version:
            print('Warning! API version ({}) different of library version ({})'.format(self._api, self._version))
        test.init(**envs)
        self._voices = test.voices
        del test

        if self._process:
            tts = MultiTTS(self._threads, self._cmd, **envs)
            self._burn = tts.nowait
        else:
            tts = OneTTS(self._cmd, **envs)
            self._burn = None

        self.say = tts.say
        self.to_file = tts.to_file
        self.set_params = tts.set_params
        self.join = tts.join

    @property
    def formats(self):
        return self._formats

    @property
    def thread_count(self):
        return self._threads

    @property
    def process(self):
        return self._process

    @property
    def voices(self):
        return tuple([key for key in self._voices])

    @property
    def api_version(self):
        return self._api

    @property
    def lib_version(self):
        return self._version

    @property
    def voices_info(self):
        return self._voices

    @property
    def cmd(self):
        return self._cmd

    @staticmethod
    def _get_environs(kwargs):
        names = ['lib_path', 'data_path', 'resources', 'lame_path', 'opus_path', 'threads']
        variables = ['RHVOICELIBPATH', 'RHVOICEDATAPATH', 'RHVOICERESOURCES', 'LAMEPATH', 'OPUSENCPATH', 'THREADED']
        result = {}
        for idx in range(len(variables)):
            if variables[idx] in os.environ:
                result[names[idx]] = os.environ[variables[idx]]
            if names[idx] in kwargs:
                result[names[idx]] = kwargs[names[idx]]
        return result

    @staticmethod
    def _prepare_threads(threads):
        if threads is None:
            return 1
        if isinstance(threads, bool):
            if threads:
                return multiprocessing.cpu_count()
            else:
                return 1
        try:
            threads = int(threads)
        except ValueError:
            threads = 1
        else:
            threads = threads if threads > 0 else 1
        return threads

    @staticmethod
    def _get_cmd(lame, opus):
        base_cmd = {
            'mp3': [[lame or 'lame', '-htv', '--silent', '-', '-'], 'lame'],
            'opus': [[opus or 'opusenc', '--quiet', '--discard-comments', '--ignorelength', '-', '-'], 'opus-tools']
        }
        cmd = {}
        for key, val in base_cmd.items():
            if shutil.which(val[0][0]):
                cmd[key] = val[0]
            else:
                print('Disable {} support - {} not found. Use apt install {}'.format(key, val[0][0], val[1]))
        return cmd

    def benchmarks(self):
        # PPS - Phrases Per Second
        # i7-8700k: 80.3 PPS
        # OrangePi Prime: 4.4 PPS
        if self._burn is None:
            return 'Only for multiprocessing mode'
        self._burn(True)
        text = 'Так себе, вызовы сэй будут блокировать выполнение'
        for _ in range(self.thread_count):
            with self.say(text, format_='wav') as fp:
                next(fp, None)
        time.sleep(2)
        yield 'Start...'
        count = 0
        test_time = 30
        end_time = time.perf_counter() + test_time
        try:
            while True:
                with self.say(text, format_='wav') as fp:
                    next(fp, None)
                count += 1
                if end_time < time.perf_counter():
                    work_time = time.perf_counter() - (end_time - test_time)
                    pps = count / work_time
                    yield 'PPS: {:.4f} (run {:.3f} sec)'.format(pps, work_time)
                    end_time = time.perf_counter() + test_time
                    count = 0
        finally:
            self._burn(False)


def main():
    tts = TTS(threads=int(multiprocessing.cpu_count() * 1.5))
    print('Lib version: {}'.format(tts.lib_version))
    print('Threads: {}'.format(tts.thread_count))
    print('Formats: {}'.format(tts.formats))
    print('Voices: {}'.format(tts.voices))
    max_ = 5
    for result in tts.benchmarks():
        print(result)
        max_ -= 1
        if not max_:
            break
    tts.join()


if __name__ == '__main__':
    main()
