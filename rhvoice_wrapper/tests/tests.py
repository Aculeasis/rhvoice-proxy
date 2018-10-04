#!/usr/bin/env python3

import os
import unittest

from rhvoice_wrapper import TTS
from rhvoice_wrapper import rhvoice_proxy


class Monolithic(unittest.TestCase):
    def step_0_init(self):
        self.files = {
            'wav_base': 'wav1.wav',
            'wav': 'wav2.wav',
            'mp3': 'mp3.mp3',
            'opus': 'opus.ogg',
        }
        self.msg = 'Я умею сохранять свой голос в {}'
        self.voice = 'anna'

        self.engine = rhvoice_proxy.Engine()
        self.wave = rhvoice_proxy.WaveWriteCallback()
        self.engine.init(self.wave)
        self.tts = TTS()

    def step_1_info(self):
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
        print()

    def step_2_engine(self):
        self.assertGreater(len(self.engine.voices), 0)
        self.assertIn(self.voice, self.engine.voices)
        self.engine.set_voice(self.voice)
        self.wave.set(self.files['wav_base'])
        self.engine.generate(self.msg.format('wav'))

    def step_3_tts(self):
        self.assertGreater(len(self.tts.voices), 0)
        self.assertIn(self.voice, self.tts.voices)
        for target in [[key, val] for key, val in self.files.items() if key in self.tts.formats]:
            self.tts.to_file(filename=target[1], text=self.msg.format(target[0]), voice=self.voice, format_=target[0])

    def step_4_wave(self):
        self.assertTrue(os.path.isfile(self.files['wav_base']))
        self.assertTrue(os.path.isfile(self.files['wav']))

        wav1 = os.path.getsize(self.files['wav_base'])
        wav2 = os.path.getsize(self.files['wav'])
        self.assertEqual(wav1, wav2)
        self.assertGreater(wav1, 0)

    def step_5_other_files(self):
        for target in [val for key, val in self.files.items() if key not in ['wav_base', 'wav']]:
            if os.path.isfile(target):
                self.assertGreater(os.path.getsize(target), 0)

    def step_6_end(self):
        self.tts.join()
        for val in self.files.values():
            if os.path.isfile(val):
                os.remove(val)

    def _steps(self):
        for name in sorted(dir(self)):
            if name.startswith('step_'):
                yield name, getattr(self, name)

    def test_steps(self):
        for name, step in self._steps():
            try:
                step()
            except Exception as e:
                self.fail('{} failed ({}: {})'.format(step, type(e), e))


if __name__ == '__main__':
    unittest.main()
