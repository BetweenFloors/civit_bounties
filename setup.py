from setuptools import setup, find_packages

setup(
    name="civitai",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["requests>=2.28"],
    python_requires=">=3.10",
    entry_points={"console_scripts": ["civitai=civitai.cli:main"]},
)
