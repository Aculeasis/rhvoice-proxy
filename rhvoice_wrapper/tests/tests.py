#!/usr/bin/env python3

import threading
import time
import traceback
import unittest

from rhvoice_wrapper import TTS
from rhvoice_wrapper import rhvoice_proxy
from rhvoice_wrapper.tests.debug_callback import WaveWriteFpCallback


def say_size(say, *args, **kwargs):
    size = 0
    with say(*args, **kwargs) as rd:
        for chunk in rd:
            size += len(chunk)
    return size


class ThChecker(threading.Thread):
    def __init__(self, say, kwargs):
        super().__init__()
        self._say = say
        self._kw = kwargs
        self._size = None
        self.start()

    def run(self):
        self._size = say_size(self._say, **self._kw)

    @property
    def size(self):
        self.join()
        return self._size


class Monolithic(unittest.TestCase):
    def step_00_init(self):
        all_formats = ['pcm', 'wav', 'mp3', 'opus', 'flac']
        self.files = {'wav_base': 'wav_engine'}
        self.files.update({key: key for key in all_formats})
        self.files2 = {key: '{}_2'.format(key) for key in all_formats}

        self.sizes = {}
        self.msg = 'Я умею сохранять свой голос в {}'
        self.voice = 'anna'
        self.wav_size = None

        self.engine = rhvoice_proxy.Engine()
        self.wave = WaveWriteFpCallback()
        self.engine.init(self.wave, self.wave.set_sample_rate)
        self.tts = TTS(quiet=True)

    def step_01_info(self):
        print()
        print('Versions:')
        print(' RHVoice:    {}'.format(self.engine.version))
        print(' Python API: {}'.format(rhvoice_proxy.__version__))
        print()

        voices = self.engine.voices
        voice_order = sorted(voices.items(), key=lambda x: x[1]['no'])
        voice_order = [v[0] for v in voice_order]
        print('Voice     Language  Gender')
        for i in range(len(voices)):
            voice = voices[voice_order[i]]
            print('  {name:10}  {lang:2}    {gender:2} '.format(**voice))
        print('Number of voices: {}'.format(len(voices)))
        print('Formats: {} ... '.format(', '.join(self.tts.formats)), end='')

    def step_02_engine(self):
        self.assertGreater(len(self.engine.voices), 0)
        self.assertIn(self.voice, self.engine.voices)
        self.engine.set_voice(self.voice)

        self.engine.generate(self.msg.format('wav'))
        self.sizes[self.files['wav_base']] = self.wave.size
        del self.wave

    def step_030_tts(self):
        self.assertGreater(len(self.tts.voices), 0)
        self.assertIn(self.voice, self.tts.voices)
        for target in [[key, val] for key, val in self.files.items() if key in self.tts.formats]:
            self.sizes[target[1]] = say_size(
                self.tts.say,
                text=self.msg.format(target[0]),
                voice=self.voice,
                format_=target[0]
            )

    def step_031_empty_text(self):
        size = say_size(self.tts.say, text='', format_='wav')
        self.assertEqual(size, 0, 'No text - no audio. Return {} bytes'.format(size))

    def step_04_wave(self):
        self.assertTrue(self.files['wav_base'] in self.sizes)
        self.assertTrue(self.files['wav'] in self.sizes)

        self.assertEqual(self.sizes[self.files['wav_base']], self.sizes[self.files['wav']])
        self.assertGreater(self.sizes[self.files['wav']], 0)

    def step_050_sets_recovery(self):
        sets = {'absolute_rate': 0.5}
        wav1 = say_size(self.tts.say, text=self.msg, voice=self.voice, format_='wav', sets=sets)
        wav2 = say_size(self.tts.say, text=self.msg, voice=self.voice, format_='wav')

        self.assertNotEqual(wav1, wav2)

    def step_05_other_files(self):
        for target in [val for key, val in self.files.items() if key not in ['wav_base', 'wav']]:
            if target in self.sizes:
                self.assertGreater(self.sizes[target], 0)

    def step_06_gen_files2(self):
        self.assertTrue(self.tts.set_params(absolute_rate=1, absolute_pitch=1))
        self.assertFalse(self.tts.set_params(absolute_rate=1, absolute_pitch=1))
        self.assertEqual(self.tts.get_params('absolute_rate'), 1)
        self.assertEqual(self.tts.get_params('absolute_pitch'), 1)

        self.assertTrue(isinstance(self.tts.get_params(), dict))
        self.assertIsNone(self.tts.get_params('always missing'))

        for target in [[key, val] for key, val in self.files2.items() if key in self.tts.formats]:
            self.sizes[target[1]] = say_size(
                self.tts.say,
                text=self.msg.format(target[0]),
                voice=self.voice,
                format_=target[0]
            )

    def step_07_compare_1_2(self):
        for key, val in self.files2.items():
            if val in self.sizes:
                s1 = self.sizes[self.files[key]]
                s2 = self.sizes[val]
                self.assertGreater(s1, s2)
                self.assertGreater(s2, 0)

    def step_080_processes_create(self):
        self.tts.join()
        self.clear_sizes()
        self.tts = TTS(threads=3, quiet=True)

    def step_081_processes_init(self):
        self._test_format('pcm')

    def step_082_processes_wave(self):
        self.wav_size = self._test_format('wav')

    def step_083_processes__pcm(self):
        self._test_format('pcm')

    def step_084_processes_opus(self):
        self._test_format('opus')

    def step_085_processes__mp3(self):
        self._test_format('mp3')

    def step_086_processes_flac(self):
        self._test_format('flac')

    def _test_format(self, format_):
        if format_ not in self.tts.formats:
            return print('skip ', end='')

        work_time = time.perf_counter()
        self._test_processes_format(format_)
        work_time = time.perf_counter() - work_time

        print('{:.3f} s '.format(work_time / len(self.files)), end='')
        data_size = self._processes_eq_size()
        if self.wav_size is not None:
            self.assertGreater(self.wav_size, data_size, 'wav must be more {}'.format(format_))
        self.clear_sizes()
        return data_size

    def _test_processes_format(self, format_, sets=None):
        ths = {}
        pos = 0
        for x in self.files.values():
            current_set = None
            if sets:
                current_set = sets[pos]
                pos += 1
            kwargs = {'text': self.msg, 'voice': self.voice, 'format_': format_, 'sets': current_set}
            ths[x] = ThChecker(self.tts.say, kwargs)
        for key, val in ths.items():
            self.sizes[key] = val.size

    def _processes_eq_size(self):
        all_size = [self.sizes[file] for file in self.files.values()]
        self.assertGreater(all_size[0], 0, 'Empty file {}'.format(str(all_size)))
        for test in all_size:
            self.assertEqual(all_size[0], test, 'File sizes must be equal: {}'.format(all_size))
        return all_size[0]

    def _processes_diff_size(self):
        all_size = [self.sizes[file] for file in self.files.values()]
        counts = len(all_size)
        for one in range(counts):
            for two in range(counts):
                if one == two:
                    continue
                self.assertNotEqual(all_size[one], all_size[two], 'File sizes must be not equal: {}'.format(all_size))

    def step_09_test_sets(self):
        volumes = [{'absolute_rate': x * 0.01} for x in range(-100, 101, 200 // (len(self.files) - 1))]
        self._test_processes_format('wav', volumes)
        self._processes_diff_size()

    def clear_sizes(self):
        self.sizes = {}

    def step_11_join(self):
        self.tts.join()

    def _steps(self):
        for name in sorted(dir(self)):
            if name.startswith('step_'):
                yield name, getattr(self, name)

    def test_steps(self):
        print()
        for name, step in self._steps():
            try:
                print('{} ... '.format(name), end='')
                step()
                print('ok')
            except Exception as e:
                print('FAILED')
                traceback.print_exc()
                self.step_11_join()
                self.fail('{} failed ({}: {})'.format(step, type(e), e))


if __name__ == '__main__':
    unittest.main()
