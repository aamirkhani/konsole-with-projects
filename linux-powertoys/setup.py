from setuptools import setup, find_packages

setup(
    name="linux-powertoys",
    version="1.0.0",
    description="A Linux port of Microsoft PowerToys",
    author="Linux PowerToys Contributors",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "Pillow",
    ],
    extras_require={
        "dev": ["pytest"],
    },
    entry_points={
        "console_scripts": [
            "linux-powertoys=powertoys.__main__:main",
        ],
    },
)
