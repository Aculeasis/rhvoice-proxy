# Docs https://docs.github.com/en/rest/reference/repos#releases

import urllib.request
import urllib.error
import json
import sys
import operator

ENDPOINT = 'https://api.github.com/repos/Aculeasis/rhvoice-wrapper-bin/releases'
OSES = {
    'ubuntu-20.04': 'linux',
    'windows-2019': 'win'
}

ARCH = {
    'win': {
        'x86': '32',
        'x64': '_amd64'
    },
    'linux': {
        'x86': '_i686',
        'x64': '_x86_64'
    }
}


def get_release_dict():
    response = urllib.request.urlopen(
        urllib.request.Request(url=ENDPOINT, headers={'Accept': 'application/vnd.github.v3+json'})
    )
    if response.getcode() != 200:
        raise RuntimeError('Request code error: {}'.format(response.getcode()))
    return json.loads(response.read().decode('utf-8'))


def prepare_release():
    result = dict()
    for release in get_release_dict():
        tag_name = release.get('tag_name')
        if tag_name:
            result[tag_name] = [x.get('browser_download_url', '') for x in release.get('assets', [])]
    return sorted(result.items(), key=operator.itemgetter(0), reverse=True)


def make_tail(os: str, arch: str):
    os = OSES[os or 'ubuntu-20.04']
    arch = ARCH[os][arch or 'x64']
    return '-py3-none-{os}{arch}.whl'.format(os=os, arch=arch)


def get_url():
    arch = sys.argv[2] if len(sys.argv) >= 3 else ''
    os = sys.argv[1] if len(sys.argv) >= 2 else ''
    tail = make_tail(os, arch)
    for _, targets in prepare_release():
        for target in targets:
            if target.endswith(tail):
                return target


if __name__ == '__main__':
    print(get_url())
