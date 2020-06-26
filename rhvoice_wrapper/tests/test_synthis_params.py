import unittest

from rhvoice_wrapper import rhvoice_bindings
from rhvoice_wrapper import rhvoice_proxy

SUPPORT_TUPLE = tuple(tuple(int(x) for x in k.split('.')) for k in rhvoice_proxy.SUPPORT)


def synth_params_keys(api: tuple):
    # noinspection PyProtectedMember
    for key, _ in rhvoice_bindings.RHVoice_synth_params(api)._fields_:
        yield key


class SynthesisParams(unittest.TestCase):
    def test_orphan_fields(self):
        all_fields = {key for api in SUPPORT_TUPLE for key in synth_params_keys(api)}
        all_checks = {key for key in rhvoice_proxy.SynthesisParams.CHECKS}

        self.assertSetEqual(all_fields, all_checks)

    def _test_fields(self, api: tuple):
        for key in synth_params_keys(api):
            self.assertTrue(key in rhvoice_proxy.SynthesisParams.CHECKS, 'field {} miss'.format(repr(key)))

    def _test_api(self, api: tuple):
        dict_standard = rhvoice_proxy.SynthesisParams(api).\
            copy_with({'absolute_volume': rhvoice_proxy.SynthesisParams.MIN_BASE}).to_dict()
        param = rhvoice_proxy.SynthesisParams(api, dict_standard)

        dict_eq = param.copy_with({'mismismis': 'FAILLANGUAGE'}).to_dict()
        dict_ne1 = param.copy_with({'voice_profile': 'FAILLANGUAGE'}).to_dict()
        dict_ne2 = rhvoice_proxy.SynthesisParams(api).to_dict()

        self.assertDictEqual(dict_standard, dict_eq)
        self.assertNotEqual(dict_standard, dict_ne1)
        self.assertNotEqual(dict_standard, dict_ne2)

    def _test_api_diff(self, api1: tuple, api2: tuple):
        dict1 = rhvoice_proxy.SynthesisParams(api1).to_dict()
        dict2 = rhvoice_proxy.SynthesisParams(api2).to_dict()

        self.assertNotEqual(api1, api2)
        self.assertNotEqual(dict1, dict2)


def _make():
    def str_ver(api_: tuple):
        return ''.join(str(x) for x in api_)

    for api in SUPPORT_TUPLE:
        def fun_api(self):
            # noinspection PyProtectedMember
            SynthesisParams._test_api(self, api)

        def fun_field(self):
            # noinspection PyProtectedMember
            SynthesisParams._test_fields(self, api)
        version = str_ver(api)
        setattr(SynthesisParams, 'test_fields_{}'.format(version), fun_field)
        setattr(SynthesisParams, 'test_api_{}'.format(version), fun_api)

    api_start = SUPPORT_TUPLE[0]
    api_end = SUPPORT_TUPLE[-1]

    def fun_diff(self):
        # noinspection PyProtectedMember
        SynthesisParams._test_api_diff(self, api_start, api_end)
    setattr(SynthesisParams, 'test_api_diff_{}_{}'.format(str_ver(api_start), str_ver(api_end)), fun_diff)


_make()
