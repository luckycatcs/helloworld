#!/usr/bin/env python3
import json
import os
import re
import sys
from datetime import datetime, date
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener
import http.cookiejar

ISO_DATE_PATTERN = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
SLASH_DATE_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/20\d{2})\b")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0 Safari/537.36"
)

LOGIN_URL = "https://trakit.losaltosca.gov/etrakit/login.aspx?lt=either&rd=~/dashboard.aspx"
DASHBOARD_URL = "https://trakit.losaltosca.gov/etrakit/dashboard.aspx"
PERMIT_ID = "BLD25-01440"
CURRENT_DATE = "2024-12-10"

USERNAME_ENV = "LOS_ALTOS_USERNAME"
PASSWORD_ENV = "LOS_ALTOS_PASSWORD"


class TextCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._texts: List[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self._texts.append(data)

    @property
    def text(self) -> str:
        return " ".join(self._texts)


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self.links.append(href)


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: List[Dict[str, object]] = []
        self._current_form: Optional[Dict[str, object]] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = dict(attrs)
        if tag == "form":
            self._current_form = {
                "action": attr_map.get("action", ""),
                "method": (attr_map.get("method") or "post").lower(),
                "inputs": [],
            }
            return

        if tag == "input" and self._current_form is not None:
            input_info = {
                "name": attr_map.get("name"),
                "value": attr_map.get("value", ""),
                "type": (attr_map.get("type") or "text").lower(),
            }
            self._current_form["inputs"].append(input_info)

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current_form is not None:
            self.forms.append(self._current_form)
            self._current_form = None


def parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def extract_dates_from_text(text: str) -> List[date]:
    dates: List[date] = []
    for match in ISO_DATE_PATTERN.findall(text):
        parsed = parse_date(match)
        if parsed:
            dates.append(parsed)
    for match in SLASH_DATE_PATTERN.findall(text):
        parsed = parse_date(match)
        if parsed:
            dates.append(parsed)
    return dates


def extract_dates_from_json(payload: object) -> List[date]:
    dates: List[date] = []
    if isinstance(payload, dict):
        for value in payload.values():
            dates.extend(extract_dates_from_json(value))
    elif isinstance(payload, list):
        for value in payload:
            dates.extend(extract_dates_from_json(value))
    elif isinstance(payload, str):
        dates.extend(extract_dates_from_text(payload))
    return dates


def fetch_with_opener(
    opener,
    url: str,
    timeout: int,
    headers: List[Tuple[str, str]],
    data: Optional[bytes] = None,
) -> Tuple[str, bytes]:
    request = Request(url, data=data)
    request.add_header("User-Agent", DEFAULT_USER_AGENT)
    for key, value in headers:
        request.add_header(key, value)
    with opener.open(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        return content_type, response.read()


def parse_available_dates(content_type: str, body: bytes) -> List[date]:
    if "application/json" in content_type.lower():
        payload = json.loads(body.decode("utf-8"))
        return extract_dates_from_json(payload)

    parser = TextCollector()
    parser.feed(body.decode("utf-8", errors="replace"))
    return extract_dates_from_text(parser.text)


def summarize_dates(dates: List[date]) -> str:
    unique_dates = sorted(set(dates))
    if not unique_dates:
        return "No available inspection dates found in the response."
    lines = ["Available inspection dates found:"]
    lines.extend(f"- {d.isoformat()}" for d in unique_dates)
    return "\n".join(lines)


def select_login_form(forms: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    for form in forms:
        inputs = form.get("inputs", [])
        if any(inp.get("type") == "password" for inp in inputs):
            return form
    return forms[0] if forms else None


def find_login_fields(inputs: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    username_field = None
    password_field = None
    for input_info in inputs:
        if input_info.get("type") == "password":
            password_field = input_info.get("name")
    for input_info in inputs:
        name = (input_info.get("name") or "").lower()
        if input_info.get("type") in {"text", "email"} and (
            "user" in name or "login" in name
        ):
            username_field = input_info.get("name")
            break
    if not username_field:
        for input_info in inputs:
            if input_info.get("type") in {"text", "email"}:
                username_field = input_info.get("name")
                break
    return username_field, password_field


def build_login_payload(
    form: Dict[str, object],
    username: str,
    password: str,
) -> Tuple[str, bytes]:
    inputs: List[Dict[str, str]] = form.get("inputs", [])  # type: ignore[assignment]
    username_field, password_field = find_login_fields(inputs)
    if not username_field or not password_field:
        raise ValueError("Unable to detect username/password fields in login form.")

    data: Dict[str, str] = {}
    for input_info in inputs:
        name = input_info.get("name")
        if not name:
            continue
        data[name] = input_info.get("value", "")

    data[username_field] = username
    data[password_field] = password

    action = form.get("action", "")  # type: ignore[assignment]
    return action, urlencode(data).encode("utf-8")


def login_and_fetch_permit_page(
    username: str,
    password: str,
    timeout: int = 20,
    headers: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[str, bytes]:
    cookie_jar = http.cookiejar.CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))
    headers = headers or []

    _, login_page = fetch_with_opener(opener, LOGIN_URL, timeout, headers)
    form_parser = FormParser()
    form_parser.feed(login_page.decode("utf-8", errors="replace"))
    login_form = select_login_form(form_parser.forms)
    if not login_form:
        raise ValueError("Unable to locate a login form on the page.")

    action, payload = build_login_payload(login_form, username, password)
    action_url = urljoin(LOGIN_URL, action) if action else LOGIN_URL
    fetch_with_opener(opener, action_url, timeout, headers, data=payload)

    _, dashboard_page = fetch_with_opener(opener, DASHBOARD_URL, timeout, headers)
    link_parser = LinkCollector()
    link_parser.feed(dashboard_page.decode("utf-8", errors="replace"))

    permit_link = None
    for link in link_parser.links:
        if PERMIT_ID in link:
            permit_link = urljoin(DASHBOARD_URL, link)
            break

    if not permit_link:
        raise ValueError(
            f"Permit link for {PERMIT_ID} not found on the dashboard page."
        )

    return fetch_with_opener(opener, permit_link, timeout, headers)


def main() -> int:
    username = os.environ.get(USERNAME_ENV)
    password = os.environ.get(PASSWORD_ENV)
    if not username or not password:
        print(
            "Error: set LOS_ALTOS_USERNAME and LOS_ALTOS_PASSWORD environment variables.",
            file=sys.stderr,
        )
        return 2

    current_date = parse_date(CURRENT_DATE)
    if not current_date:
        print("Error: CURRENT_DATE must be YYYY-MM-DD or MM/DD/YYYY.", file=sys.stderr)
        return 2

    try:
        content_type, body = login_and_fetch_permit_page(username, password)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except HTTPError as exc:
        print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
        return 1
    except URLError as exc:
        print(f"Network error: {exc.reason}", file=sys.stderr)
        return 1

    dates = parse_available_dates(content_type, body)
    earlier_dates = sorted({d for d in dates if d < current_date})

    print(summarize_dates(dates))
    if earlier_dates:
        earliest = earlier_dates[0]
        print(
            f"\nEarlier date available! Earliest found: {earliest.isoformat()} "
            f"(current: {current_date.isoformat()})."
        )
        return 0

    print(f"\nNo earlier dates found before {current_date.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
