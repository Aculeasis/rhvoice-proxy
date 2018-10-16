## High-level interface for RHVoice library
[![API](https://img.shields.io/badge/API-0.7.2-lightgrey.svg)](https://github.com/Aculeasis/rhvoice-proxy)
[![PyPI version](https://img.shields.io/pypi/v/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![Python versions](https://img.shields.io/badge/python-3.4%2B-blue.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![PyPI - Format](https://img.shields.io/pypi/format/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![Build Status](https://travis-ci.org/Aculeasis/rhvoice-proxy.svg?branch=master)](https://travis-ci.org/Aculeasis/rhvoice-proxy)
[![Build status](https://ci.appveyor.com/api/projects/status/lan2fw4c4xl7pvya/branch/master?svg=true)](https://ci.appveyor.com/project/Aculeasis/rhvoice-proxy)

Generate speech stream from text without re-initializing engine.
This very fast and more convenient than call RHVoice-test. Off the shelf supports `wav`, `mp3` and `opus`.

## Install
`pip3 install rhvoice-wrapper`

This package **NOT** provide [RHvoice](https://github.com/Olga-Yakovleva/RHVoice). You must be build (or install) RHVoice, languages and voices manually. In Windows you must specify the paths for work.

#### rhvoice-wrapper-bin
**Warning**! `rhvoice-wrapper-bin` not working in **macOS**, install RHVoice manually.

Instead of RHVoice you may install [rhvoice-wrapper-bin](https://github.com/Aculeasis/rhvoice-wrapper-bin). This is best way for Windows. 
If the `rhvoice-wrapper-bin` is installed, its libraries and data will be used automatically.

`pip3 install rhvoice-wrapper-bin`

## Documentation

First create TTS object:
```python
from rhvoice_wrapper import TTS

tts = TTS(threads=1)
```
You may set options when creating or through variable environments (UPPER REGISTER). Options override variable environments. To set the default value use `None`:
- **threads** or **THREADED**. If equal to `1`, created one thread object, if more running in multiprocessing mode and create a lot of processes. Threading mode is not race condition safe, multiprocessing mode is safe. Default `1`.
- **force_process**: If `True`, force using multiprocessing mode. Default `False`.
- **lib_path** or **RHVOICELIBPATH**: Path to RHVoice library. Default `libRHVoice.so` in Linux, `libRHVoice.dylib` in macOS and `RHVoice.dll` in Windows.
- **data_path** or **RHVOICEDATAPATH**: Path to folder, containing voices and languages folders. Default `/usr/local/share/RHVoice`.
- **resources** or **RHVOICERESOURCES**: List of paths, optional. I do not know what is this. Default: `['/usr/local/etc/RHVoice/dicts/Russian/']`.
- **lame_path** or **LAMEPATH**: Path to `lame`, optional. Lame must be present for `mp3` support. Default `lame`.
- **opus_path** or **OPUSENCPATH**: Path to `opusenc`, optional. File must be present for `opus` support. Default `opusenc`.

### Usage
Start synthesis generator and get audio data, chunk by chunk:
```python
def generator_audio(text, voice, audio_format, sets):
    with tts.say(text, voice, audio_format, sets=sets) as gen:
        for chunk in gen:
            yield chunk
```
Or just save to file:
```python
tts.to_file(filename='esperanto.ogg', text='Saluton mondo', voice='spomenka', format_='opus', sets=None)
```
`sets` may set as dict containing synthesis parameters as in [set_params](#set_params).
This parameters only work for current phrase. Default `None`.

#### Text as iterable object
If `text` iterable object, all its fragments will processing successively.
This is a good method for processing incredibly large texts.
Remember, the generator cannot be transferred to another process. Example:
```python
def _text():
    with open('wery_large_book.txt') as fp:
        text = fp.read(5000)
        while text:
            yield text
            text = fp.read(5000)

def generator_audio(voice, audio_format, sets):
    with tts.say(_text(), voice, audio_format, sets=sets) as gen:
        for chunk in gen:
            yield chunk
```
### Other methods
#### set_params
Changes voice synthesizer settings:
```python
tts.set_params(**kwargs)
```
Allow: `absolute_rate, relative_rate, absolute_pitch, relative_pitch, absolute_volume, relative_volume, punctuation_mode, capitals_mode`. See RHVoice documentation for details.

Return `True` if change, else `False`.

#### get_params
Get voice synthesizer settings:
```python
tts.get_params(param=None)
```
If param is `None` return all settings in `dict`, else parameter value by name as `numeric`. If parameter not found return `None`.

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
- [Examples](https://github.com/Aculeasis/rhvoice-proxy/tree/master/rhvoice_wrapper/examples/)
- [Example usage](https://github.com/Aculeasis/rhvoice-rest/blob/master/app.py)

## Requirements
- OS: Linux, Windows, macOS
- RHvoice library, languages and voices
- Python 3.4 +

## Links
- [RHvoice](https://github.com/Olga-Yakovleva/RHVoice)
- [rhvoice-wrapper-bin](https://github.com/Aculeasis/rhvoice-wrapper-bin)
