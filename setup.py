#!/usr/bin/env python

# File: setup.py
# Desc: needed

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(
    version='1.0.2',
    name='pytask',
    description='A simple Python based task runner',
    author='Nick Barrett',
    author_email='nick@oxygem.com',
    url='http://github.com/Oxygem/pytask',
    py_modules=['pytask']
)
