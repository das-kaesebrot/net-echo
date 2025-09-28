import datetime
from pydantic import BaseModel
import ipaddress
import os
import socket
import whoisit
from copy import deepcopy
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

site_emoji = "🌐"
site_title = "NET ECHO"

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
    reverse_dns: str | None = None
    reverse_pointer: str
    port: int
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

class RequestInfo(BaseModel):
    client_info: AddressInfo
    server_info: AddressInfo
    http_info: HttpInfo
    request_hostname: str | None
    request_url: str
    request_path: str
    request_query: str = None
    ip_version: int
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
    
async def get_request_info(request: Request) -> RequestInfo:
    request_hostname = request.url.hostname
    headers = dict(request.headers)
    
    is_https = request.url.scheme == "https"
    
    client_ip = ipaddress.ip_address(request.client.host)
    server_ip = try_parse_ip_address(request_hostname)
    if not server_ip:
        # the request was sent using a DNS name in the url
        response = socket.getaddrinfo(request_hostname, family=(socket.AF_INET if client_ip.version == 4 else socket.AF_INET6), port=0)[0]
        server_ip = ipaddress.ip_address(response[4][0])

    server_hostname = socket.getfqdn(socket.getnameinfo((str(server_ip), 0), 0)[0])
    
    http_version = headers.get(header_http_version.lower(), request.scope.get("http_version"))
    client_port = request.client.port if request.client.port != 0 else headers.get(header_client_port.lower(), 0)
    transport_protocol = headers.get(header_transport_protocol.lower(), "tcp").lower() # TODO
    request_time = headers.get(header_request_time.lower())
    
    if not request_time: request_time = datetime.datetime.utcnow()
    else: request_time = datetime.datetime.fromisoformat(request_time)
    
    headers_copy = deepcopy(headers)
    for header in headers:
        if header.lower().startswith("x-"):
            headers_copy.pop(header)
            
    headers = headers_copy
    
    client_ip_info = {}
    if client_ip.is_global:
        client_ip_info = (await whoisit.ip_async(client_ip, allow_insecure_ssl=True))
    
    server_ip_info = {}
    if server_ip.is_global:
        server_ip_info = (await whoisit.ip_async(server_ip, allow_insecure_ssl=True))

    host_info = RequestInfo(
        client_info=AddressInfo(
            ip=request.client.host,
            hostname=socket.getfqdn(socket.getnameinfo((request.client.host, 0), 0)[0]),
            port=client_port,
            ip_info_url=client_ip_info.get("url"),
            country=client_ip_info.get("country"),
            registrant=client_ip_info.get("description")[0],
        ),
        server_info=AddressInfo(
            ip=str(server_ip),
            hostname=server_hostname,
            port=request.url.port if request.url.port else (443 if is_https else 80),
            ip_info_url=server_ip_info.get("url"),
            country=server_ip_info.get("country"),
            entity=server_ip_info.get("description")[0],
        ),
        http_info=HttpInfo(
            method=request.method,
            version=http_version,
            headers=headers,
            body=await request.body(),
            is_https=is_https,
            transport_protocol=transport_protocol,
        ),
        request_hostname=request_hostname,
        ip_version=client_ip.version,
        scheme=request.url.scheme,
        request_url=str(request.url),
        request_path=request.url.path,
        request_query=request.url.query,
        request_time=request_time,
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

@api_router.api_route("/", methods=SUPPORTED_REQUEST_METHODS)
async def get_api_root(request: Request):
    if request.method == "HEAD":
        return
    
    return await get_request_info(request)

app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)
