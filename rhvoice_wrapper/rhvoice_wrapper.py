#!/usr/bin/env python3

import multiprocessing
import os
import platform
import queue
import shutil
import subprocess
import threading
import time
import wave
from collections.abc import Iterable
from contextlib import contextmanager
from ctypes import string_at

from rhvoice_wrapper import rhvoice_proxy


def prepare_synthesis_params(old: dict, data: dict):
    def _set():
        if key in old and old[key] != val:
            old[key] = val
            return True
        return False

    adv = {'punctuation_mode': 3, 'capitals_mode': 4}
    change = False
    for key, val in data.items():
        if key in adv:
            if isinstance(val, int) and 0 <= val <= adv[key]:
                change |= _set()
        elif isinstance(val, (int, float)) and -2 <= val <= 2.5:
            change |= _set()
    return change


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
    POPEN_TIMEOUT = 10
    JOIN_TIMEOUT = 10

    def __init__(self, cmd, stream_):
        self._cmd = cmd
        self._stream = stream_
        self._popen = None
        self._file = None
        self._wave = None
        self._in_out = None
        self._starting = False

        self.__empty = self._stream.empty
        if platform.system().lower() == 'darwin':
            # https://docs.python.org/3/library/multiprocessing.html?highlight=process#multiprocessing.Queue.qsize
            self.qsize = self.__qsize_osx
        else:
            self.qsize = self._stream.qsize
        self.get = self._stream.get

    def __qsize_osx(self):
        return 0 if self.__empty() else 1

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
        self._starting = True

    def processing(self, samples, count):
        self._wave.writeframesraw(string_at(samples, count * self.SAMPLE_SIZE))

    def end_processing(self):
        if not self._starting:
            # Генерации не было, надо отпустить клиента
            self._stream.put_nowait(b'')
            return False
        if self._wave:
            self._wave.close()
        if self._file:
            self._file.end()
        if self._popen:
            self._popen.stdin.close()
            try:
                self._popen.wait(self.POPEN_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
        if self._in_out:
            self._in_out.join(timeout=self.JOIN_TIMEOUT)
        if self._popen:
            self._popen.stdout.close()
            self._popen.kill()
        self._starting = False
        return True

    def _clear_stream(self):
        while self.qsize():
            try:
                self._stream.get_nowait()
            except queue.Empty:
                break

    def _create_popen(self, format_):
        self._popen = subprocess.Popen(
            self._cmd.get(format_),
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
    RELEASE_TIMEOUT = 3

    def __init__(self, stream_, cmd, **kwargs):
        self._cmd = cmd
        self._kwargs = kwargs.copy()
        self._synthesis_param = rhvoice_proxy.Engine.SYNTHESIS_SET.copy()  # Current params
        self._lib_path = {} if 'lib_path' not in self._kwargs else {'lib_path': self._kwargs.pop('lib_path')}
        self._wait = threading.Event()
        self._queue = queue.Queue()
        self._format = 'wav'
        self._engine = None
        self._worker = _AudioWorker(cmd=self._cmd, stream_=stream_)
        self._work = True
        self._client_here = threading.Event()
        self._client_here.set()
        self._generator_work = threading.Event()
        self._generator_work.set()
        self._still_processing = False

    def _engine_init(self):
        self._engine = rhvoice_proxy.Engine(**self._lib_path)
        self._engine.init(self._speech_callback, self._sr_callback, **self._kwargs)

    def _speech_callback(self, samples, count, *_):
        self._worker.processing(samples, count)
        return not self._client_here.is_set() and self._work

    def _sr_callback(self, rate, *_):
        if not self._still_processing:
            self._still_processing = True
            self._worker.start_processing(self._format, rate)
            self._wait.set()
        return True

    def busy(self):
        return not (self._client_here.is_set() and self._generator_work.is_set())

    def _release_busy(self):
        # Wait while client reading data
        while not self._client_here.is_set():
            current_size = self._worker.qsize()
            self._client_here.wait(self.RELEASE_TIMEOUT)
            if current_size == self._worker.qsize():
                # Don't reading data? Client disconnected - set process as free
                break
        self._client_here.set()
        self._generator_work.set()

    def _client_request(self, text, voice, format_, sets):
        if format_ != 'wav' and format_ not in self._cmd:
            raise RuntimeError('Unsupported format: {}'.format(format_))
        if sets is not None and not isinstance(sets, dict):
            RuntimeError('Sets must be dict or None')
        self._queue.put_nowait((text, voice, format_, sets))
        self._wait.wait(3600)
        self._wait.clear()

    @contextmanager
    def say(self, text, voice='anna', format_='mp3', buff=1024, sets=None):
        self._client_here.clear()
        try:
            self._client_request(text, voice, format_, sets)
            yield self._iter_me(buff)
        finally:
            self._client_here.set()

    def to_file(self, filename, text, voice='anna', format_='mp3', sets=None):
        self._client_here.clear()
        try:
            with open(filename, 'wb') as fp:
                self._client_request(text, voice, format_, sets)
                for chunk in self._iter_me():
                    fp.write(chunk)
        finally:
            self._client_here.set()

    def set_params(self, **kwargs):
        self._queue.put_nowait(kwargs)

    def _iter_me(self, _=None):
        while True:
            chunk = self._worker.get()
            if not chunk:
                break
            yield chunk

    def _generate(self, text, voice, format_, sets):
        self._generator_work.clear()
        rollback = False
        if sets:
            new_params = self._synthesis_param.copy()
            rollback = prepare_synthesis_params(new_params, sets)
            if rollback:
                self._engine.set_params(**new_params)
        self._format = format_
        self._engine.set_voice(voice)
        try:
            if isinstance(text, str):
                self._engine.generate(text)
            elif isinstance(text, Iterable):
                for chunk in text:
                    self._engine.generate(chunk)
        except RuntimeError:
            pass
        self._still_processing = False
        if not self._worker.end_processing():
            self._wait.set()
        if rollback:
            self._engine.set_params(**self._synthesis_param)
        self._release_busy()

    def run(self):
        self._engine_init()
        while self._work:
            data = self._queue.get()
            if data is None:
                break
            if isinstance(data, dict):
                self._synthesis_param = data
                self._engine.set_params(**data)
            else:
                self._generate(*data)


class ThreadTTS(_BaseTTS, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        _BaseTTS.__init__(self, queue.Queue(), *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join()


class ProcessTTS(_BaseTTS, multiprocessing.Process):
    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self)
        _BaseTTS.__init__(self, multiprocessing.Queue(), *args, **kwargs)
        self._wait = multiprocessing.Event()
        self._queue = multiprocessing.Queue()
        self._client_here = multiprocessing.Event()
        self._client_here.set()
        self._generator_work = multiprocessing.Event()
        self._generator_work.set()
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._queue.put_nowait(None)
        super().join()


class MultiTTS:
    TIMEOUT = 30

    def __init__(self, count, processes, *args, **kwargs):
        worker = ProcessTTS if processes else ThreadTTS
        self._workers = tuple([worker(*args, **kwargs) for _ in range(count)])
        self._lock = threading.Lock()
        self._work = True

    def to_file(self, filename, text, voice='anna', format_='mp3', sets=None):
        return self._caller().to_file(filename, text, voice, format_, sets)

    def say(self, text, voice='anna', format_='mp3', buff=1024, sets=None):
        return self._caller().say(text, voice, format_, buff, sets)

    def _caller(self):
        self._lock.acquire()
        end_time = time.perf_counter() + self.TIMEOUT
        try:
            while True:
                for worker in self._workers:
                    if not worker.busy():
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
        [x.join() for x in self._workers]


class TTS:
    def __init__(self, **kwargs):
        def dummy(*_):
            return True

        envs = self._get_environs(kwargs)

        self._threads = self._prepare_threads(envs.pop('threads', None))
        self._process = self._prepare_process(envs.pop('force_process', None), self._threads)
        self._cmd = self._get_cmd(
            envs.pop('lame_path', None),
            envs.pop('opus_path', None),
            envs.pop('flac_path', None),
        )
        self._formats = tuple(['wav'] + [key for key in self._cmd])

        self._api = rhvoice_proxy.__version__

        envs2 = envs.copy()
        lib_path = {} if 'lib_path' not in envs2 else {'lib_path': envs2.pop('lib_path')}
        test = rhvoice_proxy.Engine(**lib_path)
        self._version = test.version
        if self._api != self._version:
            print('Warning! API version ({}) different of library version ({})'.format(self._api, self._version))
        test.init(play_speech_cb=dummy, set_sample_rate_cb=dummy, **envs2)
        self._voices = test.voices
        self._synth_set = test.SYNTHESIS_SET.copy()
        del test

        tts = MultiTTS(self._threads, self._process, self._cmd, **envs)

        self.say = tts.say
        self.to_file = tts.to_file
        self.__set_params = tts.set_params
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

    def set_params(self, **kwargs):
        if prepare_synthesis_params(self._synth_set, kwargs):
            self.__set_params(**self._synth_set)
            return True
        else:
            return False

    def get_params(self, param=None):
        if param is None:
            return self._synth_set.copy()
        return self._synth_set.get(param)

    @staticmethod
    def _get_environs(kwargs):
        params = {
            'lib_path': 'RHVOICELIBPATH',
            'data_path': 'RHVOICEDATAPATH',
            'resources': 'RHVOICERESOURCES',
            'lame_path': 'LAMEPATH',
            'opus_path': 'OPUSENCPATH',
            'flac_path': 'FLACPATH',
            'threads': 'THREADED',
            'force_process': 'PROCESSES_MODE'
        }
        result = {}
        for key, val in params.items():
            if key in kwargs:
                result[key] = kwargs[key]
            elif val in os.environ:
                result[key] = os.environ[val]
        return result

    @staticmethod
    def _prepare_process(force_process, threads):
        if isinstance(force_process, str):
            force_process = force_process.lower()
            if force_process in ['true', 'yes', 'enable']:
                return True
            elif force_process in ['false', 'no', 'disable']:
                return False
        elif isinstance(force_process, bool):
            return force_process
        return threads > 1

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
    def _get_cmd(lame, opus, flac):
        base_cmd = {
            'mp3': [[lame or 'lame', '-htv', '--silent', '-', '-'], 'lame'],
            'opus': [[opus or'opusenc', '--quiet', '--discard-comments', '--ignorelength', '-', '-'], 'opus-tools'],
            'flac': [[flac or 'flac', '--totally-silent', '--best', '--stdout', '--ignore-chunk-sizes', '-'], 'flac'],
        }
        cmd = {}
        for key, val in base_cmd.items():
            if shutil.which(val[0][0]):
                cmd[key] = val[0]
            else:
                print('Disable {} support - {} not found. Use apt install {}'.format(key, val[0][0], val[1]))
        return cmd
