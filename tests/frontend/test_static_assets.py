from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "services" / "frontend" / "public"


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.refs.append(values["src"])
        if tag == "link" and values.get("href"):
            self.refs.append(values["href"])
        if tag == "a" and values.get("href"):
            self.refs.append(values["href"])


def _local_ref(ref: str) -> str | None:
    if ref.startswith("#") or ref.startswith(("http://", "https://", "mailto:", "tel:")):
        return None
    parsed = urlparse(ref)
    path = parsed.path
    if not path or path == "#":
        return None
    return path


def test_frontend_html_local_links_scripts_and_styles_exist():
    html_files = sorted(PUBLIC.glob("*.html"))
    assert html_files

    for html_file in html_files:
        parser = AssetParser()
        parser.feed(html_file.read_text(encoding="utf-8"))
        for ref in parser.refs:
            local = _local_ref(ref)
            if not local:
                continue
            assert (PUBLIC / local).exists(), f"{html_file.name} references missing {ref}"


def test_frontend_pages_reference_expected_scripts_and_styles():
    assert 'href="style.css"' in (PUBLIC / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in (PUBLIC / "index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in (PUBLIC / "track.html").read_text(encoding="utf-8")
    assert 'src="admin.js"' in (PUBLIC / "admin.html").read_text(encoding="utf-8")


def test_frontend_javascript_uses_gateway_api_contracts():
    app_js = (PUBLIC / "app.js").read_text(encoding="utf-8")
    admin_js = (PUBLIC / "admin.js").read_text(encoding="utf-8")
    login_html = (PUBLIC / "login.html").read_text(encoding="utf-8")

    assert "window.GATEWAY_URL || '/api'" in app_js
    assert "fetch(`${GATEWAY_URL}/complaints`" in app_js
    assert "localStorage.getItem('cf_token')" in app_js

    for endpoint in (
        "/admin/stats",
        "/admin/complaints",
        "/admin/review-queue",
        "/admin/review-resolved",
        "/admin/duplicates",
        "/admin/retraining/",
    ):
        assert endpoint in admin_js

    assert "/auth/login" in login_html
    assert "/auth/register" in login_html


def test_frontend_nginx_proxies_api_and_review_service():
    nginx = (ROOT / "services" / "frontend" / "nginx.conf").read_text(encoding="utf-8")

    assert "location /api/" in nginx
    assert "proxy_pass http://api-service:8000/" in nginx
    assert "location /review-api/" in nginx
    assert "proxy_pass http://api-service:8008/" in nginx
    assert "location /health" in nginx
