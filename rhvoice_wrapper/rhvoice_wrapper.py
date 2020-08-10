#!/usr/bin/env python3

import multiprocessing
import os
import queue
import shutil
import subprocess
import threading
import wave
from collections.abc import Iterable
from contextlib import contextmanager
from ctypes import string_at
from io import BytesIO

from rhvoice_wrapper import rhvoice_proxy

try:
    multiprocessing.Queue().qsize()
except NotImplementedError:
    OSX_FIX = True
else:
    OSX_FIX = False

_unset = object()
DEFAULT_CHUNK_SIZE = 1024 * 4
DEFAULT_FORMAT = 'wav'


class _WaveWrite(wave.Wave_write):
    def _ensure_header_written(self, _):
        pass

    def _patchheader(self):
        pass

    def write_header(self, init_length=0xFFFFFFF):   # Задаем 'бесконечную' длину файла
        self._write_header(init_length)


class _InOut(threading.Thread):
    def __init__(self, in_, out_, chunk_size):
        super().__init__()
        self._in = in_
        self._out = out_
        self._chunk_size = chunk_size
        self.start()

    def run(self):
        while True:
            try:
                chunk = self._in.read(self._chunk_size)
            except ValueError:
                break
            if not chunk:
                break
            self._out.put(chunk)


class _Pipe:
    # Pipe fasted for Process
    # Queue fasted for Thread (i don't know why)
    def __init__(self, is_multiprocessing=False):
        self._pipe = multiprocessing.Pipe(False) if is_multiprocessing else queue.Queue()
        if is_multiprocessing:
            self.get = self._pipe[0].recv
            self.put = self._pipe[1].send
        else:
            self.get = self._pipe.get
            self.put = self._pipe.put_nowait


class _StreamPipe:
    def __init__(self, is_multiprocessing=False):
        self._pipe = multiprocessing.Queue() if is_multiprocessing else queue.Queue()
        self.get = self._pipe.get
        self.put = self._pipe.put_nowait
        self.write = self.put
        if is_multiprocessing and OSX_FIX:
            self.qsize = self._osx_qsize
        else:
            self.qsize = self._pipe.qsize

    def _osx_qsize(self) -> int:
        return int(not self._pipe.empty())

    def clear(self):
        while self.qsize():
            try:
                self._pipe.get_nowait()
            except queue.Empty:
                pass

    def close(self):
        pass

    def flush(self):
        pass

    @staticmethod
    def tell():
        return 0


class _AudioWorker:
    SAMPLE_WIDTH = 2

    def __init__(self, cmd: dict, pipe: _StreamPipe):
        self._cmd = cmd
        self._stream = pipe
        self._wave = None
        self._starting = False

        self.get = self._stream.get
        self.qsize = self._stream.qsize

    def start_processing(self, format_, chunk_size, rate=24000):
        raise NotImplementedError

    def processing(self, samples, count):
        raise NotImplementedError

    def end_processing(self):
        raise NotImplementedError


class _AudioWorkerStream(_AudioWorker):
    POPEN_TIMEOUT = 10
    JOIN_TIMEOUT = 10

    def __init__(self, cmd: dict, pipe: _StreamPipe):
        super().__init__(cmd, pipe)
        self._in_out, self._popen = None, None

    def start_processing(self, format_, chunk_size, rate=24000):
        self._stream.clear()

        self._wave, self._in_out, self._popen = None, None, None

        if format_ != 'pcm':
            self._wave = _WaveWrite(self._select_target(format_, chunk_size))
            self._wave.setnchannels(1)
            self._wave.setsampwidth(self.SAMPLE_WIDTH)
            self._wave.setframerate(rate)
            self._wave.write_header()
        self._starting = True

    def processing(self, samples, count):
        data = string_at(samples, count * self.SAMPLE_WIDTH)
        if self._wave:
            self._wave.writeframesraw(data)
        else:
            self._stream.put(data)

    def end_processing(self):
        if not self._starting:
            # Генерации не было, надо отпустить клиента
            self._stream.put(b'')
            return False
        if self._wave:
            self._wave.close()
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
        self._stream.put(b'')
        self._starting = False
        return True

    def _create_popen(self, format_):
        self._popen = subprocess.Popen(
            self._cmd.get(format_),
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE
        )

    def _select_target(self, format_, chunk_size):
        if format_ in self._cmd:
            self._create_popen(format_)
            self._in_out = _InOut(self._popen.stdout, self._stream, chunk_size)
            return self._popen.stdin
        else:
            return self._stream


class _AudioWorkerBlocked(_AudioWorker):
    def __init__(self, cmd: dict, pipe: _StreamPipe):
        super().__init__(cmd, pipe)
        self._file, self._format = None, None

    def start_processing(self, format_, chunk_size, rate=24000):
        self._stream.clear()

        self._wave, self._format, self._file = None, format_, BytesIO()

        if self._format != 'pcm':
            self._wave = wave.Wave_write(self._file)
            self._wave.setnchannels(1)
            self._wave.setsampwidth(self.SAMPLE_WIDTH)
            self._wave.setframerate(rate)
        self._starting = True

    def processing(self, samples, count):
        data = string_at(samples, count * self.SAMPLE_WIDTH)
        if self._wave:
            self._wave.writeframesraw(data)
        else:
            self._file.write(data)

    def end_processing(self):
        if not self._starting:
            # Генерации не было, надо отпустить клиента
            self._stream.put(b'')
            return False
        if self._wave:
            self._wave.close()
        else:
            self._file.close()
        if self._format in self._cmd:
            try:
                self._stream.put(subprocess.check_output(self._cmd[self._format], input=self._file.getvalue()))
            except subprocess.CalledProcessError:
                pass
        else:
            self._stream.put(self._file.getvalue())
        self._file = None
        self._stream.put(b'')
        self._starting = False
        return True


class _BaseTTS:
    RELEASE_TIMEOUT = 3

    def __init__(self, is_multiprocessing: bool, free, cmd: dict, allow_formats: frozenset, **kwargs):
        _event = multiprocessing.Event if is_multiprocessing else threading.Event
        self._free = free
        self._allow_formats = allow_formats
        self._kwargs = kwargs.copy()
        self._is_stream = self._kwargs.pop('stream')
        self._lib_path = {} if 'lib_path' not in self._kwargs else {'lib_path': self._kwargs.pop('lib_path')}
        self._wait = _event()
        self._pipe = _Pipe(is_multiprocessing=is_multiprocessing)
        self._format = DEFAULT_FORMAT
        self._chunk_size = DEFAULT_CHUNK_SIZE
        self._engine = None
        _worker = _AudioWorkerStream if self._is_stream else _AudioWorkerBlocked
        self._worker = _worker(cmd=cmd, pipe=_StreamPipe(is_multiprocessing=is_multiprocessing))
        self._work = True
        self._client_here = _event()
        self._client_here.set()
        self._generator_work = _event()
        self._generator_work.set()
        self._still_processing = False

    def _engine_init(self):
        self._engine = rhvoice_proxy.Engine(**self._lib_path)
        self._engine.init(self._speech_callback, self._sr_callback, **self._kwargs)

    def _engine_destroy(self):
        self._engine.exterminate()
        self._engine = None

    def _speech_callback(self, samples, count, *_):
        self._worker.processing(samples, count)
        return not self._client_here.is_set() and self._work

    def _sr_callback(self, rate, *_):
        if not self._still_processing:
            self._still_processing = True
            self._worker.start_processing(self._format, self._chunk_size, rate)
            self._wait.set()
        return True

    def client_here(self):
        self._client_here.clear()

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
        self._free.set()

    def _client_request(self, text, voice, format_, chunk_size, sets):
        if format_ not in self._allow_formats:
            raise RuntimeError('Unsupported format: {}'.format(format_))
        sets = sets or {}
        if not isinstance(sets, dict):
            RuntimeError('Sets must be dict or None')
        if voice:
            sets['voice_profile'] = voice
        self._pipe.put((text, format_, chunk_size, sets))
        self._wait.wait(3600)
        self._wait.clear()

    @contextmanager
    def say(self, text, voice, format_, buff, sets):
        try:
            format_ = format_ or DEFAULT_FORMAT
            buff = buff if self._is_stream else None
            self._client_request(text, voice, format_, buff, sets)
            yield self._iter_me_splitting(buff) if format_ in ['pcm', 'wav'] and buff else self._iter_me()
        finally:
            self._client_here.set()

    def get(self, text, voice, format_, sets) -> bytes:
        format_ = format_ or DEFAULT_FORMAT
        try:
            self._client_request(text, voice, format_, DEFAULT_CHUNK_SIZE, sets)
            return b''.join(self._iter_me())
        finally:
            self._client_here.set()

    def to_file(self, filename, text, voice, format_, sets):
        try:
            with open(filename, 'wb') as fp:
                format_ = format_ or DEFAULT_FORMAT
                self._client_request(text, voice, format_, DEFAULT_CHUNK_SIZE, sets)
                for chunk in self._iter_me():
                    fp.write(chunk)
        finally:
            self._client_here.set()

    def set_params(self, **kwargs):
        self._pipe.put(kwargs)

    def _iter_me(self):
        while True:
            chunk = self._worker.get()
            if not chunk:
                break
            yield chunk

    def _iter_me_splitting(self, chunk_size):
        buffer = b''
        while True:
            chunk = self._worker.get()
            if not chunk:
                break
            buffer += chunk
            size = len(buffer)
            while size >= chunk_size:
                yield buffer[:chunk_size]
                buffer = buffer[chunk_size:]
                size -= chunk_size
        if buffer:
            yield buffer

    def _get_temporary_params(self, sets):
        try:
            return self._engine.params.copy_with(sets)
        except Exception as e:
            print('sets error: {}'.format(e))
        return None

    def _generate(self, text, format_, chunk_size, sets):
        self._generator_work.clear()
        self._format = format_
        self._chunk_size = chunk_size or DEFAULT_CHUNK_SIZE
        params = self._get_temporary_params(sets) if sets else None
        try:
            if isinstance(text, str):
                self._engine.generate(text=text, params=params)
            elif isinstance(text, Iterable):
                for chunk in text:
                    self._engine.generate(chunk, params=params)
        except RuntimeError:
            pass
        self._still_processing = False
        if not self._worker.end_processing():
            self._wait.set()
        self._release_busy()

    def run(self):
        self._engine_init()
        try:
            while self._work:
                data = self._pipe.get()
                if data is None:
                    break
                if isinstance(data, dict):
                    self._engine.set_params(**data)
                else:
                    self._generate(*data)
        finally:
            self._engine_destroy()

    def stop(self):
        if self._work:
            self._work = False
            self._pipe.put(None)


class ThreadTTS(_BaseTTS, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        _BaseTTS.__init__(self, False, *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self.stop()
        super().join()


class ProcessTTS(_BaseTTS, multiprocessing.Process):
    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self)
        _BaseTTS.__init__(self, True, *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self.stop()
        super().join()


class MultiTTS:
    TIMEOUT = 30

    def __init__(self, count, processes, *args, **kwargs):
        if processes:
            worker = ProcessTTS
            self._free = multiprocessing.Event()
        else:
            worker = ThreadTTS
            self._free = threading.Event()
        self._workers = tuple([worker(self._free, *args, **kwargs) for _ in range(count)])
        self._lock = threading.Lock()
        self._work = True

    def to_file(self, filename: str, text: str, voice=None, format_=None, sets=None):
        """Generate and save audio in a file"""
        return self._caller().to_file(filename, text, voice, format_, sets)

    def say(self, text: str, voice=None, format_=None, buff=DEFAULT_CHUNK_SIZE, sets=None):
        """
        Starting audio generation and returned it chunk by chunk
        with tts.say(*args, **kwargs) as gen:
            print('chunks count: ', len([print('new chunk, len: ', len(chunk)) for chunk in gen]))
        """
        return self._caller().say(text, voice, format_, buff, sets)

    def get(self, text: str, voice=None, format_=None, sets=None) -> bytes:
        """Generate and returned audio as bytes"""
        return self._caller().get(text, voice, format_, sets)

    def _caller(self):
        with self._lock:
            while True:
                self._free.clear()
                for worker in self._workers:
                    if not worker.busy():
                        worker.client_here()
                        return worker
                if not self._free.wait(self.TIMEOUT):
                    raise RuntimeError('Still busy')

    def set_params(self, **kwargs):
        for worker in self._workers:
            worker.set_params(**kwargs)

    def join(self, *_):
        if not self._work:
            return
        self._work = False
        [x.stop() for x in self._workers]
        [x.join() for x in self._workers]


class TTS(MultiTTS):
    PARAMS = {
        'threads': 'THREADED',
        'force_process': 'PROCESSES_MODE',
        'lib_path': 'RHVOICELIBPATH',
        'data_path': 'RHVOICEDATAPATH',
        'resources': 'RHVOICERESOURCES',
        'lame_path': 'LAMEPATH',
        'opus_path': 'OPUSENCPATH',
        'flac_path': 'FLACPATH',
        'quiet': 'QUIET',
        'config_path': 'RHVOICECONFIGPATH',
        'stream': 'RHVOICESTREAM',
    }

    def __init__(self, threads=_unset, force_process=_unset,
                 lib_path=_unset, data_path=_unset, resources=_unset,
                 lame_path=_unset, opus_path=_unset, flac_path=_unset,
                 quiet=_unset, config_path=_unset, stream=_unset,
                 ):
        """
        :param int or bool or None threads: If equal to 1, created one thread object,
        if more running in multiprocessing mode and create a lot of processes. Default 1
        :param bool or None force_process: If True engines run in multiprocessing mode, if False in threads mode.
        Default False if threads == 1, else True.
        :param str or None lib_path: Path to RHVoice library.
        Default libRHVoice.so in Linux, libRHVoice.dylib in macOS and RHVoice.dll in Windows.
        :param str or None data_path: Path to folder, containing voices and languages folders.
        Default /usr/local/share/RHVoice.
        :param list or str or None resources: A list of paths to language and voice data.
        It should be used when it is not possible to collect all the data in one place. Default [].
        :param str or None lame_path: Path to lame, optional. File must be present for mp3 support. Default lame.
        :param str or None opus_path: Path to opusenc, optional. File must be present for opus support. Default opusenc.
        :param str or None flac_path: Path to flac, optional. File must be present for flac support. Default flac.
        :param bool or None quiet: If True don't info output. Default False.
        :param str or None config_path: Path to folder, contain RHVoice.conf in linux and RHVoice.ini in windows.
        Default /usr/local/etc/RHVoice.
        :param bool stream: Processing and sending chunks soon as possible,
        otherwise processing and sending only full data including length:
        say will return one big chunk, formats other than wav and pcm will be generated much slower. Default True.
        """
        envs = {}
        for key in self.PARAMS:
            if key in locals() and locals()[key] is not _unset:
                envs[key] = locals()[key]

        envs = self._get_environs(envs)
        quiet = self._prepare_bool(envs.pop('quiet', False))
        stream = self._prepare_bool(envs.pop('stream', True), True)
        self._threads = self._prepare_threads(envs.pop('threads', None))
        self._process = self._prepare_process(envs.pop('force_process', None), self._threads)
        self._cmd = self._get_cmd(
            quiet, stream,
            envs.pop('lame_path', None),
            envs.pop('opus_path', None),
            envs.pop('flac_path', None),
        )
        self._formats = frozenset(['pcm', 'wav'] + [key for key in self._cmd])

        self.__test_engine(envs.copy(), quiet)
        envs.update(stream=stream)
        super().__init__(self._threads, self._process, self._cmd, self._formats, **envs)

    def __test_engine(self, envs: dict, quiet: bool):
        lib_path = {} if 'lib_path' not in envs else {'lib_path': envs.pop('lib_path')}
        test = rhvoice_proxy.Engine(**lib_path)
        self._api = test.api
        self._version = test.version
        if self._version not in rhvoice_proxy.SUPPORT and not quiet:
            print(
                'Warning! Unsupported library version, use API {}. Supported: {}, library: {}.'.format(
                    self._api, rhvoice_proxy.SUPPORT, self._version
                )
            )
        test.init(play_speech_cb=lambda *_: True, set_sample_rate_cb=lambda *_: True, **envs)
        self._voices = test.voices
        self._params = test.params
        self._voice_profiles = test.voice_profiles
        test.exterminate()

    @property
    def formats(self) -> frozenset:
        return self._formats

    @property
    def thread_count(self) -> int:
        return self._threads

    @property
    def process(self) -> bool:
        return self._process

    @property
    def voices(self) -> tuple:
        return tuple([key for key in self._voices])

    @property
    def voice_profiles(self) -> tuple:
        return self._voice_profiles

    @property
    def api_version(self) -> str:
        return self._api

    @property
    def lib_version(self) -> str:
        return self._version

    @property
    def voices_info(self) -> dict:
        return self._voices

    @property
    def cmd(self) -> dict:
        return self._cmd

    def set_params(self, **kwargs) -> bool:
        result = False
        try:
            result = self._params.update_from_dict(kwargs)
        except RuntimeError as e:
            print('set_params error: {}'.format(e))
        if result:
            super().set_params(**kwargs)
        return result

    def get_params(self, param=None):
        if param is None:
            return self._params.to_dict()
        return self._params.get_param(param)

    def _get_environs(self, kwargs):
        result = {}
        for key, val in self.PARAMS.items():
            if key in kwargs:
                result[key] = kwargs[key]
            elif val in os.environ:
                result[key] = os.environ[val]
        return result

    @staticmethod
    def _prepare_bool(val, def_: bool = False):
        if isinstance(val, str):
            val = val.lower()
            if val in ['true', 'yes', 'enable']:
                return True
            elif val in ['false', 'no', 'disable']:
                return False
        elif isinstance(val, bool):
            return val
        return def_

    def _prepare_process(self, force_process, threads):
        return self._prepare_bool(force_process, threads > 1)

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
    def _get_cmd(quiet, stream, lame, opus, flac):
        base_cmd = {
            'mp3': [[lame or 'lame', '-t', '-hv', '--silent', '-', '-'], 'lame'],
            'opus': [[opus or 'opusenc', '--ignorelength', '--quiet', '--discard-comments', '-', '-'], 'opus-tools'],
            'flac': [[flac or 'flac', '--ignore-chunk-sizes', '--totally-silent', '--best', '--stdout', '-'], 'flac'],
        }
        cmd = {}

        for key, val in base_cmd.items():
            if shutil.which(val[0][0]):
                cmd[key] = val[0]
                if not stream:
                    cmd[key].pop(1)
            elif not quiet:
                print('Disable {} support - {} not found. Use apt install {}'.format(key, val[0][0], val[1]))
        return cmd
