#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import httpx

# Prefer project TLS helpers if available, but fall back to default verification.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from ingestion.http.client import _build_ssl_context, _default_extra_ca_files
except Exception:
    _build_ssl_context = None
    _default_extra_ca_files = None


ROOT = Path(__file__).resolve().parent.parent
SLUG_MAP = ROOT / "trading_tools" / "mappings" / "ammc_issuer_slugs.json"
BASE = "https://www.ammc.ma/fr/espace-emetteurs/societes-cotees/"


def load_slugs(path: Path) -> Dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, str] = {}
    for k, v in raw.items():
        if str(k).startswith("_"):
            continue
        out[str(k).strip().upper()] = str(v).strip().strip("/")
    return out


def main() -> int:
    if not SLUG_MAP.exists():
        print(f"missing slug map: {SLUG_MAP}", file=sys.stderr)
        return 2

    slugs = load_slugs(SLUG_MAP)
    # Disable SSL verification for ad-hoc slug testing (user-requested).
    verify = False
    ok = 0
    bad: list[tuple[str, int]] = []

    with httpx.Client(verify=verify, timeout=20.0) as client:
        for symbol, slug in sorted(slugs.items()):
            url = BASE + slug
            try:
                r = client.get(url)
                code = r.status_code
                if code == 200:
                    ok += 1
                    print(f"OK   {symbol:6} {code} {url}")
                else:
                    bad.append((symbol, code))
                    print(f"FAIL {symbol:6} {code} {url}")
            except Exception as exc:
                bad.append((symbol, 0))
                print(f"ERR  {symbol:6} 0   {url}  ({exc})")

    total = len(slugs)
    print()
    print(f"checked {total} slugs: {ok} OK, {len(bad)} failed")
    if bad:
        print("failures:")
        for sym, code in bad:
            print(f" - {sym}: {code}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
