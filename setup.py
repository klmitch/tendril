#!/usr/bin/env python

from setuptools import setup

def readfile(filename):
    with open(filename) as f:
        return f.read()

setup(
    name='Tendril',
    version='0.1.0',
    author='Kevin L. Mitchell',
    author_email='klmitch@mit.edu',
    url='http://github.com/klmitch/tendril',
    description='Frame-based Network Connection Tracker',
    long_description=readfile('README.rst'),
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python',
        ],
    packages=['tendril'],
    requires=[
        "gevent",
        "netaddr",
        "pkg_resources",
        ],
    tests_require=[
        "mock>=1.0b1",
        ],
    entry_points={
        'tendril.manager': [
            'tcp = tendril.tcp:TCPTendrilManager',
            ],
        },
    )
