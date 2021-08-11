import subprocess

from setuptools import setup


def get_version() -> str:
    version_file = 'version'

    def version_to_file(ver):
        with open(version_file, mode='w') as fd:
            fd.write(ver)

    def version_from_file():
        with open(version_file) as fd:
            return fd.read().splitlines()[0]

    def version_from_git():
        cmd = ['git', 'describe', '--abbrev=0', '--tags']
        try:
            return subprocess.check_output(cmd).decode().splitlines()[0]
        except Exception as e:
            print('ERROR! Execute {}: {}'.format(cmd, e))
            return None
    version = version_from_git()
    if not version:
        version = version_from_file()
        print('WARNING! Get version from a file: {}'.format(version))
    else:
        version_to_file(version)
    return version


def get_long_description():
    with open('README.md') as fh:
        return fh.read()


setup(
    name='rhvoice-wrapper',
    version=get_version(),
    packages=['rhvoice_wrapper'],
    url='https://github.com/Aculeasis/rhvoice-proxy',
    license='GPLv3+',
    author='Aculeasis',
    author_email='amilpalimov2@ya.ru',
    description='High-level interface for RHVoice library',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    python_requires='>=3.6',
    extras_require={
        'rhvoice': ['rhvoice-wrapper-bin'],
    },
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Topic :: Multimedia :: Sound/Audio :: Speech',
        'Topic :: Software Development :: Libraries',
    ],
)
