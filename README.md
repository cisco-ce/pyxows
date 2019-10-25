# Cisco Telepresence XAPI over WebSockets, python library.

Python version required: 3.7 or newer.


## Description

This library allows you to connect to a Cisco Telepresence endpoint running CE
software version 9.7 or later using jsonrpc over websocket. There is also a
command-line utility built on top of the library.


## Installing

    python setup.py install [--user]

## Requirements

Websockets should be set to `FollowHTTPService` and HTTP Mode should be set to either `HTTPS` or `HTTP/HTTPS`. 

## Usage example

```py
import xows
import asyncio

async def start():
    async with xows.XoWSClient('10.10.10.1', username='admin1', password='') as client:
        def callback(data, id_):
            print(f'Feedback (Id {id_}): {data}')

        print('Status Query:',
            await client.xQuery(['Status', '**', 'DisplayName']))

        print('Get:',
            await client.xGet(['Status', 'Audio', 'Volume']))

        print('Command:',
              await client.xCommand(['Audio', 'Volume', 'Set'], Level=60))

        print('Configuration:',
            await client.xSet(['Configuration', 'Audio', 'DefaultVolume'], 50))

        print('Subscription 0:',
            await client.subscribe(['Status', 'Audio', 'Volume'], callback, True))

        await client.wait_until_closed()

asyncio.run(start())
```

For more usage examples, check out the clixows script. It's source is found
under `xows/__main__.py` and it can be invoked using `python3 -m xows`, or,
after install, as `clixows`

Note that piping output from python scripts to other commands doesn't work well
unless you switch to unbuffered output, so e.g. if you want timestamping using
`ts(1)` you need to do e.g.

    python3 -u -m xows my-endpoint feedback '**' | ts
