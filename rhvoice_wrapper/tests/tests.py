#!/usr/bin/env python3

import os
import threading
import traceback
import unittest

from rhvoice_wrapper import TTS
from rhvoice_wrapper import rhvoice_proxy
from rhvoice_wrapper.debug_callback import WaveWriteCallback


class Monolithic(unittest.TestCase):
    def step_00_init(self):
        self.files = {
            'wav_base': 'wav1.wav',
            'wav': 'wav2.wav',
            'mp3': 'mp3.mp3',
            'opus': 'opus.ogg',
        }
        self.files2 = {
            'wav': 'wav22.wav',
            'mp3': 'mp32.mp3',
            'opus': 'opus2.ogg',
        }
        self.msg = 'Я умею сохранять свой голос в {}'
        self.voice = 'anna'

        self.engine = rhvoice_proxy.Engine()
        self.wave = WaveWriteCallback()
        self.engine.init(self.wave)
        self.tts = TTS()

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
        print('Formats: {}'.format(', '.join(self.tts.formats)))

    def step_02_engine(self):
        self.assertGreater(len(self.engine.voices), 0)
        self.assertIn(self.voice, self.engine.voices)
        self.engine.set_voice(self.voice)
        self.wave.set(self.files['wav_base'])
        self.engine.generate(self.msg.format('wav'))
        self.wave.close()

    def step_03_tts(self):
        self.assertGreater(len(self.tts.voices), 0)
        self.assertIn(self.voice, self.tts.voices)
        for target in [[key, val] for key, val in self.files.items() if key in self.tts.formats]:
            self.tts.to_file(filename=target[1], text=self.msg.format(target[0]), voice=self.voice, format_=target[0])

    def step_04_wave(self):
        self.assertTrue(os.path.isfile(self.files['wav_base']))
        self.assertTrue(os.path.isfile(self.files['wav']))

        wav1 = os.path.getsize(self.files['wav_base'])
        wav2 = os.path.getsize(self.files['wav'])
        self.assertEqual(wav1, wav2)
        self.assertGreater(wav1, 0)

    def step_050_sets_recovery(self):
        sets = {'absolute_rate': 0.5}
        self.tts.to_file(filename=self.files['wav_base'], text=self.msg, voice=self.voice, format_='wav', sets=sets)
        self.tts.to_file(filename=self.files['wav'], text=self.msg, voice=self.voice, format_='wav')

        wav1 = os.path.getsize(self.files['wav_base'])
        wav2 = os.path.getsize(self.files['wav'])

        self.assertNotEqual(wav1, wav2)

    def step_05_other_files(self):
        for target in [val for key, val in self.files.items() if key not in ['wav_base', 'wav']]:
            if os.path.isfile(target):
                self.assertGreater(os.path.getsize(target), 0)

    def step_06_gen_files2(self):
        self.assertTrue(self.tts.set_params(absolute_rate=1, absolute_pitch=1))
        self.assertFalse(self.tts.set_params(absolute_rate=1, absolute_pitch=1))
        self.assertEqual(self.tts.get_params('absolute_rate'), 1)
        self.assertEqual(self.tts.get_params('absolute_pitch'), 1)

        self.assertTrue(isinstance(self.tts.get_params(), dict))
        self.assertIsNone(self.tts.get_params('always missing'))

        for target in [[key, val] for key, val in self.files2.items() if key in self.tts.formats]:
            self.tts.to_file(filename=target[1], text=self.msg.format(target[0]), voice=self.voice, format_=target[0])

    def step_07_compare_1_2(self):
        for key, val in self.files2.items():
            if os.path.isfile(val):
                f2 = os.path.getsize(val)
                self.assertNotEqual(f2, os.path.getsize(self.files[key]))
                self.assertGreater(f2, 0)

    def step_080_processes_create(self):
        self.tts.join()
        self.step_10_clear()
        self.tts = TTS(threads=3)

    def step_081_processes_wav(self):
        self._test_processes_format('wav')
        self.wav_size = self._processes_eq_size()
        self.step_10_clear()

    def step_082_processes_opus(self):
        self._test_format('opus')

    def step_083_processes_mp3(self):
        self._test_format('mp3')

    def _test_format(self, format_):
        if format_ not in self.tts.formats:
            return print('skip ', end='')
        self._test_processes_format(format_)
        lossy_size = self._processes_eq_size()
        self.assertGreater(self.wav_size, lossy_size, 'wav must be more {}'.format(format_))
        self.step_10_clear()

    def _test_processes_format(self, format_, sets=None):
        ths = []
        pos = 0
        for x in self.files.values():
            current_set = None
            if sets:
                current_set = sets[pos]
                pos += 1
            kwargs = {'filename': x, 'text': self.msg, 'voice': self.voice, 'format_': format_, 'sets': current_set}
            th = threading.Thread(target=self.tts.to_file, kwargs=kwargs)
            th.start()
            ths.append(th)
        [x.join() for x in ths]

    def _processes_eq_size(self):
        first = os.path.getsize(self.files['wav_base'])
        self.assertGreater(first, 0)
        for test in self.files.values():
            second = os.path.getsize(test)
            self.assertEqual(first, second, 'File sizes must be equal')
        return first

    def _processes_diff_size(self):
        all_size = [os.path.getsize(file) for file in self.files.values()]
        counts = len(all_size)
        for one in range(counts):
            for two in range(counts):
                if one == two:
                    continue
                self.assertNotEqual(all_size[one], all_size[two])

    def step_09_test_sets(self):
        volumes = [{'absolute_rate': x/1.2-1} for x in range(len(self.files))]
        self._test_processes_format('wav', volumes)
        self._processes_diff_size()

    def step_10_clear(self):
        for val in [x for x in self.files.values()] + [x for x in self.files2.values()]:
            if os.path.isfile(val):
                os.remove(val)

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
                self.step_10_clear()
                self.step_11_join()
                self.fail('{} failed ({}: {})'.format(step, type(e), e))


if __name__ == '__main__':
    unittest.main()
