import os
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

site_emoji = "📟"
version = os.getenv("APP_VERSION", "local-dev")
app = FastAPI(title="")
app.mount("/static", StaticFiles(directory="resources/static"), name="static")
templates = Jinja2Templates(directory="resources/templates")

class FaviconResponse(Response):
    media_type = "image/svg+xml"

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
async def get_root_view(request: Request, plain: bool = False):
    if plain:
        return ""
    
    return templates.TemplateResponse(
        request=request,
        name="main.j2",
        context={ "request": request },
    )


@api_router.get("/")
async def get_api_root(request: Request):
    pass


app.include_router(api_router, prefix="/api/v1")
app.include_router(view_router)
