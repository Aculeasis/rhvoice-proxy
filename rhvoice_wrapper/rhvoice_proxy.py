#  part of rhvoice_bindings.py

from ctypes import c_char_p, byref

from rhvoice_wrapper.rhvoice_bindings import (
    RHVoice_callbacks, RHVoice_callback_types, RHVoice_init_params, RHVoice_synth_params, RHVoice_message_type,
    RHVoice_punctuation_mode, RHVoice_capitals_mode, RHVoice_synth_flag, load_tts_library, get_rhvoice_version
)

try:
    # noinspection PyUnresolvedReferences
    import rhvoice_wrapper_bin
    _LIB_PATH = rhvoice_wrapper_bin.lib_path
    _DATA_PATH = rhvoice_wrapper_bin.data_path
except ImportError:
    _LIB_PATH = None
    _DATA_PATH = None

SUPPORT = ('0.7.2', '1.0.0', '1.2.0', '1.2.1', '1.2.2', '1.2.3', '1.4.2')


class _SynthesisCheck:
    # magic?
    MIN_BASE = -2
    MAX_BASE = 2.5
    # from 0 to X, int
    MAX_PUNCTUATION = 3
    MAX_CAPITALS = 4
    MAX_FLAGS = 1
    #
    DEFAULT_VOICE = 'Anna'

    @staticmethod
    def __pass_interval(value, min_, max_):
        if value > max_:
            raise TypeError('{} > {}'.format(value, max_))
        if value < min_:
            raise TypeError('{} < {}'.format(value, min_))
        return value

    @classmethod
    def _pass_voice(cls, voices: str or list) -> bytes:
        if not isinstance(voices, list):
            voices = [voices]
        voices = '+'.join([x.capitalize() for x in voices[:2] if x])
        return (voices or cls.DEFAULT_VOICE).encode()

    @classmethod
    def _pass_base(cls, value: int or float) -> int or float:
        """MIN_BASE <= val <= MAX_BASE"""
        return cls.__pass_interval(value, cls.MIN_BASE, cls.MAX_BASE)

    @classmethod
    def __pass_enum(cls, value: int, max_: int) -> int:
        """0 <= val <= max_"""
        if not isinstance(value, int):
            raise TypeError('Must be int, get {}'.format(type(value)))
        return cls.__pass_interval(value, 0, max_)

    @classmethod
    def _pass_punctuation_mode(cls, value: int) -> int:
        return cls.__pass_enum(value, cls.MAX_PUNCTUATION)

    @classmethod
    def _pass_capitals_mode(cls, value: int) -> int:
        return cls.__pass_enum(value, cls.MAX_CAPITALS)

    @classmethod
    def _pass_flags(cls, value: int) -> int:
        return cls.__pass_enum(value, cls.MAX_FLAGS)

    @classmethod
    def _pass_punctuation_list(cls, punctuation_list: str or None) -> bytes or None:
        return punctuation_list.encode() if punctuation_list else None


class SynthesisParams(_SynthesisCheck):
    CHECKS = {
        # key: (default value, validation+clear function)
        'voice_profile': (_SynthesisCheck.DEFAULT_VOICE.encode(), _SynthesisCheck._pass_voice),
        'absolute_rate': (0, _SynthesisCheck._pass_base),
        'absolute_pitch': (0, _SynthesisCheck._pass_base),
        'absolute_volume': (0, _SynthesisCheck._pass_base),
        'relative_rate': (1, _SynthesisCheck._pass_base),
        'relative_pitch': (1, _SynthesisCheck._pass_base),
        'relative_volume': (1, _SynthesisCheck._pass_base),
        'punctuation_mode': (RHVoice_punctuation_mode.default, _SynthesisCheck._pass_punctuation_mode),
        'punctuation_list': (None, _SynthesisCheck._pass_punctuation_list),
        'capitals_mode': (RHVoice_capitals_mode.default, _SynthesisCheck._pass_capitals_mode),
        'flags': (int(not RHVoice_synth_flag.dont_clip_rate), _SynthesisCheck._pass_flags),
    }

    def __init__(self, api: tuple, params: dict or None = None):
        self.api = api
        self.synth_params = RHVoice_synth_params(self.api)()
        if params:
            self.update_from_dict(params)
        else:
            self._set_default()

    def update_from_dict(self, params: dict) -> bool:
        is_change = False
        for key, value in params.items():
            try:
                old_value = getattr(self.synth_params, key)
            except AttributeError:
                continue
            if key not in self.CHECKS:
                continue
            try:
                new_value = self.CHECKS[key][1](value)
            except Exception as e:
                raise RuntimeError('Wrong value from {}: {}'.format(key, e))
            if old_value == new_value:
                continue
            setattr(self.synth_params, key, new_value)
            is_change = True
        return is_change

    def get_param(self, key):
        try:
            return self._get_param(key)
        except AttributeError:
            return None

    def to_dict(self) -> dict:
        return {key: self._get_param(key) for key in self._synth_params_keys()}

    def copy_with(self, params: dict):
        result = SynthesisParams(self.api, params=self.to_dict())
        if params:
            result.update_from_dict(params)
        return result

    def _set_default(self):
        for key in self._synth_params_keys():
            setattr(self.synth_params, key, self.CHECKS[key][0])

    def _get_param(self, key):
        result = getattr(self.synth_params, key)
        return result.decode() if isinstance(result, bytes) else result

    def _synth_params_keys(self):
        # noinspection PyProtectedMember
        for key, _ in self.synth_params._fields_:
            yield key


class Engine:
    DEFAULT_DATA_PATH = '/usr/local/share/RHVoice'
    DEFAULT_CONFIG_PATH = '/usr/local/etc/RHVoice'
    GENDERS = {0: 'unknown', 1: 'male', 2: 'female'}

    def __init__(self, lib_path=_LIB_PATH, api=None):
        self._lib, self._api = load_tts_library(lib_path, api)
        self.params = SynthesisParams(self._api)
        self._engine, self.__save_me = None, None

    @property
    def version(self):
        return get_rhvoice_version(self._lib)

    @property
    def api(self):
        return '.'.join(str(k) for k in self._api)

    def init(self, play_speech_cb, set_sample_rate_cb, resources=None, data_path=_DATA_PATH, config_path=None):
        """initialize speech engine - load language data and set callbacks."""
        resources = resources or []
        if isinstance(resources, str):
            resources = [resources]
        resource_paths = [k.encode() for k in resources]

        callbacks = RHVoice_callbacks(self._api)(
            play_speech=RHVoice_callback_types.play_speech(play_speech_cb),
            set_sample_rate=RHVoice_callback_types.set_sample_rate(set_sample_rate_cb)
        )
        # noinspection PyTypeChecker
        params = RHVoice_init_params(self._api)(
            resource_paths=(c_char_p * (len(resource_paths) + 1))(*(resource_paths + [None])),
            data_path=(data_path or self.DEFAULT_DATA_PATH).encode(),
            config_path=(config_path or self.DEFAULT_CONFIG_PATH).encode(),
            callbacks=callbacks
        )
        self._engine = self._lib.RHVoice_new_tts_engine(byref(params))
        if not self._engine:
            raise RuntimeError('RHVoice: engine initialization error')
        # link for params must be present in memory while engine works
        self.__save_me = params

    @property
    def voices(self) -> dict:
        """
        Returns nested dictionary with voice information. First
        level key is voice name in lowercase, second level keys
        are voice properties.
        """
        voices = dict()
        voices_raw = self._lib.RHVoice_get_voices(self._engine)
        for number in range(self._lib.RHVoice_get_number_of_voices(self._engine)):
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
                'gender': self.GENDERS.get(vi.gender, 'NaN'),
                'country': 'NaN' if self._api < (1, 0, 0) or not vi.country else vi.country.decode(errors='replace')
            }
        return voices

    @property
    def voice_profiles(self) -> tuple:
        result = list()
        profiles_raw = self._lib.RHVoice_get_voice_profiles(self._engine)
        for number in range(self._lib.RHVoice_get_number_of_voice_profiles(self._engine)):
            try:
                result.append(profiles_raw[number].decode())
            except UnicodeDecodeError:
                pass
        return tuple(result)

    def generate(self, text, params: SynthesisParams = None):
        text = text.encode()
        synth_params = (params or self.params).synth_params
        message = self._lib.RHVoice_new_message(
            self._engine,
            text,
            len(text),
            RHVoice_message_type.text,
            byref(synth_params),
            None
        )
        if not message:
            raise RuntimeError('RHVoice: message building error')
        self._lib.RHVoice_speak(message)
        self._lib.RHVoice_delete_message(message)  # free the memory (check when message is stored)

    def set_params(self, **kw):
        self.params.update_from_dict(kw)

    def exterminate(self):
        if self._engine:
            self._lib.RHVoice_delete_tts_engine(self._engine)
            self._engine = None
            self.__save_me = None
