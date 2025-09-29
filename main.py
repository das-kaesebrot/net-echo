import datetime
from typing import Union
from zoneinfo import ZoneInfo
from pydantic import BaseModel
import ipaddress
import os
import socket
import whoisit
from copy import deepcopy
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from ipaddress import IPv4Address, IPv6Address

site_emoji = "🌐"
site_title = "net-echo"

ENV_PREFIX = "NET_ECHO"
version = os.getenv("APP_VERSION", "local-dev")
header_client_port = os.getenv(f"{ENV_PREFIX}_HEADER_CLIENT_PORT", "X-Client-Port")
header_http_version = os.getenv(f"{ENV_PREFIX}_HEADER_HTTP_VERSION", "X-Http-Version")
header_transport_protocol = os.getenv(f"{ENV_PREFIX}_HEADER_TRANSPORT_PROTOCOL", "X-Transport-Protocol")
header_request_time = os.getenv(f"{ENV_PREFIX}_REQUEST_TIME", "X-Request-Time")

version = os.getenv("APP_VERSION", "local-dev")
app = FastAPI(title=site_title)
app.mount("/static", StaticFiles(directory="resources/static"), name="static")
templates = Jinja2Templates(directory="resources/templates")

SUPPORTED_REQUEST_METHODS = ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"]

whoisit.bootstrap()

class AddressInfo(BaseModel):
    ip: str
    ip_version: int
    reverse_dns: str | None = None
    reverse_pointer: str
    ip_info_url: str | None = None
    country: str | None = None
    registrant: str | None = None
    entity_name: str | None = None
    description: str | None = None
    
class HttpInfo(BaseModel):
    method: str
    version: str
    headers: dict[str, str]
    body: str
    is_https: bool
    transport_protocol: str
    url: str
    path: str
    query: str = None

class RequestInfo(BaseModel):
    address_info: AddressInfo
    http_info: HttpInfo | None = None
    request_hostname: str | None
    client_port: int
    scheme: str
    request_time: datetime.datetime


class FaviconResponse(Response):
    media_type = "image/svg+xml"
    
def try_parse_ip_address(ip_addr: str) -> Union[IPv4Address, IPv6Address, None]:
    try:
        parsed_ip = ipaddress.ip_address(ip_addr)
        return parsed_ip
    except ValueError:
        return None
    
async def get_request_info(request: Request, fill_http_info: bool = True) -> RequestInfo:
    request_hostname = request.url.hostname
    headers = dict(request.headers)
    
    is_https = request.url.scheme == "https"
    
    client_ip = ipaddress.ip_address(request.client.host)
    client_reverse_dns = socket.getfqdn(socket.getnameinfo((str(client_ip), 0), 0)[0])
    if client_reverse_dns.strip() == str(client_ip):
        client_reverse_dns = None # set none if we didn't actually get a reverse dns record back
    
    http_version = headers.get(header_http_version.lower(), request.scope.get("http_version"))
    client_port = request.client.port if request.client.port != 0 else headers.get(header_client_port.lower(), 0)
    transport_protocol = headers.get(header_transport_protocol.lower(), "tcp").lower() # TODO
    request_time = headers.get(header_request_time.lower())
    
    tz = ZoneInfo(os.getenv("TZ", "Europe/Berlin"))
    if not request_time: request_time = datetime.datetime.now(tz)
    else: request_time = datetime.datetime.fromisoformat(request_time).astimezone(tz)
    
    headers_copy = deepcopy(headers)
    for header in headers:
        if header.lower().startswith("x-"):
            headers_copy.pop(header)
            
    headers = headers_copy
    
    client_ip_info = None
    if client_ip.is_global:
        client_ip_info = (await whoisit.ip_async(client_ip, allow_insecure_ssl=True))

    host_info = RequestInfo(
        address_info=AddressInfo(
            ip=str(client_ip),
            ip_version=client_ip.version,
            reverse_dns=client_reverse_dns,
            reverse_pointer=client_ip.reverse_pointer,
            ip_info_url=client_ip_info.get("url") if client_ip_info else None,
            country=client_ip_info.get("country") if client_ip_info else None,
            entity_name=client_ip_info.get("name") if client_ip_info else None,
            registrant=client_ip_info.get("entities").get("registrant")[0].get("name") if client_ip_info else None,
            description=" ".join(client_ip_info.get("description", [])) if client_ip_info else None,
        ),
        client_port=client_port,
        request_hostname=request_hostname,
        scheme=request.url.scheme,
        request_time=request_time,
    )
    
    if fill_http_info:
        host_info.http_info = HttpInfo(
            method=request.method,
            version=http_version,
            headers=headers,
            body=await request.body(),
            is_https=is_https,
            transport_protocol=transport_protocol,
            url=str(request.url),
            path=request.url.path,
            query=request.url.query,
        )
    
    return host_info

api_router = APIRouter(tags=["api"])
view_router = APIRouter(tags=["view"], default_response_class=HTMLResponse)


@view_router.get("/favicon.ico", response_class=FaviconResponse)
async def get_favicon():
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        + f'<text y=".9em" font-size="90">{site_emoji}</text>'
        + "</svg>"
    )


@view_router.api_route("/", methods=SUPPORTED_REQUEST_METHODS, response_class=HTMLResponse)
async def get_root_view(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="main.j2",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "request_info": await get_request_info(request),
        },
    )
    

@view_router.get("/plain", response_class=PlainTextResponse)
async def get_plain_ip(request: Request):
    return request.client.host

@api_router.api_route("", methods=SUPPORTED_REQUEST_METHODS)
async def get_api_root(request: Request, http_info: bool = False) -> RequestInfo:
    if request.method == "HEAD":
        return
    
    return await get_request_info(request, fill_http_info=http_info)

app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)
