import re
import webbrowser
from urllib.parse import quote_plus, urlparse

from logger import log_error
from search.engine import SearchEngine


SEARCH_ENGINES = {
    "bing": "https://www.bing.com/search?q=",
    "google": "https://www.google.com/search?q=",
    "duckduckgo": "https://duckduckgo.com/?q=",
    "baidu": "https://www.baidu.com/s?wd=",
}

COMMON_URL_SUFFIXES = (
    "com",
    "net",
    "org",
    "io",
    "dev",
    "app",
    "cn",
    "com.cn",
    "top",
    "xyz",
    "site",
    "me",
    "co",
    "ai",
)

_ENGINE = SearchEngine()


def normalize_engine(engine: str | None) -> str:
    return engine if engine in SEARCH_ENGINES else "bing"


def detect_url(text: str) -> str | None:
    candidate = _first_url_candidate(text)
    if not candidate or any(char.isspace() for char in candidate):
        return None
    if candidate.isdigit():
        return None
    parsed = urlparse(candidate)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return candidate
    if "://" in candidate and parsed.scheme and parsed.scheme not in ("http", "https"):
        return None
    if _looks_like_ip_or_localhost(candidate):
        host = _host_without_port(candidate)
        scheme = "http" if _is_private_ip_or_localhost(host) else "https"
        return f"{scheme}://{candidate}"
    if _looks_like_domain(candidate):
        return f"https://{candidate}"
    return None


def is_url(text: str) -> bool:
    return detect_url(text) is not None


def build_search_url(query: str, engine: str | None) -> str:
    text = query.strip()
    if not text:
        return ""
    detected = detect_url(text)
    if detected:
        return detected
    base = SEARCH_ENGINES[normalize_engine(engine)]
    return f"{base}{quote_plus(text)}"


def open_query(query: str, engine: str | None) -> bool:
    text = query.strip()
    if not text:
        return False
    detected = detect_url(text)
    if detected:
        try:
            return bool(webbrowser.open(detected))
        except Exception as exc:
            log_error("URL open failed", exc)
            return False
    if open_local_match(text):
        return True
    try:
        return bool(webbrowser.open(build_search_url(text, engine)))
    except Exception as exc:
        log_error("Search open failed", exc)
        return False


def open_local_match(query: str) -> bool:
    results = search_local_results(query, 1)
    if not results:
        return False
    return open_search_result(results[0])


def search_local_results(query: str, limit: int = 50) -> list[dict]:
    return [result.to_dict() for result in _ENGINE.search(query, limit)]


def prewarm_search_indexes() -> None:
    _ENGINE.prewarm_static_indexes()


def open_search_result(result: dict) -> bool:
    return _ENGINE.open_result(result)


def _first_url_candidate(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    return stripped.splitlines()[0].strip()


def _is_private_ip_or_localhost(host: str) -> bool:
    if host == "localhost":
        return True
    return bool(re.match(r"^(10|127|192\.168|172\.(1[6-9]|2\d|3[0-1]))\.\d{1,3}\.\d{1,3}$", host))


def _host_without_port(candidate: str) -> str:
    host = candidate.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.lower()


def _looks_like_domain(candidate: str) -> bool:
    host = _host_without_port(candidate)
    if host.startswith("www."):
        return True
    return any(host.endswith(f".{suffix}") for suffix in COMMON_URL_SUFFIXES)


def _looks_like_ip_or_localhost(candidate: str) -> bool:
    host = _host_without_port(candidate)
    if host == "localhost":
        return True
    return bool(re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host))
