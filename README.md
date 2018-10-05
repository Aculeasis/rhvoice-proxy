## High-level interface for RHVoice library
[![PyPI version](https://img.shields.io/pypi/v/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/) [![Python versions](https://img.shields.io/pypi/pyversions/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/) [![Build Status](https://travis-ci.org/Aculeasis/rhvoice-proxy.svg?branch=master)](https://travis-ci.org/Aculeasis/rhvoice-proxy)

Generate speech stream from text without re-initializing engine.
This very fast and more convenient than call RHVoice-test. Off the shelf supports `wav`, `mp3` and `opus`.

## Install
`pip install rhvoice-wrapper`

This package **NOT** provide [RHvoice](https://github.com/Olga-Yakovleva/RHVoice). You must be build (or install) RHVoice, languages and voices manually. In Windows you must specify the paths for work.

## Documentation

First create TTS object:
```python
from rhvoice_wrapper import TTS

tts = TTS(threads=1)
```
You may set options when creating or through variable environments (UPPER REGISTER). Options override variable environments. To set the default value use `None`:
- **threads** or **THREADED**. If equal to `1`, created one thread object, if more running in multiprocessing mode and create a lot of processes. Threading mode is not race condition safe, multiprocessing mode is safe. Default `1`.
- **force_process**: If `True`, force using multiprocessing mode. Default `False`.
- **lib_path** or **RHVOICELIBPATH**: Path to RHVoice library. Default `libRHVoice.so` in Linux and `RHVoice.dll` in Windows.
- **data_path** or **RHVOICEDATAPATH**: Path to folder, containing voices and languages folders. Default `/usr/local/share/RHVoice`.
- **resources** or **RHVOICERESOURCES**: List of paths, optional. I do not know what is this. Default: `['/usr/local/etc/RHVoice/dicts/Russian/']`.
- **lame_path** or **LAMEPATH**: Path to `lame`, optional. Lame must be present for `mp3` support. Default `lame`.
- **opus_path** or **OPUSENCPATH**: Path to `opusenc`, optional. File must be present for `opus` support. Default `opusenc`.

### Usage
Start synthesis generator and get audio data, chunk by chunk:
```python
def generator_audio(text, voice, audio_format):
    with tts.say(text, voice, audio_format) as gen:
        for chunk in gen:
            yield chunk
```
Or just save to file:
```python
tts.to_file(filename='esperanto.ogg', text='Saluton mondo', voice='spomenka', format_='opus')
```

### Other methods
#### set_params
Changes voice synthesizer settings:
```python
tts.set_params(**kwargs)
```
Allow: `absolute_rate, relative_rate, absolute_pitch, relative_pitch, absolute_volume, relative_volume, punctuation_mode, capitals_mode`. See RHVoice documentation for details.

#### benchmarks
Synthetic benchmark. First return string 'start...', then results every 30 seconds. Works only in multiprocessing mode. Example:
```python
from rhvoice_wrapper import TTS

tts = TTS(threads=24)
end_in = 5
for result in tts.benchmarks():
    print(result)
    end_in -= 1
    if not end_in:
        break
tts.join()
```

#### join
Join thread or processes. Don't use object after join:
```python
tts.join()
```

### Properties
- `TTS.formats`: List of supported formats, `wav` always present.
- `TTS.thread_count`: Number of synthesis threads.
- `TTS.process`: If `True`, TTS running in multiprocessing mode.
- `TTS.voices`: List of supported voices.
- `TTS.voices_info`: Dictionary of supported voices with voices information. 
- `TTS.api_version`: Supported RHVoice library version. If different from `lib_version`, may incorrect work.
- `TTS.lib_version`: RHVoice library version.
- `TTS.cmd`: Dictionary of external calls, as it is.

## Examples
- [Example usage](https://github.com/Aculeasis/rhvoice-rest/blob/master/app.py)

## Requirements
- RHvoice library, languages and voices.
- Python 3+.

Tested on python 3.6 in Linux and Windows 10.

## Links
- [RHvoice](https://github.com/Olga-Yakovleva/RHVoice)
