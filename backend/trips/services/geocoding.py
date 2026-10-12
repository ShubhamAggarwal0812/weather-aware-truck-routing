"""Place search for the origin/destination boxes: TomTom when keyed, Photon (OSM) otherwise."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache

from .http import UpstreamError, request_json

# North America, where the trucking units (mph, lb, in/hr) apply.
COUNTRIES = "US,CA,MX"
PHOTON_BBOX = "-170,14,-50,72"
CACHE_TTL_S = 24 * 3600
LIMIT = 6


class GeocodingError(Exception):
    pass


def search(query: str) -> list[dict[str, Any]]:
    query = " ".join(query.split())
    provider = "tomtom" if settings.TOMTOM_API_KEY else "photon"
    key = "geo:" + hashlib.sha1(f"{provider}:{query.lower()}".encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        results = _tomtom(query) if provider == "tomtom" else _photon(query)
    except UpstreamError as exc:
        raise GeocodingError("Place search is unavailable right now.") from exc
    cache.set(key, results, CACHE_TTL_S)
    return results


def _tomtom(query: str) -> list[dict[str, Any]]:
    data = request_json(
        "GET",
        f"https://api.tomtom.com/search/2/search/{quote(query, safe='')}.json",
        service="tomtom-search",
        params={
            "key": settings.TOMTOM_API_KEY,
            "typeahead": "true",
            "limit": LIMIT,
            "countrySet": COUNTRIES,
            "language": "en-US",
            "idxSet": "Geo,PAD,Addr,Str,POI",
        },
    )
    out = []
    for r in data.get("results", []):
        address = r.get("address", {})
        poi = (r.get("poi") or {}).get("name")
        label = address.get("freeformAddress") or ""
        if r.get("type") == "Geography" and address.get("countrySubdivision") and address.get("municipality"):
            label = f"{address['municipality']}, {address['countrySubdivision']}"
        out.append(
            {
                "label": f"{poi}, {label}" if poi else label,
                "lat": r["position"]["lat"],
                "lon": r["position"]["lon"],
            }
        )
    return _unique(out)


def _photon(query: str) -> list[dict[str, Any]]:
    data = request_json(
        "GET",
        f"{settings.PHOTON_BASE_URL.rstrip('/')}/api/",
        service="photon",
        params={"q": query, "limit": LIMIT, "lang": "en", "bbox": PHOTON_BBOX},
    )
    out = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
        parts = [p.get("name") or street, p.get("city"), p.get("state"), p.get("countrycode")]
        seen: list[str] = []
        for part in parts:
            if part and part not in seen:
                seen.append(part)
        lon, lat = f["geometry"]["coordinates"]
        out.append({"label": ", ".join(seen), "lat": lat, "lon": lon})
    return _unique(out)


def _unique(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for r in results:
        if r["label"] and r["label"] not in seen:
            seen.add(r["label"])
            out.append(r)
    return out
