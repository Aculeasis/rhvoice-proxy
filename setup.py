from setuptools import setup

with open('README.md') as fh:
    long_description = fh.read()

with open('version') as fh:
    version = fh.read().splitlines()[0]

setup(
    name='rhvoice-wrapper',
    version=version,
    packages=['rhvoice_wrapper'],
    url='https://github.com/Aculeasis/rhvoice-proxy',
    license='GPLv3+',
    author='Aculeasis',
    author_email='amilpalimov2@ya.ru',
    description='High-level interface for RHVoice library',
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires='>=3.4',
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Topic :: Multimedia :: Sound/Audio :: Speech',
        'Topic :: Software Development :: Libraries',
    ],
)
