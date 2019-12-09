import setuptools

with open('xows/version.py') as fh:
    exec(fh.read())

setuptools.setup(
    name="xows",
    version=__version__,
    author="Morten Minde Neergaard",
    author_email="mneergaa@cisco.com",
    description="XoWS library / cli tool",
    license="MIT",
    keywords="websocket jsonrpc",
    url="https://github.com/cisco-ce/pyxows",
    python_requires='>=3.7',
    install_requires=[
        "aiohttp >= 3.1",
        "click >= 6.0",
    ],
    packages=['xows'],
    entry_points={
        'console_scripts': ['clixows=xows.__main__:cli'],
    },
    long_description="Library xows contains XoWSClient, script is called clixows",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Programming Language :: Python :: 3",
        "Topic :: Utilities",
        "Framework :: asyncio",
    ],
)
