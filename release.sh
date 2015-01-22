#!/bin/sh

VERSION=`python setup.py --version`

echo "# Releasing pytask v$VERSION"

echo "# Git tag & push..."
git tag -a "v$VERSION" -m "v$VERSION"
git push --tags

echo "# Publishing to pypi
python setup.py sdist upload

echo "# Done!"

