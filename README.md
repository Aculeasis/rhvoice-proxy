## High-level interface for RHVoice library
[![API](https://img.shields.io/badge/API-1.2.0-lightgrey.svg)](https://github.com/Aculeasis/rhvoice-proxy)
[![PyPI version](https://img.shields.io/pypi/v/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![Python versions](https://img.shields.io/badge/python-3.4%2B-blue.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![PyPI - Format](https://img.shields.io/pypi/format/rhvoice-wrapper.svg)](https://pypi.org/project/rhvoice-wrapper/)
[![Build Status](https://travis-ci.org/Aculeasis/rhvoice-proxy.svg?branch=master)](https://travis-ci.org/Aculeasis/rhvoice-proxy)
[![Build status](https://ci.appveyor.com/api/projects/status/lan2fw4c4xl7pvya/branch/master?svg=true)](https://ci.appveyor.com/project/Aculeasis/rhvoice-proxy)

Generate speech stream used [RHVoice](https://github.com/Olga-Yakovleva/RHVoice) library from text without re-initializing engine.
This very fast and more convenient than call RHVoice-test.

Supported audio formats: `wav`, `mp3`, `opus`, `flac` and `pcm` (raw RHVoice output).

## Install
`pip3 install rhvoice-wrapper`

This package **NOT** provide RHVoice. You must be build (or install) RHVoice, languages and voices manually. In Windows you must specify the paths for work.

#### rhvoice-wrapper-bin
**Warning**! `rhvoice-wrapper-bin` not working in **macOS**, install RHVoice manually.

Instead of RHVoice you may install [rhvoice-wrapper-bin](https://github.com/Aculeasis/rhvoice-wrapper-bin). This is best way for Windows. 
If the `rhvoice-wrapper-bin` is installed, its libraries and data will be used automatically.

`pip3 install rhvoice-wrapper[rhvoice]`

## Documentation

First create TTS object:
```python
from rhvoice_wrapper import TTS

tts = TTS(threads=1)
```
You may set options when creating or through variable environments (UPPER REGISTER). Options override variable environments. To set the default value use `None`:
- **threads** or **THREADED**. If equal to `1`, created one thread object, if more running in multiprocessing mode and create a lot of processes. Default `1`.
- **force_process** or **PROCESSES_MODE**: If `True` engines run in multiprocessing mode, if `False` in threads mode.
Default `False` if threads == 1, else `True`.
**Threads mode and threads > 1 causes a segmentation faults or may return corrupted data**
- **lib_path** or **RHVOICELIBPATH**: Path to RHVoice library. Default `libRHVoice.so` in Linux, `libRHVoice.dylib` in macOS and `RHVoice.dll` in Windows.
- **data_path** or **RHVOICEDATAPATH**: Path to folder, containing voices and languages folders. Default `/usr/local/share/RHVoice`.
- **config_path** or **RHVOICECONFIGPATH**: Path to folder, contain RHVoice.conf in linux and RHVoice.ini in windows. Default `/usr/local/etc/RHVoice`.
- **resources** or **RHVOICERESOURCES**: A list of paths to language and voice data. It should be used when it is not possible to collect all the data in one place. Default `[]`.
- **lame_path** or **LAMEPATH**: Path to `lame`, optional. Lame must be present for `mp3` support. Default `lame`.
- **opus_path** or **OPUSENCPATH**: Path to `opusenc`, optional. File must be present for `opus` support. Default `opusenc`.
- **flac_path** or **FLACPATH**: Path to `flac`, optional. File must be present for `flac` support. Default `flac`.
- **quiet** or **QUIET**: If `True` don't info output. Default `False`.
- **stream** or **RHVOICESTREAM**: Processing and sending chunks soon as possible, otherwise processing and sending only full data including length: `say` will return one big chunk, formats other than `wav` and `pcm` will be generated much slower. Default `True`.

### Usage
Start synthesis generator and get audio data, chunk by chunk:
```python
def generator_audio(text, voice='anna', format_='wav', buff=4096, sets=None):
    with tts.say(text, voice, format_, buff, sets) as gen:
        for chunk in gen:
            yield chunk
```
Or get all audio data in one big chunk:
```python
data = tts.get('Hello world!', format_='wav')
print('data size: ', len(data), ' bytes')
subprocess.check_output(['aplay', '-q'], input=data)
```
Or just save to file:
```python
tts.to_file(filename='esperanto.ogg', text='Saluton mondo', voice='spomenka', format_='opus', sets=None)
```
`format_` is output audio format. Must be present in `tts.formats`.

`voice` is a voice of speaker. Must be present in `tts.voice_profiles`.
`voice='Voice', sets=None` equal `voice=None, sets={'voice_profile': 'Voice'}`, `voice` more priority.

`sets` may set as dict containing synthesis parameters as in [set_params](#set_params).
This parameters only work for current phrase. Default `None`.

If `buff` equal `None or 0`, for pcm and wav chunks return as is (probably little faster).
For others used default chunk size (4 KiB).

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

def generator_audio():
    with tts.say(_text()) as gen:
        for chunk in gen:
            yield chunk
```
### Other methods
#### set_params
Changes voice synthesizer settings:
```python
tts.set_params(**kwargs)
```
Allow: `voice_profile`, `absolute_rate`, `absolute_pitch`, `absolute_volume`, `relative_rate`, `relative_pitch`, `relative_volume`, `punctuation_mode`, `punctuation_list`, `capitals_mode`, `flags`. See RHVoice documentation for details.

Return `True` if change, else `False`.

#### get_params
Get voice synthesizer settings:
```python
tts.get_params(param=None)
```
If param is `None` return all settings in `dict`, else parameter value by name. If parameter not found return `None`.

#### join
Join thread or processes. Don't use object after join:
```python
tts.join()
```

### Properties
- `TTS.formats`: List of supported formats, `pcm` and `wav` always present.
- `TTS.thread_count`: Number of synthesis threads.
- `TTS.process`: If `True`, TTS running in multiprocessing mode.
- `TTS.voices`: List of supported voices.
- `TTS.voice_profiles`: List of supported voice profiles.
- `TTS.voices_info`: Dictionary of supported voices with voices information. 
- `TTS.api_version`: Supported RHVoice library version. If different from `lib_version`, may incorrect work.
- `TTS.lib_version`: RHVoice library version.
- `TTS.cmd`: Dictionary of external calls, as it is.

## Examples
- [Examples](https://github.com/Aculeasis/rhvoice-proxy/tree/master/rhvoice_wrapper/examples/)
- [Example usage](https://github.com/Aculeasis/rhvoice-rest/blob/master/app.py)

## Requirements
- OS: Linux, Windows, macOS
- RHVoice library 0.7.2 or above, languages and voices
- Python 3.4 +
