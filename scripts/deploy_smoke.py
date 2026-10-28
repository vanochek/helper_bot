"""Проверить HTTPS с доверенным сертификатом и изоляцию данных через публичный вход."""

import argparse
import http.cookiejar
import json
import ssl
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("url")
parser.add_argument("--ca", help="Корневая CA только для локального проверочного стека")
args = parser.parse_args()
origin = args.url.rstrip("/")
context = ssl.create_default_context(cafile=args.ca)


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def call(browser, path, data=None):
    request = urllib.request.Request(
        origin + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Origin": origin, "Content-Type": "application/json"},
    )
    with browser.open(request, timeout=15) as response:
        return json.load(response)


first, second = client(), client()
assert call(first, "/health/ready") == {"status": "ok"}
for browser in (first, second):
    call(browser, "/api/v1/session", {"timezone": "Europe/Moscow"})
entry = call(first, "/api/v1/entries", {"kind": "task", "title": "Проверка HTTPS"})
assert call(first, "/api/v1/entries/" + entry["id"])["title"] == "Проверка HTTPS"
assert call(second, "/api/v1/entries") == []
print("HTTPS, доверие сертификату, сессии, запись и изоляция проверены.")
