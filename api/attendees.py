"""Read-only, single-event attendee feed for the public Vercel website."""

import json
import os
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from picklequeue.engine import Problem
from picklequeue.reclub import public_attendee_feed


SUCCESS_HEADERS = {
    'Cache-Control':'public, s-maxage=60, stale-while-revalidate=300, stale-if-error=600',
    'X-Content-Type-Options':'nosniff',
}
ERROR_HEADERS = {
    'Cache-Control':'no-store',
    'X-Content-Type-Options':'nosniff',
}


def response_for_event(event_reference):
    if not event_reference:
        return 503, {'error':'Reclub sign-ups are not configured.'}, ERROR_HEADERS
    try:
        return 200, public_attendee_feed(event_reference), SUCCESS_HEADERS
    except Problem as error:
        return error.status, {'error':str(error)}, ERROR_HEADERS


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status, payload, headers):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        for name,value in headers.items():
            self.send_header(name,value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).query:
            self.send_json(400,{'error':'Query parameters are not accepted.'},ERROR_HEADERS)
            return
        status,payload,headers = response_for_event(os.environ.get('RECLUB_EVENT_REF'))
        self.send_json(status,payload,headers)

    def do_HEAD(self):
        self.send_response(405)
        self.send_header('Allow','GET')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length','0')
        self.end_headers()

    def do_POST(self):
        self.send_json(405,{'error':'This endpoint is read-only.'},{**ERROR_HEADERS,'Allow':'GET'})

    def do_PUT(self):
        self.send_json(405,{'error':'This endpoint is read-only.'},{**ERROR_HEADERS,'Allow':'GET'})

    def do_DELETE(self):
        self.send_json(405,{'error':'This endpoint is read-only.'},{**ERROR_HEADERS,'Allow':'GET'})
