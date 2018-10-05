#!/usr/bin/env python3

import os
import threading
import unittest

from rhvoice_wrapper import TTS
from rhvoice_wrapper import rhvoice_proxy


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
        self.wave = rhvoice_proxy.WaveWriteCallback()
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

    def step_05_other_files(self):
        for target in [val for key, val in self.files.items() if key not in ['wav_base', 'wav']]:
            if os.path.isfile(target):
                self.assertGreater(os.path.getsize(target), 0)

    def step_06_gen_files2(self):
        self.tts.set_params(absolute_rate=1, absolute_pitch=1)
        for target in [[key, val] for key, val in self.files2.items() if key in self.tts.formats]:
            self.tts.to_file(filename=target[1], text=self.msg.format(target[0]), voice=self.voice, format_=target[0])

    def step_07_compare_1_2(self):
        for key, val in self.files2.items():
            if os.path.isfile(val):
                f2 = os.path.getsize(val)
                self.assertNotEqual(f2, os.path.getsize(self.files[key]))
                self.assertGreater(f2, 0)

    def step_08_processes(self):
        self.tts.join()
        self.tts = TTS(threads=3)

        self.step_09_clear()
        wav_size = self._test_processes_format('wav')
        self.step_09_clear()

        for test in ['opus', 'mp3']:
            if test in self.tts.formats:
                lossy_size = self._test_processes_format(test)
                self.assertGreater(wav_size, lossy_size)
                break

    def _test_processes_format(self, format_):
        ths = []
        for x in self.files.values():
            kwargs = {'filename': x, 'text': self.msg, 'voice': self.voice, 'format_': format_}
            th = threading.Thread(target=self.tts.to_file, kwargs=kwargs)
            th.start()
            ths.append(th)
        [x.join() for x in ths]

        first = os.path.getsize(self.files['wav_base'])
        self.assertGreater(first, 0)
        for test in self.files.values():
            second = os.path.getsize(test)
            self.assertEqual(first, second)
        return first

    def step_09_clear(self):
        for val in [x for x in self.files.values()] + [x for x in self.files2.values()]:
            if os.path.isfile(val):
                os.remove(val)

    def step_10_join(self):
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
                self.fail('{} failed ({}: {})'.format(step, type(e), e))


if __name__ == '__main__':
    unittest.main()
