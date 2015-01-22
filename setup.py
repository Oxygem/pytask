#!/usr/bin/env python

# File: setup.py
# Desc: needed

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    version = '1.0.0',
    name = 'pytask',
    description = 'A simple Python based task runner',
    author = 'Nick Barrett',
    author_email = 'nick@oxygem.com',
    url = 'http://github.com/Fizzadar/pytask',
    py_modules = ['pytask']
)
