# pytask
# File: docs/conf.py
# Desc: minimal Sphinx config

extensions = [
    # Official
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon'
]

source_suffix = '.rst'
master_doc = 'index'
project = 'pytask'
copyright = '2015, Nick Barrett (Oxygem)'
author = 'Fizzadar'
version = 'develop'
pygments_style = 'sphinx'
html_theme = 'sphinx_rtd_theme'
htmlhelp_basename = 'pyinfradoc'
