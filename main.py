from pydantic import BaseModel
import ipaddress
import os
import socket
import whoisit
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

site_emoji = "📟"
site_title = "Net tester"
version = os.getenv("APP_VERSION", "local-dev")
app = FastAPI(title=site_title)
app.mount("/static", StaticFiles(directory="resources/static"), name="static")
templates = Jinja2Templates(directory="resources/templates")

SUPPORTED_REQUEST_METHODS = ["GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"]

class AddressInfo(BaseModel):
    ip: str
    hostname: str
    port: int
    whois_url: str = None
    
class HttpInfo(BaseModel):
    method: str
    version: str
    headers: dict[str, str]
    body: str

class RequestInfo(BaseModel):
    client_info: AddressInfo
    server_info: AddressInfo
    http_info: HttpInfo
    request_hostname: str
    request_url: str
    request_path: str
    request_query: str = None
    ip_version: int
    scheme: str


class FaviconResponse(Response):
    media_type = "image/svg+xml"

async def get_request_info(request: Request) -> RequestInfo:
    request_hostname = request.url.hostname
    client_ip = ipaddress.ip_address(request.client.host)
    try:
        server_ip = ipaddress.ip_address(request_hostname)
        pass
    except ValueError:
        # the request was sent using a DNS name in the url
        response = socket.getaddrinfo(request_hostname, family=(socket.AF_INET if client_ip.version == 4 else socket.AF_INET6), port=0)[0]
        server_ip = ipaddress.ip_address(response[4][0])

    server_hostname = socket.getfqdn(socket.getnameinfo((str(server_ip), 0), 0)[0])

    host_info = RequestInfo(
        client_info=AddressInfo(
            ip=request.client.host,
            hostname=socket.getfqdn(socket.getnameinfo((request.client.host, 0), 0)[0]),
            port=request.client.port
        ),
        server_info=AddressInfo(
            ip=str(server_ip),
            hostname=server_hostname,
            port=request.url.port,
        ),
        http_info=HttpInfo(
            method=request.method,
            version=request.scope.get("http_version"),
            headers=request.headers,
            body=await request.body(),
        ),
        request_hostname=request_hostname,
        ip_version=client_ip.version,
        scheme=request.url.scheme,
        request_url=str(request.url),
        request_path=request.url.path,
        request_query=request.url.query
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
