'Python library for connection to the Cisco Telepresence XAPI over WebSockets.'


import asyncio
import inspect

import aiohttp


from .version import __version__


class XoWSError(Exception):
    "Parent exception class for all XoWS errors."

class ConnectionClosed(XoWSError):
    "Connection closed unexpectedly."

class AuthenticationFailure(XoWSError):
    "Invalid username or password."

class NotEnabledError(XoWSError):
    "You may need to enable NetworkServices Websocket."

class HTTPNotEnabledError(XoWSError):
    "You may have connected to an HTTPS-only endpoint over HTTP"

class RateLimitError(XoWSError):
    "You have exceeded the codec connection rate limit."

class InvalidRequest(XoWSError):
    "The request was invalid or unsupported."

class MethodNotFound(XoWSError):
    "The supplied method doesn't exist."

class InvalidParameter(XoWSError):
    "A parameter was missing or invalid."

class InternalError(XoWSError):
    "Internal server error."

class ParseError(XoWSError):
    "Server couldn't parse the message."

class PermissionDenied(XoWSError):
    "Permission was denied for current user."

class SubscriberCountExceeded(XoWSError):
    "Global subscription count exceeded."

class NotReady(XoWSError):
    "System not ready to accept requests."

class CommandError(XoWSError):
    "Command returned an error."


EXCEPTION_TYPES = {
    -32600: InvalidRequest,
    -32601: MethodNotFound,
    -32602: InvalidParameter,
    -32603: InternalError,
    -32700: ParseError,
    -31999: PermissionDenied,
    -31998: SubscriberCountExceeded,
    -31997: NotReady,
    1: CommandError,
}


class XoWSClient:
    '''XoWSClient accepts three parameters; hostname / url is the first
    argument, and can be specified as e.g.

    endpoint
    endpoint.domain
    ws://endpoint/ws
    wss://endpoint/ws

    SSL verification is always disabled.

    Can be used as an async context manager.'''

    # pylint: disable=too-many-instance-attributes

    def __init__(self, url_or_host, username='admin', password=''):
        if 's://' in url_or_host:
            self._url = url_or_host
        else:
            self._url = f'wss://{url_or_host}/ws'
        self._auth = aiohttp.helpers.BasicAuth(username, password)
        self._id_counter = 0
        self._pending = {}
        self._feedback_handlers = {}

        self._session = self._client = self._closed = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *_):
        await self.disconnect()

    async def connect(self):
        '''Initializes the actual connection.

        You most likely want to use the class as an async context manager
        instead of calling connect() / disconnect().'''

        self._session = aiohttp.ClientSession()
        self._closed = asyncio.get_running_loop().create_future()
        error = None
        try:
            self._client = await self._session.ws_connect(self._url,
                                                          auth=self._auth,
                                                          ssl=False)
        except aiohttp.client_exceptions.ClientError as err:
            error = err
            await self._session.close()

        if error:
            if not hasattr(error, 'status'):
                raise ConnectionError(error)
            if error.status == 401 and self._url.startswith('ws:'):
                raise HTTPNotEnabledError(HTTPNotEnabledError.__doc__, error.status)
            if error.status == 403:
                raise AuthenticationFailure(AuthenticationFailure.__doc__, error.status)
            if error.status == 502:
                raise ConnectionError("Proxy error. Most likely cause for these is codec reboot.")
            if error.status == 503:
                raise RateLimitError(RateLimitError.__doc__, error.status)
            raise NotEnabledError(NotEnabledError.__doc__, error.status)
        asyncio.create_task(self._read_loop())

    async def send(self, message):
        "Sends data to server. message can be str, bytes, or json serializable."
        if isinstance(message, bytes):
            await self._client.send_bytes(message)
        else:
            if isinstance(message, str):
                await self._client.send_str(message)
            elif isinstance(message, bytes):
                await self._client.send_bytes(message)
            else:
                await self._client.send_json(message)

    @staticmethod
    def _make_exception(data):
        error = data.get('error', None)
        if error:
            code = error.get('code', None)
            exception = EXCEPTION_TYPES.get(code, XoWSError)
            message = error.get('message', exception.__doc__)
            if 'data' in error:
                return exception(message, error['data'])
            return exception(message)
        return None

    async def _api_call(self, method, **params):
        self._id_counter += 1
        req = {
            'jsonrpc': '2.0',
            'method': method,
            'id': self._id_counter,
            'params': params,
        }
        await self.send(req)
        future = asyncio.get_running_loop().create_future()
        self._pending[self._id_counter] = future
        return future

    async def api_call(self, method, **params):
        '''Performs a jsonrpc call, autogenerating an ID.

        Returns an awaitable for that specific request.'''

        future = await self._api_call(method, **params)
        return await future

    async def xGet(self, path):
        'Gets a value or subtree.'
        return await self.api_call('xGet', Path=path)

    async def xQuery(self, query):
        'Queries a tree.'
        return await self.api_call('xQuery', Query=query)

    async def xSet(self, path, value):
        'Sets a value. Returns True on success.'
        return await self.api_call('xSet', Path=path, Value=value)

    async def xCommand(self, command, **params):
        'Runs a command.'
        return await self.api_call('xCommand/' + '/'.join(command), **params)

    async def subscribe(self, query, handler, notify_current_value=False):
        '''Subcribes to a query, running handler whenever value changes.

        If notify_current_value is set to True, notifies the caller of current
        value for all matching nodes.

        Returns the ID of the subscription.'''

        future = await self._api_call('xFeedback/Subscribe',
                                      Query=query,
                                      NotifyCurrentValue=notify_current_value)
        def register_handler(fut):
            response = fut.result()
            self._feedback_handlers[response['Id']] = handler
        future.add_done_callback(register_handler)
        data = await future
        return data['Id']

    async def unsubscribe(self, id_):
        'Unsubscribes a specified feedback subscription.'
        return await self.api_call('xFeedback/Unsubscribe', Id=id_)

    async def _process(self, data):
        exception = self._make_exception(data)
        if 'id' in data:
            future = self._pending[data['id']]
            if exception:
                future.set_exception(exception)
            else:
                future.set_result(data['result'])
            await asyncio.wait([future])
        elif exception:
            raise exception
        else:
            assert data['method'] == 'xFeedback/Event'
            params = data['params']
            id_ = params.pop('Id')
            handler = self._feedback_handlers[id_]
            ret = handler(params, id_)
            if inspect.isawaitable(ret):
                asyncio.create_task(ret)

    async def _read_loop(self):
        while True:
            msg = await self._client.receive()
            if msg.type == aiohttp.WSMsgType.TEXT:
                await self._process(msg.json())
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                self._closed.set_result(None)
                break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                self._closed.set_exception(ConnectionClosed(ConnectionClosed.__doc__))
                break
            elif msg.type in (aiohttp.WSMsgType.CLOSING,):
                pass
            else:
                raise RuntimeError(f'Unhandled msg type {msg.type}')

    async def wait_until_closed(self):
        '''Waits until the server closes the connection.

        Useful in case of long-running feedback.

        Raises ConnectionClosed if there is a connection error, otherwise
        returns None.'''
        await self._closed

    async def disconnect(self):
        'Disconnect the session. See connect().'
        await self._client.close()
        await self._session.close()
