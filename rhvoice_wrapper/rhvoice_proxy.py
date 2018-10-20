#!/usr/bin/env python3

# Copyright (C) 2010-2013  Olga Yakovleva <yakovleva.o.v@gmail.com>
# Copyright (C) 2015  anatoly techtonik <techtonik@gmail.com>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Base on:
# https://github.com/Olga-Yakovleva/RHVoice/blob/master/src/nvda-synthDriver/__init__.py
# https://github.com/techtonik/RHVoice/blob/master/src/nvda-synthDriver/RHVoice.py

__author__ = "Olga Yakovleva <yakovleva.o.v@gmail.com>"
__version__ = '0.7.2'

import os
import platform
from ctypes import CDLL, CFUNCTYPE, POINTER, Structure, c_char_p, c_double
from ctypes import c_int, c_uint, c_short, c_void_p, byref

try:
    import rhvoice_wrapper_bin
    _LIB_PATH = rhvoice_wrapper_bin.lib_path
    _DATA_PATH = rhvoice_wrapper_bin.data_path
except ImportError:
    _LIB_PATH = None
    _DATA_PATH = None


# --- bindings ---
class RHVoice_tts_engine_struct(Structure):
    pass


RHVoice_tts_engine = POINTER(RHVoice_tts_engine_struct)


class RHVoice_message_struct(Structure):
    pass


RHVoice_message = POINTER(RHVoice_message_struct)


class RHVoice_callback_types:
    set_sample_rate = CFUNCTYPE(c_int, c_int, c_void_p)
    play_speech = CFUNCTYPE(c_int, POINTER(c_short), c_uint, c_void_p)
    process_mark = CFUNCTYPE(c_int, c_char_p, c_void_p)
    word_starts = CFUNCTYPE(c_int, c_uint, c_uint, c_void_p)
    word_ends = CFUNCTYPE(c_int, c_uint, c_uint, c_void_p)
    sentence_starts = CFUNCTYPE(c_int, c_uint, c_uint, c_void_p)
    sentence_ends = CFUNCTYPE(c_int, c_uint, c_uint, c_void_p)
    play_audio = CFUNCTYPE(c_int, c_char_p, c_void_p)


class RHVoice_callbacks(Structure):
    _fields_ = [("set_sample_rate", RHVoice_callback_types.set_sample_rate),
                ("play_speech", RHVoice_callback_types.play_speech),
                ("process_mark", RHVoice_callback_types.process_mark),
                ("word_starts", RHVoice_callback_types.word_starts),
                ("word_ends", RHVoice_callback_types.word_ends),
                ("sentence_starts", RHVoice_callback_types.sentence_starts),
                ("sentence_ends", RHVoice_callback_types.sentence_ends),
                ("play_audio", RHVoice_callback_types.play_audio)]


class RHVoice_init_params(Structure):
    _fields_ = [("data_path", c_char_p),
                ("config_path", c_char_p),
                ("resource_paths", POINTER(c_char_p)),
                ("callbacks", RHVoice_callbacks),
                ("options", c_uint)]


class RHVoice_message_type:
    text = 0
    ssml = 1
    characters = 2


class RHVoice_voice_gender:
    unknown = 0
    male = 1
    female = 2


class RHVoice_voice_info(Structure):
    _fields_ = [("language", c_char_p),
                ("name", c_char_p),
                ("gender", c_int)]


class RHVoice_punctuation_mode:
    default = 0
    none = 1
    all = 2
    some = 3


class RHVoice_capitals_mode:
    default = 0
    off = 1
    word = 2
    pitch = 3
    sound = 4


class RHVoice_synth_params(Structure):
    _fields_ = [("voice_profile", c_char_p),
                ("absolute_rate", c_double),
                ("absolute_pitch", c_double),
                ("absolute_volume", c_double),
                ("relative_rate", c_double),
                ("relative_pitch", c_double),
                ("relative_volume", c_double),
                ("punctuation_mode", c_int),
                ("punctuation_list", c_char_p),
                ("capitals_mode", c_int)]


def _lib_selector(lib_path):
    if lib_path is None:
        if os.name == 'nt':
            lib_path = 'RHVoice.dll'
        else:
            lib_path = 'libRHVoice.{}'.format('dylib' if platform.system().lower() == 'darwin' else 'so')
    return lib_path if os.name == 'nt' else lib_path.encode()


def load_tts_library(lib_path=None):
    lib = CDLL(_lib_selector(lib_path))
    lib.RHVoice_get_version.restype = c_char_p
    lib.RHVoice_new_tts_engine.argtypes = (POINTER(RHVoice_init_params),)
    lib.RHVoice_new_tts_engine.restype = RHVoice_tts_engine
    lib.RHVoice_delete_tts_engine.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_delete_tts_engine.restype = None
    lib.RHVoice_get_number_of_voices.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voices.restype = c_uint
    lib.RHVoice_get_voices.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_voices.restype = POINTER(RHVoice_voice_info)
    lib.RHVoice_get_number_of_voice_profiles.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voice_profiles.restype = c_uint
    lib.RHVoice_get_voice_profiles.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_voice_profiles.restype = POINTER(c_char_p)
    lib.RHVoice_are_languages_compatible.argtypes = (RHVoice_tts_engine, c_char_p, c_char_p)
    lib.RHVoice_are_languages_compatible.restype = c_int
    lib.RHVoice_new_message.argtypes = (
        RHVoice_tts_engine, c_char_p, c_uint, c_int, POINTER(RHVoice_synth_params), c_void_p)
    lib.RHVoice_new_message.restype = RHVoice_message
    lib.RHVoice_delete_message.arg_types = (RHVoice_message,)
    lib.RHVoice_delete_message.restype = None
    lib.RHVoice_speak.argtypes = (RHVoice_message,)
    lib.RHVoice_speak.restype = c_int
    return lib


# --- main code ---

def get_rhvoice_version(lib):
    return lib.RHVoice_get_version().decode('utf-8')


def get_engine(lib, play_speech_cb, set_sample_rate_cb, resources=None, data_path=None):
    """
    Load DLL and initialize speech engine - load language data
    and set callbacks.
    """
    if isinstance(resources, str):
        resources = [resources]

    callbacks = RHVoice_callbacks()
    callbacks.play_speech = RHVoice_callback_types.play_speech(play_speech_cb)
    callbacks.set_sample_rate = RHVoice_callback_types.set_sample_rate(set_sample_rate_cb)

    resource_paths = [b'/usr/local/etc/RHVoice/dicts/Russian/', ] if not resources else [k.encode() for k in resources]
    params = RHVoice_init_params()
    # noinspection PyTypeChecker,PyCallingNonCallable
    params.resource_paths = (c_char_p * (len(resource_paths) + 1))(*(resource_paths + [None]))
    params.data_path = data_path.encode() if data_path else b'/usr/local/share/RHVoice'
    params.callbacks = callbacks
    engine = lib.RHVoice_new_tts_engine(byref(params))
    if not engine:
        raise RuntimeError('RHVoice: engine initialization error')
    # link for params must be present in memory while engine works
    return engine, params


def speak_generate(lib, text, synth_params, engine):
    text = text.encode()
    message = lib.RHVoice_new_message(
        engine,
        text,
        len(text),
        RHVoice_message_type.text,
        byref(synth_params),
        None
    )
    if not message:
        raise RuntimeError('RHVoice: message building error')
    lib.RHVoice_speak(message)
    lib.RHVoice_delete_message(message)  # free the memory (check when message is stored)


def get_voices(lib, engine):
    """
    Returns nested dictionary with voice information. First
    level key is voice name in lowercase, second level keys
    are voice properties.
    """
    genders = {1: 'male', 2: 'female'}
    voices = dict()
    voices_total = lib.RHVoice_get_number_of_voices(engine)
    first_voice = lib.RHVoice_get_voices(engine)
    for voiceno in range(voices_total):
        vi = first_voice[voiceno]
        key = vi.name.lower().decode()
        voices[key] = dict(
            no=voiceno,
            name=vi.name.decode(),
            lang=vi.language.decode(),
            gender=genders[vi.gender]
        )
    return voices


class Engine:
    SYNTHESIS_SET = {
        'absolute_rate': 0,
        'relative_rate': 1,
        'absolute_pitch': 0,
        'relative_pitch': 1,
        'absolute_volume': 0,
        'relative_volume': 1,
        'punctuation_mode': RHVoice_punctuation_mode.default,
        'capitals_mode': RHVoice_capitals_mode.default
    }

    def __init__(self, lib_path=_LIB_PATH):
        self._lib = load_tts_library(lib_path)
        self._engine = None
        self._synth_params = None
        self.set_params(**self.SYNTHESIS_SET)
        self.__save_me = None

    @property
    def version(self):
        return get_rhvoice_version(self._lib)

    def init(self, play_speech_cb, set_sample_rate_cb, resources=None, data_path=_DATA_PATH):
        (self._engine, self.__save_me) = get_engine(self._lib, play_speech_cb, set_sample_rate_cb, resources, data_path)

    @property
    def voices(self):
        return get_voices(self._lib, self._engine)

    def set_voice(self, voices):
        alt_voice = None
        voice = None
        if isinstance(voices, str):
            voice = voices
        elif isinstance(voices, (tuple, list)) and len(voices) >= 2:
            voice = voices[0]
            alt_voice = voices[1]
        voice = voice or 'anna'
        voice = voice.capitalize()
        if alt_voice:
            voice = '{}+{}'.format(voice, alt_voice.capitalize())
        self._synth_params.voice_profile = voice.encode()

    def generate(self, text):
        speak_generate(self._lib, text, self._synth_params, self._engine)

    def set_params(self, **kw):
        val = kw.copy()
        val.update(voice_profile=b'Anna', punctuation_list=None)
        self._synth_params = RHVoice_synth_params(**val)
