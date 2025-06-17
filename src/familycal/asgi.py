from collections import namedtuple
from io import RawIOBase
import json
import re
from types import SimpleNamespace
from typing import List, Union
from urllib.parse import unquote

from familycal.settings import config, logger


Route = namedtuple("Route", ["name", "pattern", "resolver"])

route_tables = {
    "__system__": [],
}

lifetime_begin_registry = []
lifetime_end_registry = []


def sys_route(name, pattern):
    def decorator(func):
        route_tables["__system__"].append(Route(name, pattern, func))
        return func
    return decorator


def run_at_startup():
    def decorator(func):
        lifetime_begin_registry.append(func)
        return func
    return decorator


def run_at_shutdown():
    def decorator(func):
        lifetime_end_registry.append(func)
        return func
    return decorator


class FamilyCalConnectionClosed(OSError):
    pass


class Response(SimpleNamespace):
    def __init__(self, status: int, headers: List[List[str]], body: Union[bytes, RawIOBase], **kwargs):
        kwargs.update(dict(
            status=status,
            headers=headers,
            body=body,
        ))
        super().__init__(**kwargs)


def plaintext_response(status: int, extra_headers: List[List[str]], body: bytes) -> Response:
    headers = [
        ["Content-Type", "text/plain"],
    ]
    headers.extend(extra_headers)
    return Response(status=status, headers=headers, body=body)


def html_response(status: int, extra_headers: List[List[str]], body: str) -> Response:
    headers = [
        ["Content-Type", "text/html"],
    ]
    headers.extend(extra_headers)
    return Response(status=status, headers=headers, body=body.encode("utf-8"))


def json_response(status: int, extra_headers: List[List[str]], body: dict) -> Response:
    headers = [
        ["Content-Type", "application/json"],
    ]
    headers.extend(extra_headers)
    return Response(status=status, headers=headers, body=json.dumps(body).encode("utf-8"))


async def respond(send, status=200, headers=None, body=None):
    """form and send a complete asgi response.

    Args:
        send: asgi send method

    Kwargs:
        status (int): http response status code
        headers (List[List[str]]): a list of 2-length lists like [name, value]
        body (Union[bytes, RawIOBase]): complete set of bytes to respond with,
            or an object that acts like a RawIOBase

    """

    start = {
        "type": "http.response.start",
        "status": status,
        "headers": headers or [],
        "trailers": False,
    }
    try:
        await send(start)
    except Exception:
        logger.error("something happened while starting to send...", exc_info=True)
        raise FamilyCalConnectionClosed()

    respbody = {
        "type": "http.response.body",
        "body": b"",
        "more_body": False,
    }

    # with bytes, we can just send the whole thing all at once
    if isinstance(body, bytes) and body is not None:
        respbody["body"] = body

    # with an RawIOBase (unbuffered IO), we're saying we need to stream the response in
    # chunks of body back to the client
    elif isinstance(body, RawIOBase):
        # the first http.response.body will be empty,
        # but indicate more chunks are coming
        respbody["more_body"] = True

    # send the initial chunk (maybe the only chunk)
    try:
        await send(respbody)
    except Exception:
        logger.error("something happened while sending...", exc_info=True)
        raise FamilyCalConnectionClosed()

    # send any additional chunks needed to be streamed back -- we can assume
    # the body type is RawIOBase
    if respbody["more_body"]:
        chunk_size = config.get("app", {}).get("response_chunk_size", 1024)
        def getchunk():
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            return None

        try:
            for chunk in getchunk():
                respbody["body"] = chunk
                try:
                    await send(respbody)
                except Exception:
                    logger.error("something happened while sending...", exc_info=True)
                    raise FamilyCalConnectionClosed()

            # close up the stream
            try:
                respbody["body"] = b""
                respbody["more_body"] = False
                await send(respbody)
            except Exception:
                logger.error("something happened while sending...", exc_info=True)
                raise FamilyCalConnectionClosed()

        finally:
            body.close()


async def application(scope, receive, send, lifetime_begin, lifetime_end, resolve_request):
    if scope["type"] == "lifespan":
        # this is an implementation suggested in the docs/spec -- basically
        # loops forever, but really just waits to receive a lifespan in
        # this call to application()
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                # Stuff to run before server startup
                # ----->
                await lifetime_begin()
                # <-----

                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                # Stuff to run after server shutdown
                # ----->
                await lifetime_end()
                # <-----

                await send({"type": "lifespan.shutdown.complete"})
                return

    # we're not supporting websockets, or anything that may be added to
    # the asgi spec, except http
    elif scope["type"] != "http":
        logger.error(f"non-supported connection type ('{scope['type']}'), responding with 501")
        await respond(send, status=501)
        return

    event = await receive()
    if event["type"] == "http.disconnect":
        return

    await resolve_request(scope, send)


async def resolve_systempath(scope: dict, path: str) -> Response:
    for route in route_tables["__system__"]:
        matches = re.match(route.pattern, path)
        if matches is not None:
            return await route.resolver(scope)
            break

    return plaintext_response(404, [], b"not found")


async def resolver(scope, send) -> Response:
    path = unquote(scope["path"])
    system_index_re = r"^(?P<systempath>\/[\w\-\._~!$&'\(\)\*\+,;=:@\/%]*)$"

    matches = re.match(system_index_re, path)
    if matches is not None:
        systempath = matches.group("systempath")
        resp = await resolve_systempath(scope, systempath)
        await respond(send, **resp.__dict__)
        return

    await respond(send, **plaintext_response(404, [], b'not found').__dict__)


async def lifetime_begin():
    for func in lifetime_begin_registry:
        await func()


async def lifetime_end():
    for func in lifetime_end_registry:
        await func()


async def app(scope, receive, send):
    await application(scope, receive, send, lifetime_begin, lifetime_end, resolver)


