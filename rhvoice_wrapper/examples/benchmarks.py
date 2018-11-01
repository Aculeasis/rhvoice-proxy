#!/usr/bin/env python3

import multiprocessing
import threading
import time
from rhvoice_wrapper import TTS


def benchmarks(tts):
    # PPS - Phrases Per Second
    # i7-8700k: 82 PPS
    # OrangePi Prime: 4.4 PPS
    text = 'Так себе, вызовы сэй будут блокировать выполнение'
    workers = tuple([_Benchmarks(text, tts.say) for _ in range(tts.thread_count)])
    yield 'Start...'
    test_time = 30
    control = None
    try:
        while True:
            work_time = time.perf_counter()
            time.sleep(test_time)
            count = sum([w.count for w in workers])
            sizes = []
            for worker in workers:
                sizes.extend(worker.sizes)
            work_time = time.perf_counter() - work_time
            pps = count / work_time
            yield 'PPS: {:.4f} (run {:.3f} sec)'.format(pps, work_time)
            if sizes:
                if control is None:
                    control = sizes[0]
                avg = sum(sizes) / len(sizes)
                assert control == avg, 'Different sizes: {}'.format(sizes)

    finally:
        [w.join() for w in workers]


class _Benchmarks(threading.Thread):
    def __init__(self, text, say):
        super().__init__()
        self._text = text
        self._say = say
        self._count = 0
        self._sizes = []
        self._work = True
        self.start()

    def run(self):
        while self._work:
            size = 0
            with self._say(text=self._text, format_='wav') as fp:
                for chunk in fp:
                    size += len(chunk)
            self._sizes.append(size)
            self._count += 1

    @property
    def count(self):
        try:
            return self._count
        finally:
            self._count = 0

    @property
    def sizes(self):
        try:
            return self._sizes
        finally:
            self._sizes = []

    def join(self, timeout=None):
        if self._work:
            self._work = False
            super().join(timeout)


def main():
    tts = TTS(threads=int(multiprocessing.cpu_count() * 1.5))
    print('Lib version: {}'.format(tts.lib_version))
    print('Threads: {}'.format(tts.thread_count))
    print('Formats: {}'.format(tts.formats))
    print('Voices: {}'.format(tts.voices))
    max_ = 5
    for result in benchmarks(tts):
        print(result)
        max_ -= 1
        if not max_:
            break
    tts.join()


if __name__ == '__main__':
    main()
