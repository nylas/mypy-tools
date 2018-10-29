from setuptools import setup

setup(name='mypytools',
      version='0.1.11',
      description='A bundle of tools to make using mypy easier',
      url='https://github.com/nylas/mypy-tools',
      license='MIT',
      install_requires=[
          'click',
          'findimports',
          'typing',
          'watchdog'
      ],
      packages=['mypytools', 'mypytools.server'],
      scripts=[
          'bin/check_mypy_annotations.py',
          'bin/mypy_server.py',
          'bin/print_mypy_coverage.py',
      ],
      zip_safe=False)
