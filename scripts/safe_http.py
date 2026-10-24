#!/usr/bin/env python3
"""Strict HTTPS fetch for PUBLIC research sources, using DNS-validated pinned sockets.

Never fetches local/private IPs, arbitrary ports, credentials or HTTP downgrades.
No proxy inheritance; fail closed on DNS uncertainty, oversized replies and redirects.
Results are text snapshots, NOT independently verified claims.
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse

MAX_REDIRECTS = 3
USER_AGENT = "AI-News-Video-Skill/1.0 (public-research; editorial-review)"

def url_parts(url: str) -> urllib.parse.SplitResult:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("HTTPS URL missing or too long")
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("malformed source URL") from exc
    if (parts.scheme.lower() != "https" or not host or port not in (None, 443)
            or parts.username is not None or parts.password is not None
            or any(ord(x) < 32 for x in url) or "\\" in url):
        raise ValueError("public HTTPS URL on port 443 required")
    if len(host) > 253 or host.endswith(".local") or host.lower() == "localhost":
        raise ValueError("local or invalid source hostname")
    return parts

def resolved_public_addrs(host: str) -> list[tuple]:
    """Reject the ENTIRE DNS answer if ANY address is private/reserved."""
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("source hostname cannot be resolved") from exc
    if not answers or len(answers) > 32:
        raise ValueError("no safe DNS answers")
    result = []
    for family, kind, proto, _canonical, sockaddr in answers:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise ValueError("invalid source DNS address") from exc
        if not address.is_global:
            raise ValueError("source resolves to a non-public address")
        if family not in (socket.AF_INET, socket.AF_INET6):
            raise ValueError("unsupported address family")
        result.append((family, kind, proto, sockaddr))
    return result

class _PinnedTLSConnection(http.client.HTTPSConnection):
    def connect(self):
        # TLS SNI/certificate validation uses original hostname while TCP uses
        # a previously vetted numeric IP. No second resolver / DNS rebinding.
        resolved = resolved_public_addrs(self.host)
        last = None
        for family, kind, proto, address in resolved:
            conn = socket.socket(family, kind, proto)
            try:
                conn.settimeout(self.timeout)
                conn.connect(address)
                self.sock = self._context.wrap_socket(conn, server_hostname=self.host)
                return
            except (OSError, ssl.SSLError) as exc:
                last = exc
                conn.close()
        raise ValueError("safe HTTPS connection failed") from last

def get(url: str, max_bytes: int, *, timeout: int = 12) -> tuple[bytes, str, str, int]:
    if not 100 <= max_bytes <= 2_000_000:
        raise ValueError("HTTP byte budget outside allowed bounds")
    if not 1 <= timeout <= 25:
        raise ValueError("timeout outside allowed bounds")
    current = url
    visited = set()
    for _ in range(MAX_REDIRECTS + 1):
        parsed = url_parts(current)
        key = current.split("#", 1)[0]
        if key in visited:
            raise ValueError("redirect loop")
        visited.add(key)
        host = parsed.hostname
        assert host is not None
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection = _PinnedTLSConnection(host, port=443, timeout=timeout,
                                         context=ssl.create_default_context())
        try:
            connection.request("GET", path, headers={
                "Host": host, "User-Agent": USER_AGENT,
                "Accept-Encoding": "identity", "Connection": "close"})
            response = connection.getresponse()
            status = response.status
            if status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("redirect missing Location")
                dest = urllib.parse.urljoin(current, location)
                url_parts(dest)
                current = dest.split("#", 1)[0]
                continue
            if status != 200:
                raise ValueError("source HTTP status " + str(status))
            if response.getheader("Content-Encoding", "identity").lower() not in ("identity", ""):
                raise ValueError("compressed HTTP replies not accepted")
            content_length = response.getheader("Content-Length")
            if content_length is not None:
                try:
                    if int(content_length) > max_bytes:
                        raise ValueError("source larger than byte budget")
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid or oversized source Content-Length") from exc
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("source larger than byte budget")
            return body, current, response.getheader("Content-Type", ""), status
        except (socket.timeout, ssl.SSLError, http.client.HTTPException, OSError) as exc:
            raise ValueError("public HTTPS retrieval failed") from exc
        finally:
            connection.close()
    raise ValueError("too many redirects")
