# pytask
# File: setup.py
# Desc: needed

from setuptools import setup


setup(
    version='1.1dev0',
    name='pytask',
    description='A simple gevent Python task runner',
    author='Nick Barrett @ Oxygem',
    author_email='nick@oxygem.com',
    url='http://github.com/Oxygem/pytask',
    packages=('pytask',),
    package_dir={'pytask': 'pytask'},
    install_requires=(
        'gevent',
        'redis>=2.10'
    )
)
