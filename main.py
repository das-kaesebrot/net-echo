from dataclasses import dataclass, asdict
from pydantic import BaseModel
from starlette.datastructures import URL
import ipaddress
import os
import socket
import json
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


class HostInfo(BaseModel):
    client_ip: str
    client_hostname: str
    client_port: int
    server_ip: str
    server_hostname: str
    server_port: int
    request_hostname: str
    request_url: URL
    method: str
    http_version: str
    ip_version: int
    scheme: str
    headers: dict[str, str]

    def as_dict(self):
        return asdict(self)
    
    def as_json(self):
        return json.dumps(self.as_dict(), indent=4, sort_keys=True)


class FaviconResponse(Response):
    media_type = "image/svg+xml"

def get_host_info(request: Request) -> HostInfo:
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

    host_info = HostInfo(
        client_ip=request.client.host,
        client_hostname=socket.getfqdn(socket.getnameinfo((request.client.host, 0), 0)[0]),
        client_port=request.client.port,
        server_ip=str(server_ip),
        server_hostname=server_hostname,
        server_port=request.url.port,
        request_hostname=request_hostname,
        method=request.method,
        http_version=request.scope.get("http_version"),
        ip_version=client_ip.version,
        scheme=request.url.scheme,
        headers=request.headers,
        request_url=request.url,
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


@view_router.get("/", response_class=HTMLResponse)
async def get_root_view(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="main.j2",
        context={
            "site_emoji": site_emoji,
            "site_title": site_title,
            "host_info": get_host_info(request),
        },
    )


@api_router.get("/")
async def get_api_root(request: Request):
    return get_host_info(request)

app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)
