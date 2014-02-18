#!/usr/bin/env python

from setuptools import setup


def readreq(filename):
    result = []
    with open(filename) as f:
        for req in f:
            req = req.lstrip()
            if req.startswith('-e ') or req.startswith('http:'):
                idx = req.find('#egg=')
                if idx >= 0:
                    req = req[idx + 5:].partition('#')[0].strip()
                else:
                    pass
            else:
                req = req.partition('#')[0].strip()
            if not req:
                continue
            result.append(req)
    return result


def readfile(filename):
    with open(filename) as f:
        return f.read()


setup(
    name='Tendril',
    version='0.1.1',
    author='Kevin L. Mitchell',
    author_email='klmitch@mit.edu',
    url='http://github.com/klmitch/tendril',
    description='Frame-based Network Connection Tracker',
    long_description=readfile('README.rst'),
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'Topic :: Software Development :: Libraries :: Python Modules',
        ],
    packages=['tendril'],
    install_requires=readreq('requirements.txt'),
    tests_require=readreq('test-requirements.txt'),
    entry_points={
        'tendril.manager': [
            'tcp = tendril.tcp:TCPTendrilManager',
            'udp = tendril.udp:UDPTendrilManager',
            ],
        },
    )
