"""HTML page routes — serves the browser UI templates."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Pages"], include_in_schema=False)

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="login.html")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html")

@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="users.html")

@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="products.html")


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="transactions.html")


@router.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="reports.html")