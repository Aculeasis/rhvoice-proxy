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

from rhvoice_wrapper import rhvoice_proxy

_unset = object()
DEFAULT_CHUNK_SIZE = 1024 * 4
DEFAULT_FORMAT = 'wav'


def _prepare_synthesis_params(old: dict, data: dict):
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
        try:
            self._pipe.qsize()
        except NotImplementedError:
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
    POPEN_TIMEOUT = 10
    JOIN_TIMEOUT = 10

    def __init__(self, cmd: dict, pipe: _StreamPipe):
        self._cmd = cmd
        self._stream = pipe
        self._wave, self._in_out, self._popen = None, None, None
        self._starting = False

        self.get = self._stream.get
        self.qsize = self._stream.qsize

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


class _BaseTTS:
    RELEASE_TIMEOUT = 3

    def __init__(self, pipe: _StreamPipe, free, cmd: dict, allow_formats: frozenset, **kwargs):
        self._free = free
        self._allow_formats = allow_formats
        self._kwargs = kwargs.copy()
        self._synthesis_param = rhvoice_proxy.Engine.SYNTHESIS_SET.copy()  # Current params
        self._lib_path = {} if 'lib_path' not in self._kwargs else {'lib_path': self._kwargs.pop('lib_path')}
        self._wait = threading.Event()
        self._pipe = _Pipe()
        self._format = DEFAULT_FORMAT
        self._chunk_size = DEFAULT_CHUNK_SIZE
        self._engine = None
        self._worker = _AudioWorker(cmd=cmd, pipe=pipe)
        self._work = True
        self._client_here = threading.Event()
        self._client_here.set()
        self._generator_work = threading.Event()
        self._generator_work.set()
        self._still_processing = False
        self._rollback_sets = None

    def _change_sets(self, sets: dict or None):
        if not sets:
            return
        old_params = self._synthesis_param.copy()
        if _prepare_synthesis_params(self._synthesis_param, sets):
            self._engine.set_params(**self._synthesis_param)
            if self._rollback_sets is None:
                self._rollback_sets = old_params

    def _restore_sets(self):
        if self._rollback_sets:
            self._synthesis_param = self._rollback_sets
            self._engine.set_params(**self._synthesis_param)
            self._rollback_sets = None

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
        if sets is not None and not isinstance(sets, dict):
            RuntimeError('Sets must be dict or None')
        self._pipe.put((text, voice, format_, chunk_size, sets))
        self._wait.wait(3600)
        self._wait.clear()

    @contextmanager
    def say(self, text, voice, format_, buff, sets):
        try:
            format_ = format_ or DEFAULT_FORMAT
            self._client_request(text, voice, format_, buff, sets)
            yield self._iter_me_splitting(buff) if format_ in ['pcm', 'wav'] and buff else self._iter_me()
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

    def _generate(self, text, voice, format_, chunk_size, sets):
        self._generator_work.clear()
        self._change_sets(sets)
        self._format = format_
        self._chunk_size = chunk_size or DEFAULT_CHUNK_SIZE
        if voice:
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
        self._restore_sets()
        self._release_busy()

    def run(self):
        self._engine_init()
        while self._work:
            data = self._pipe.get()
            if data is None:
                break
            if isinstance(data, dict):
                self._synthesis_param = data
                self._engine.set_params(**data)
            else:
                self._generate(*data)
        self._engine_destroy()


class ThreadTTS(_BaseTTS, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        _BaseTTS.__init__(self, _StreamPipe(), *args, **kwargs)
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._pipe.put(None)
        super().join()


class ProcessTTS(_BaseTTS, multiprocessing.Process):
    def __init__(self, *args, **kwargs):
        multiprocessing.Process.__init__(self)
        _BaseTTS.__init__(self, _StreamPipe(True), *args, **kwargs)
        self._wait = multiprocessing.Event()
        self._pipe = _Pipe(True)
        self._client_here = multiprocessing.Event()
        self._client_here.set()
        self._generator_work = multiprocessing.Event()
        self._generator_work.set()
        self.start()

    def join(self, timeout=None):
        self._work = False
        self._pipe.put(None)
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

    def to_file(self, filename: str, text: str, voice='anna', format_=DEFAULT_FORMAT, sets=None):
        return self._caller().to_file(filename, text, voice, format_, sets)

    def say(self, text: str, voice='anna', format_=DEFAULT_FORMAT, buff=DEFAULT_CHUNK_SIZE, sets=None):
        return self._caller().say(text, voice, format_, buff, sets)

    def _caller(self):
        self._lock.acquire()
        try:
            while True:
                self._free.clear()
                for worker in self._workers:
                    if not worker.busy():
                        worker.client_here()
                        return worker
                if not self._free.wait(self.TIMEOUT):
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
    }

    def __init__(self, threads=_unset, force_process=_unset,
                 lib_path=_unset, data_path=_unset, resources=_unset,
                 lame_path=_unset, opus_path=_unset, flac_path=_unset,
                 quiet=_unset
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
        """
        kwargs = {}
        for key in self.PARAMS:
            if key in locals() and locals()[key] is not _unset:
                kwargs[key] = locals()[key]

        envs = self._get_environs(kwargs)

        self._threads = self._prepare_threads(envs.pop('threads', None))
        self._process = self._prepare_process(envs.pop('force_process', None), self._threads)
        quiet = self._prepare_bool(envs.pop('quiet', False))
        self._cmd = self._get_cmd(
            quiet,
            envs.pop('lame_path', None),
            envs.pop('opus_path', None),
            envs.pop('flac_path', None),
        )
        self._formats = frozenset(['pcm', 'wav'] + [key for key in self._cmd])

        self._api = rhvoice_proxy.__version__

        envs2 = envs.copy()
        lib_path = {} if 'lib_path' not in envs2 else {'lib_path': envs2.pop('lib_path')}
        test = rhvoice_proxy.Engine(**lib_path)
        self._version = test.version
        if self._version not in rhvoice_proxy.SUPPORT and not quiet:
            print(
                'Warning! Unsupported library version (API: {}; LIB: {})'.format(rhvoice_proxy.SUPPORT, self._version)
            )
        test.init(play_speech_cb=lambda *_: True, set_sample_rate_cb=lambda *_: True, **envs2)
        self._voices = test.voices
        self._synth_set = test.SYNTHESIS_SET.copy()
        del test

        tts = MultiTTS(self._threads, self._process, self._cmd, self._formats, **envs)

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
        if _prepare_synthesis_params(self._synth_set, kwargs):
            self.__set_params(**self._synth_set)
            return True
        else:
            return False

    def get_params(self, param=None):
        if param is None:
            return self._synth_set.copy()
        return self._synth_set.get(param)

    def _get_environs(self, kwargs):
        result = {}
        for key, val in self.PARAMS.items():
            if key in kwargs:
                result[key] = kwargs[key]
            elif val in os.environ:
                result[key] = os.environ[val]
        return result

    @staticmethod
    def _prepare_bool(val, def_: bool=False):
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
    def _get_cmd(quiet, lame, opus, flac):
        base_cmd = {
            'mp3': [[lame or 'lame', '-htv', '--silent', '-', '-'], 'lame'],
            'opus': [[opus or 'opusenc', '--quiet', '--discard-comments', '--ignorelength', '-', '-'], 'opus-tools'],
            'flac': [[flac or 'flac', '--totally-silent', '--best', '--stdout', '--ignore-chunk-sizes', '-'], 'flac'],
        }
        cmd = {}
        for key, val in base_cmd.items():
            if shutil.which(val[0][0]):
                cmd[key] = val[0]
            elif not quiet:
                print('Disable {} support - {} not found. Use apt install {}'.format(key, val[0][0], val[1]))
        return cmd
