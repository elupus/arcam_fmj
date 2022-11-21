from setuptools import find_packages, setup

# read the contents of your README file
from os import path

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="arcam-fmj",
    version="1.0.1",
    description="A python library for speaking to Arcam receivers",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    license="MIT",
    packages=["arcam.fmj"],
    package_dir={"": "src"},
    package_data = {
        'arcam.fmj': ['py.typed'],
    },
    python_requires=">=3.8",
    author="Joakim Plate",
    install_requires=["attrs>18.1"],
    extras_require={
        "tests": [
            "pytest>3.6.4",
            "pytest-asyncio",
            "pytest-aiohttp>=1.0.0",
            "pytest-cov>=3.0.0",
            "coveralls",
            "pytest-mock",
            "aiohttp",
            "defusedxml"
        ]
    },
    entry_points={"console_scripts": ["arcam-fmj=arcam.fmj.console:main"]},
    url="https://github.com/elupus/arcam_fmj",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Environment :: Plugins",
        "Framework :: AsyncIO",
    ],
)
