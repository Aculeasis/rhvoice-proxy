#!/usr/bin/env python3

# Copyright (C) 2010-2013  Olga Yakovleva <yakovleva.o.v@gmail.com>
# Copyright (C) 2015  anatoly techtonik <techtonik@gmail.com>
# Copyright (C) 2018 Aculeasis

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
SUPPORT = ('0.7.2', '1.0.0', '1.2.0')

import os
import platform
from ctypes import CDLL, CFUNCTYPE, POINTER, Structure, c_char_p, c_double
from ctypes import c_int, c_uint, c_short, c_void_p, byref

try:
    # noinspection PyUnresolvedReferences
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
    done = CFUNCTYPE(None, c_void_p)


class RHVoice_callbacks_072(Structure):
    _fields_ = [("set_sample_rate", RHVoice_callback_types.set_sample_rate),
                ("play_speech", RHVoice_callback_types.play_speech),
                ("process_mark", RHVoice_callback_types.process_mark),
                ("word_starts", RHVoice_callback_types.word_starts),
                ("word_ends", RHVoice_callback_types.word_ends),
                ("sentence_starts", RHVoice_callback_types.sentence_starts),
                ("sentence_ends", RHVoice_callback_types.sentence_ends),
                ("play_audio", RHVoice_callback_types.play_audio)]


class RHVoice_callbacks_100(Structure):
    # noinspection PyProtectedMember
    _fields_ = RHVoice_callbacks_072._fields_.copy()
    _fields_.append(("done", RHVoice_callback_types.done))


def RHVoice_callbacks(api: tuple):
    if api < (1, 0, 0):
        return RHVoice_callbacks_072
    return RHVoice_callbacks_100


class RHVoice_init_params_072(Structure):
    _fields_ = [("data_path", c_char_p),
                ("config_path", c_char_p),
                ("resource_paths", POINTER(c_char_p)),
                ("callbacks", RHVoice_callbacks_072),
                ("options", c_uint)]


class RHVoice_init_params_100(Structure):
    _fields_ = [("data_path", c_char_p),
                ("config_path", c_char_p),
                ("resource_paths", POINTER(c_char_p)),
                ("callbacks", RHVoice_callbacks_100),
                ("options", c_uint)]


def RHVoice_init_params(api: tuple):
    if api < (1, 0, 0):
        return RHVoice_init_params_072
    return RHVoice_init_params_100


class RHVoice_voice_info_072(Structure):
    _fields_ = [("language", c_char_p),
                ("name", c_char_p),
                ("gender", c_int)]


class RHVoice_voice_info_100(Structure):
    # noinspection PyProtectedMember
    _fields_ = RHVoice_voice_info_072._fields_.copy()
    _fields_.append(("country", c_char_p))


def RHVoice_voice_info(api: tuple):
    if api < (1, 0, 0):
        return RHVoice_voice_info_072
    return RHVoice_voice_info_100


class RHVoice_synth_params_100(Structure):
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


class RHVoice_synth_params_120(Structure):
    # noinspection PyProtectedMember
    _fields_ = RHVoice_synth_params_100._fields_.copy()
    _fields_.append(("flags", c_int))


def RHVoice_synth_params(api: tuple):
    if api < (1, 2, 0):
        return RHVoice_synth_params_100
    return RHVoice_synth_params_120


class RHVoice_message_type:
    text = 0
    ssml = 1
    characters = 2


class RHVoice_voice_gender:
    unknown = 0
    male = 1
    female = 2


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


class RHVoice_synth_flag:
    dont_clip_rate = 1


def _lib_selector(lib_path):
    if lib_path is None:
        if os.name == 'nt':
            lib_path = 'RHVoice.dll'
        else:
            lib_path = 'libRHVoice.{}'.format('dylib' if platform.system().lower() == 'darwin' else 'so')
    return lib_path if os.name == 'nt' else lib_path.encode()


def load_tts_library(lib_path=None, api=None):
    lib = CDLL(_lib_selector(lib_path))
    lib.RHVoice_get_version.restype = c_char_p
    api = api or get_compatible_api(lib)
    lib.RHVoice_new_tts_engine.argtypes = (POINTER(RHVoice_init_params(api)),)
    lib.RHVoice_new_tts_engine.restype = RHVoice_tts_engine
    lib.RHVoice_delete_tts_engine.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_delete_tts_engine.restype = None
    lib.RHVoice_get_number_of_voices.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voices.restype = c_uint
    lib.RHVoice_get_voices.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_voices.restype = POINTER(RHVoice_voice_info(api))
    lib.RHVoice_get_number_of_voice_profiles.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_number_of_voice_profiles.restype = c_uint
    lib.RHVoice_get_voice_profiles.argtypes = (RHVoice_tts_engine,)
    lib.RHVoice_get_voice_profiles.restype = POINTER(c_char_p)
    lib.RHVoice_are_languages_compatible.argtypes = (RHVoice_tts_engine, c_char_p, c_char_p)
    lib.RHVoice_are_languages_compatible.restype = c_int
    lib.RHVoice_new_message.argtypes = (
        RHVoice_tts_engine, c_char_p, c_uint, c_int, POINTER(RHVoice_synth_params(api)), c_void_p)
    lib.RHVoice_new_message.restype = RHVoice_message
    lib.RHVoice_delete_message.arg_types = (RHVoice_message,)
    lib.RHVoice_delete_message.restype = None
    lib.RHVoice_speak.argtypes = (RHVoice_message,)
    lib.RHVoice_speak.restype = c_int
    return lib, api


# --- main code ---

def get_compatible_api(lib) -> tuple:
    version = get_rhvoice_version(lib)
    # noinspection PyBroadException
    try:
        version = tuple(int(x) for x in version.split('.'))
    except Exception:
        version = (1, 0, 0)

    if version < (1, 0, 0):
        return 0, 7, 2
    if version < (1, 2, 0):
        return 1, 0, 0
    return 1, 2, 0


def get_rhvoice_version(lib):
    return lib.RHVoice_get_version().decode('utf-8')


def get_engine(lib, api, play_speech_cb, set_sample_rate_cb, resources=None, data_path=None, config_path=None):
    """
    Load DLL and initialize speech engine - load language data
    and set callbacks.
    """
    if isinstance(resources, str):
        resources = [resources]

    callbacks = RHVoice_callbacks(api)()
    callbacks.play_speech = RHVoice_callback_types.play_speech(play_speech_cb)
    callbacks.set_sample_rate = RHVoice_callback_types.set_sample_rate(set_sample_rate_cb)

    resource_paths = [] if not resources else [k.encode() for k in resources]
    params = RHVoice_init_params(api)()
    # noinspection PyTypeChecker,PyCallingNonCallable
    params.resource_paths = (c_char_p * (len(resource_paths) + 1))(*(resource_paths + [None]))
    params.data_path = data_path.encode() if data_path else b'/usr/local/share/RHVoice'
    params.config_path = config_path.encode() if config_path else b'/usr/local/etc/RHVoice'
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


def get_voices(lib, engine, api) -> dict:
    """
    Returns nested dictionary with voice information. First
    level key is voice name in lowercase, second level keys
    are voice properties.
    """
    genders = {0: 'unknown', 1: 'male', 2: 'female'}
    voices = dict()
    voices_total = lib.RHVoice_get_number_of_voices(engine)
    voices_raw = lib.RHVoice_get_voices(engine)
    for number in range(voices_total):
        vi = voices_raw[number]
        try:
            name = vi.name.decode()
        except (UnicodeDecodeError, AttributeError) as e:
            print('Wrong voice name, ignore #{}: {}'.format(number, e))
            continue
        key = name.lower()
        voices[key] = {
            'no': number,
            'name': name,
            'lang': vi.language.decode(errors='replace') if vi.language else 'NaN',
            'gender': genders.get(vi.gender, 'NaN'),
            'country': 'NaN' if api < (1, 0, 0) or not vi.country else vi.country.decode(errors='replace')
        }
    return voices


SYNTHESIS_SET_100 = {
        'absolute_rate': 0,
        'relative_rate': 1,
        'absolute_pitch': 0,
        'relative_pitch': 1,
        'absolute_volume': 0,
        'relative_volume': 1,
        'punctuation_mode': RHVoice_punctuation_mode.default,
        'capitals_mode': RHVoice_capitals_mode.default
    }
SYNTHESIS_SET_120 = SYNTHESIS_SET_100.copy()
SYNTHESIS_SET_120.update(flags=int(not RHVoice_synth_flag.dont_clip_rate))


def get_synthesis_set(api: tuple) -> dict:
    if api < (1, 2, 0):
        return SYNTHESIS_SET_100
    return SYNTHESIS_SET_120


class Engine:
    def __init__(self, lib_path=_LIB_PATH, api=None):
        self._lib, self._api = load_tts_library(lib_path, api)
        self.synthesis_set = get_synthesis_set(self._api)
        self._engine = None
        self._synth_params = None
        self._voice_profile = b'Anna'
        self.set_params(**self.synthesis_set)
        self.__save_me = None

    @property
    def version(self):
        return get_rhvoice_version(self._lib)

    @property
    def api(self):
        return '.'.join(str(k) for k in self._api)

    def init(self, play_speech_cb, set_sample_rate_cb, resources=None, data_path=_DATA_PATH, config_path=None):
        (self._engine, self.__save_me) = get_engine(
            self._lib, self._api, play_speech_cb, set_sample_rate_cb, resources, data_path, config_path
        )

    @property
    def voices(self) -> dict:
        return get_voices(self._lib, self._engine, self._api)

    def set_voice(self, voices: str or list):
        if not isinstance(voices, list):
            voices = [voices]
        voices = '+'.join([x.capitalize() for x in voices[:2] if x]) or 'Anna'
        self._voice_profile = voices.encode()
        self._synth_params.voice_profile = self._voice_profile

    def generate(self, text):
        speak_generate(self._lib, text, self._synth_params, self._engine)

    def set_params(self, **kw):
        val = kw.copy()
        val.update(voice_profile=self._voice_profile, punctuation_list=None)
        self._synth_params = RHVoice_synth_params(self._api)(**val)

    def exterminate(self):
        if self._engine:
            self._lib.RHVoice_delete_tts_engine(self._engine)
            self._engine = None
            self.__save_me = None
