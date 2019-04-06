from setuptools import find_packages, setup

setup(
    name='arcam-fmj',
    version='0.2.0',
    description='A python library for speaking to Arcam receivers',
    license='MIT',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    python_requires='>3.5',
    author='Joakim Plate',
    install_requires=[
        'asyncio',
        'attrs>18.1',
    ],
    extras_require={
        'tests': [
            'pytest>3.6.4',
            'pytest-asyncio',
            'pytest-cov<2.6',
            'coveralls'
        ]
    },
    entry_points={
        'console_scripts':['arcam-fmj=arcam.fmj.console:main']
    },
    url='https://github.com/elupus/arcam_fmj',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Plugins',
        'Framework :: AsyncIO',
    ]
)
