from setuptools import setup, find_packages
from pkg_resources import parse_version
import glob
import os
here = os.path.abspath(os.path.dirname(__file__))

import sys
if sys.version_info[:2] < (2, 6) or (3, 0) <= sys.version_info[0:2] < (3, 2):
    raise RuntimeError("Python version 2.6, 2.7 or >= 3.2 required.")

# Get the long description from the relevant file
with open(os.path.join(here, 'README.rst')) as f:
    long_description = f.read()

# Get the version from the relevant file
with open(os.path.join(here, 'modred/_version.py')) as f:
    exec(f.read())
# Get the development status from the version string
parsed_version = parse_version(__version__)
if any(w in ['*a', '*alpha'] for w in parsed_version):
    devstatus = 'Development Status :: 3 - Alpha'
elif any(w in ['*b', '*beta'] for w in parsed_version):
    devstatus = 'Development Status :: 4 - Beta'
else:
    devstatus = 'Development Status :: 5 - Production/Stable'

OKID_test_data_files = list()
for c in ['SISO', 'SIMO', 'MISO', 'MIMO']:
    OKID_test_data_files.append((os.path.join('modred', 'tests', 'OKID_files' , c), 
        glob.glob(os.path.join('modred', 'tests', 'OKID_files', c, '*'))))
setup(
    name='modred',
    version=__version__,
    description=(
        'Compute modal decompositions and reduced-order models, '
        'easily, efficiently, and in parallel.'),
    # long_description=long_description,
    # keywords='',
    author=('Brandt Belson, Jonathan Tu, and Clancy Rowley;'
            'ported for Python 3 by Pierre Augier'),
    author_email=(
        'brandt.belson@gmail.com, jonathantu@gmail.com, cwrowley@princeton.edu'),
    url='https://pythonhosted.org/modred',
    maintainer=('Brandt Belson, Jonathan Tu, and Clancy Rowley;'
            'ported for Python 3 by Pierre Augier'),
    maintainer_email='brandt.belson@gmail.com',
    license='Free BSD',
    classifiers=[
        # How mature is this project? Common values are
        # 3 - Alpha
        # 4 - Beta
        # 5 - Production/Stable
        devstatus,
        'Intended Audience :: Science/Research',
        'Intended Audience :: Education',
        'Topic :: Scientific/Engineering',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4'
        ],
    packages=find_packages(exclude=['doc', 'matlab']),
    data_files=OKID_test_data_files,
    install_requires=['numpy', 'future']
    )
