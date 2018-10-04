from setuptools import setup

with open('README.md') as fh:
    long_description = fh.read()

setup(
    name='rhvoice-wrapper',
    version='0.1.1',
    packages=['rhvoice_wrapper'],
    url='https://github.com/Aculeasis/rhvoice-proxy',
    license='GPLv3+',
    author='Aculeasis',
    author_email='amilpalimov2@ya.ru',
    description='High-level interface for RHVoice library',
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires='>=3',
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Operating System :: OS Independent',
        'Topic :: Multimedia :: Sound/Audio :: Speech',
        'Topic :: Software Development :: Libraries',
    ],
)
