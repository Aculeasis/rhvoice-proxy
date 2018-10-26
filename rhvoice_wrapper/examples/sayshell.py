#!/usr/bin/env python3

import cmd as cmd__
import queue
import textwrap
import threading

import pyaudio
from rhvoice_wrapper import TTS


def _prepare_set(val):
    try:
        return max(0, min(100, int(val)))
    except (TypeError, ValueError):
        return None


def _normalize_set(val):
        return val/50.0-1


def _get_sets(args):
    keys = ['absolute_rate', 'absolute_pitch', 'absolute_volume']
    return {key: _prepare_set(_normalize_set(args[key])) for key in keys if key in args}


class Player(threading.Thread):
    def __init__(self):
        super().__init__()
        self.tts = TTS(threads=1, force_process=False)
        self._queue = queue.Queue()
        self._p_audio = pyaudio.PyAudio()
        self._stream = self._p_audio.open(
            format=self._p_audio.get_format_from_width(2),
            channels=1,
            rate=24000,
            output=True,
            start=False,
        )
        self._sets = {'absolute_rate': '50', 'absolute_pitch': '50', 'absolute_volume': '50', 'voice': ['anna']}
        self._nums = 'min: 0, max 100'
        self._info = '{}: [{}] current: {}'
        self._work = True
        self._clear_queue = threading.Event()
        self.start()

    def volume(self, volume):
        if not volume:
            return self._info.format('Volume', self._nums, self._sets['absolute_volume'])
        else:
            return self._set_set('absolute_volume', volume)

    def rate(self, rate):
        if not rate:
            return self._info.format('Rate', self._nums, self._sets['absolute_rate'])
        else:
            return self._set_set('absolute_rate', rate)

    def pitch(self, pitch):
        if not pitch:
            return self._info.format('Pitch', self._nums, self._sets['absolute_pitch'])
        else:
            return self._set_set('absolute_pitch', pitch)

    def voice(self, voice):
        if not voice:
            return self._info.format('Voice', ', '.join(self.tts.voices), ', '.join(self._sets['voice']))
        else:
            if isinstance(voice, str):
                voice = [voice]
            voice = voice[:2]
            return self._set_set('voice', voice)

    def _set_set(self, param, value):
        if self._sets[param] == value:
            return 'unchanged'
        if param == 'voice':
            return self._set_voice(value)
        else:
            n_value = _prepare_set(value)
            if n_value is None:
                return 'bad value: {}'.format(value)
            self._sets[param] = str(n_value)
            self.tts.set_params(**{param: _normalize_set(n_value)})
            return 'success'

    def _set_voice(self, voice):
        for target in voice:
            if target not in self.tts.voices:
                return 'unknown voice: {}'.format(target)
        self._sets['voice'] = voice
        return 'success'

    def _text(self, text):
        for line in textwrap.wrap(text, 200):
            if not self._work:
                break
            line = line.strip('\n')
            if line:
                yield line

    def _clear(self):
        if self._clear_queue.is_set():
            while self._queue.qsize():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            self._clear_queue.clear()

    def clear(self):
        self._clear_queue.set()

    def stop(self):
        if self._work:
            self._work = False
            self._queue.put_nowait(None)
            self.join()
            self.tts.join()
            self._stream.stop_stream()
            self._stream.close()
            self._p_audio.terminate()

    def run(self):
        while self._work:
            self._clear()
            data = self._queue.get()
            if not data:
                break
            self._say(data)

    def say(self, text: str, print_=True):
        if not text:
            return
        if print_:
            print(text)
        self._queue.put_nowait(text)

    def _say(self, text):
        self._stream.start_stream()
        with self.tts.say(self._text(text), self._sets['voice'], 'pcm') as gen:
            for chunk in gen:
                if not self._work or self._clear_queue.is_set():
                    break
                self._stream.write(chunk)

        self._stream.stop_stream()


class StdOut:
    def __init__(self, say, std):
        self._say = say
        self._std = std
        self.flush = std.flush

    def write(self, data):
        self._std.write(data)
        self._say(data, False)


class SayShell(cmd__.Cmd):
    intro = 'Welcome to the test shell. Type help or ? to list commands.\n'
    prompt = '~# '

    def __init__(self):
        super().__init__()
        self._play = Player()
        self.say = self._play.say
        self.stdout = StdOut(self.say, self.stdout)

    def do_exit(self, _):
        """Exit from shell"""
        self.say('Exit', False)
        self._play.stop()
        return True

    def do_volume(self, arg):
        """Get\\Set volume: volume"""
        self.say(self._play.volume(arg))

    def do_rate(self, arg):
        """Get\\Set rate: rate."""
        self.say(self._play.rate(arg))

    def do_pitch(self, arg):
        """Get\\Set pitch: pitch."""
        self.say(self._play.pitch(arg))

    def do_voice(self, arg: str):
        """Get\\Set voices: voice [voice]."""
        arg = arg.strip()
        arg = arg.split() if arg else ''
        self.say(self._play.voice(arg))

    def do_say(self, arg):
        """Say: any string."""
        self.say(arg)

    def do_clear(self, _):
        """Stop playing and clear queue."""
        self._play.clear()


if __name__ == '__main__':
    SayShell().cmdloop()
