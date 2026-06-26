import argparse
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests


DEFAULT_BASE_URL = "https://ps2-media-library-api.fly.dev"
DEFAULT_ORIGIN = "https://theavenoircollection.com"
PS_FOCUS_PLATFORMS = ["PlayStation 3", "PlayStation 4"]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def get_json(session: requests.Session, base_url: str, path: str, timeout: int = 30, params: Optional[Dict[str, str]] = None):
    response = session.get(f"{base_url}{path}", timeout=timeout, params=params)
    response.raise_for_status()
    return response.json()


def cors_options(session: requests.Session, base_url: str, origin: str, timeout: int = 30):
    response = session.options(
        f"{base_url}/api/media",
        timeout=timeout,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    response.raise_for_status()
    return response.headers


def admin_login_logout(session: requests.Session, base_url: str, password: str, timeout: int = 30) -> CheckResult:
    try:
        login_response = session.post(
            f"{base_url}/api/admin/login",
            json={"password": password},
            timeout=timeout,
        )
        login_response.raise_for_status()
        token = (login_response.json() or {}).get("token")
        if not token:
            return CheckResult("admin-login-logout", False, "No token returned by login endpoint")

        logout_response = session.post(
            f"{base_url}/api/admin/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        logout_response.raise_for_status()
        logout_ok = bool((logout_response.json() or {}).get("success"))
        if not logout_ok:
            return CheckResult("admin-login-logout", False, "Logout endpoint did not return success=true")

        return CheckResult("admin-login-logout", True, "Login/logout succeeded")
    except requests.RequestException as exc:
        return CheckResult("admin-login-logout", False, f"{exc}")


def run_smoke(base_url: str, origin: str, timeout: int, admin_password: Optional[str]) -> List[CheckResult]:
    results: List[CheckResult] = []

    with requests.Session() as session:
        try:
            media_all = get_json(session, base_url, "/api/media", timeout=timeout)
            results.append(CheckResult("media-all", isinstance(media_all, list), f"count={len(media_all) if isinstance(media_all, list) else 'n/a'}"))
        except requests.RequestException as exc:
            results.append(CheckResult("media-all", False, str(exc)))
            return results

        try:
            systems = get_json(session, base_url, "/api/systems", timeout=timeout)
            system_count = len(systems) if isinstance(systems, list) else 0
            results.append(CheckResult("systems", isinstance(systems, list) and system_count > 0, f"count={system_count}"))
        except requests.RequestException as exc:
            results.append(CheckResult("systems", False, str(exc)))

        try:
            filters = get_json(session, base_url, "/api/filters", timeout=timeout)
            categories = filters.get("categories", []) if isinstance(filters, dict) else []
            has_expected = "Games" in categories and "Music" in categories
            results.append(CheckResult("filters", has_expected, f"categories={categories}"))
        except requests.RequestException as exc:
            results.append(CheckResult("filters", False, str(exc)))

        for platform in PS_FOCUS_PLATFORMS:
            try:
                games = get_json(
                    session,
                    base_url,
                    "/api/media",
                    timeout=timeout,
                    params={"category": "Games", "platform": platform},
                )
                count = len(games) if isinstance(games, list) else 0
                results.append(CheckResult(f"games-{platform}", isinstance(games, list) and count > 0, f"count={count}"))
            except requests.RequestException as exc:
                results.append(CheckResult(f"games-{platform}", False, str(exc)))

        try:
            music = get_json(session, base_url, "/api/media", timeout=timeout, params={"category": "Music"})
            count = len(music) if isinstance(music, list) else 0
            results.append(CheckResult("music", isinstance(music, list) and count > 0, f"count={count}"))
        except requests.RequestException as exc:
            results.append(CheckResult("music", False, str(exc)))

        try:
            headers = cors_options(session, base_url, origin=origin, timeout=timeout)
            allow_origin = headers.get("access-control-allow-origin", "")
            allow_methods = headers.get("access-control-allow-methods", "")
            cors_ok = allow_origin in {"*", origin} and "POST" in allow_methods and "GET" in allow_methods
            results.append(
                CheckResult(
                    "cors",
                    cors_ok,
                    f"allow-origin={allow_origin}; allow-methods={allow_methods}",
                )
            )
        except requests.RequestException as exc:
            results.append(CheckResult("cors", False, str(exc)))

        if admin_password:
            results.append(admin_login_logout(session, base_url, admin_password, timeout=timeout))

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test live API deployment with PS3/PS4 focus.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help="Origin to use for CORS check")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout seconds")
    parser.add_argument("--admin-password", default=None, help="Optional admin password for login/logout verification")
    args = parser.parse_args()

    results = run_smoke(
        base_url=args.base_url.rstrip("/"),
        origin=args.origin,
        timeout=args.timeout,
        admin_password=args.admin_password,
    )

    failures = [r for r in results if not r.ok]
    for result in results:
        state = "PASS" if result.ok else "FAIL"
        print(f"[{state}] {result.name}: {result.detail}")

    if failures:
        print(f"\nSmoke test failed: {len(failures)} check(s) failed.")
        return 1

    print("\nSmoke test passed: all checks succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
