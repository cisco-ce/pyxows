#!/usr/bin/env python3

"Command-line tool based on pyxows."


import asyncio
import functools
import pprint

import click

import xows


def wrap_cli(fun):
    'Wraps calls in an async with XoWSClient + async.run'

    async def wrapper(obj, *args, **kwargs):
        async with obj as client:
            await fun(client, *args, **kwargs)
    def run_wrapper(*args, **kwargs):
        asyncio.run(wrapper(*args, **kwargs))

    return functools.update_wrapper(run_wrapper, fun)


def _coerce_list(path):
    ret = []
    for part in path:
        if part.startswith('/'):
            part = part[1:]
        for p in part.split('/'):
            if p:
                ret.append(p)
            elif ret and ret[-1] != '**':
                ret.append('**')
    return [int(part) if part.isnumeric() else part
            for part in ret]


def coerce_list(arg_name):
    def coerced(fun):
        def wrapper(*args, **kwargs):
            kwargs[arg_name] = _coerce_list(kwargs.pop(arg_name))
            return fun(*args, **kwargs)
        return functools.update_wrapper(wrapper, fun)
    return coerced


@click.group()
@click.version_option(xows.__version__)
@click.argument('host_or_url',)
@click.option('-u', '--username', default='admin', show_default=True)
@click.option('-p', '--password', default='', show_default=True)
@click.pass_context
def cli(ctx, host_or_url, username, password):
    """First argument is hostname, or url (e.g. ws://example.host/ws)

    Usage examples:

    clixows ws://example.codec/ws get Status SystemUnit Uptime

    clixows example.codec set Configuration Audio Ultrasound MaxVolume 70

    clixows example.codec command Phonebook Search Limit=1 Offset=0

    clixows example.codec feedback -c '**'
    """

    ctx.obj = xows.XoWSClient(host_or_url, username, password)


@cli.command()
@click.pass_obj
@wrap_cli
async def demo(client):
    "Runs a quick demo, read source to see possibilities here."

    def callback(data, id_):
        print(f'Ultrasound change, Id = {id_}: {data}')

    print('Get SystemUnit Name:',
          await client.xGet(['Configuration', 'SystemUnit', 'Name']))

    print('Subscribe ultrasound: Id =',
          await client.subscribe(['Configuration', 'Audio', 'Ultrasound'], callback, True))

    print('Change Ultrasound (1):',
          await client.xSet(['Configuration', 'Audio', 'Ultrasound', 'MaxVolume'], 69))

    print('Change Ultrasound (2):',
          await client.xSet(['Configuration', 'Audio', 'Ultrasound', 'MaxVolume'], 70))

    print('Phonebook Search Command:',
          await client.xCommand(['Phonebook', 'Search'], Limit=1))

    print('Bulk processing...')
    # Truly and very async =)
    for task in asyncio.as_completed([
            asyncio.create_task(
                client.xCommand(['HttpClient', 'Post'],
                                Url='http://google.com/',
                                body=str(x)))
            for x in range(5)]):
        try:
            print(await task)
        except xows.CommandError as err:
            print(err)

@cli.command()
@click.argument('path', nargs=-1)
@coerce_list('path')
@click.pass_obj
@wrap_cli
async def get(client, path):
    "Get data from a config/status path."

    pprint.pprint(await client.xGet(path))

@cli.command()
@click.argument('query', nargs=-1)
@coerce_list('query')
@click.pass_obj
@wrap_cli
async def query(client, query):
    "Query config/status docs. Supports '**' as wildcard."

    pprint.pprint(await client.xQuery(query))

@cli.command()
@click.argument('path', nargs=-1)
@coerce_list('path')
@click.argument('value')
@click.pass_obj
@wrap_cli
async def set(client, path, value):
    "Set a single configuration."

    pprint.pprint(await client.xSet(path, value))

@cli.command()
@click.argument('params', nargs=-1)
@click.pass_obj
@wrap_cli
async def command(client, params):
    "Run a command. Example: command Phonebook Search Limit=1"

    command = []
    for param in params:
        if '=' in param:
            break
        command.append(param)
    command = _coerce_list(command)
    params = params[len(command):]
    try:
        params = dict(param.split('=', 1) for param in params)
    except ValueError:
        print('Command arguments must contain "="')
    else:
        pprint.pprint(await client.xCommand(command, **params))

@cli.command()
@click.argument('query', nargs=-1)
@coerce_list('query')
@click.option('-c', '--current-value/--no-current-value', default=False, show_default=True)
@click.pass_obj
@wrap_cli
async def feedback(client, query, current_value):
    "Listen for feedback on a particular query."

    def handler(feedback, id_):
        pprint.pprint(feedback)

    print('Subscription Id:', await client.subscribe(query, handler, current_value))

    await client.wait_until_closed()

if __name__ == '__main__':
    cli()
