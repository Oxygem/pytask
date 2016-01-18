# pytask
# File: setup.py
# Desc: needed

from setuptools import setup


setup(
    version='1.0.2',
    name='pytask',
    description='A simple Python based task runner',
    author='Nick Barrett',
    author_email='nick@oxygem.com',
    url='http://github.com/Oxygem/pytask',
    packages=('pytask',),
    package_dir={'pytask': 'pytask'},
    install_requires=(
        'gevent',
    )
)
