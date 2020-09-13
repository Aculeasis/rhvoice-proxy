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

import os
import platform
from ctypes import CDLL, CFUNCTYPE, POINTER, Structure, c_char_p, c_double, c_int, c_uint, c_short, c_void_p

ADAPTED = ((0, 7, 2), (1, 0, 0), (1, 2, 0))


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


def get_rhvoice_version(lib):
    return lib.RHVoice_get_version().decode('utf-8')


def _get_compatible_api(lib) -> tuple:
    # noinspection PyBroadException
    try:
        version = tuple(int(x) for x in get_rhvoice_version(lib).split('.'))
    except Exception:
        version = (1, 0, 0)

    result = ADAPTED[0]
    for check in ADAPTED:
        if version < check:
            break
        result = check
    return result


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
    api = api or _get_compatible_api(lib)
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
