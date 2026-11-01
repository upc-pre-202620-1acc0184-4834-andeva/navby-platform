import os
from datetime import UTC, datetime, timedelta

import httpx


def main() -> int:
    base_url = os.environ.get("SMOKE_BASE_URL", "https://navby.andeva.tech/api/v1").rstrip("/")
    email = os.environ.get("SMOKE_USER_EMAIL", "")
    password = os.environ.get("SMOKE_USER_PASSWORD", "")
    run_paid_quotes = os.environ.get("RUN_PAID_QUOTES", "false").lower() == "true"

    with httpx.Client(timeout=35.0) as client:
        r_health = client.get(f"{base_url}/health")
        if r_health.status_code != 200:
            print(f"Health check failed: {r_health.status_code} {r_health.text}")
            return 1
        health_data = r_health.json()
        if health_data.get("graph", {}).get("nodes") != 3354:
            print(f"Unexpected graph nodes: {health_data}")
            return 1

        r_cities = client.get(f"{base_url}/routing/cities", params={"q": "lim"})
        if r_cities.status_code != 200 or not r_cities.json().get("cities"):
            print(f"Cities smoke check failed: {r_cities.status_code}")
            return 1

        r_preview = client.get(
            f"{base_url}/routing/preview",
            params={"origins": "LIM", "destinations": "MAD"},
        )
        if r_preview.status_code != 200 or not r_preview.json().get("reachable"):
            print(f"Preview smoke check failed: {r_preview.status_code}")
            return 1

        if email and password:
            r_login = client.post(
                f"{base_url}/auth/login",
                json={"email": email, "password": password},
            )
            if r_login.status_code != 200:
                print(f"Smoke login failed: {r_login.status_code}")
                return 1
            token = r_login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            r_order = client.post(
                f"{base_url}/billing/orders",
                headers=headers,
                json={"package_code": "pack_50"},
            )
            if r_order.status_code != 201:
                print(f"Order smoke check failed: {r_order.status_code}")
                return 1

            if run_paid_quotes:
                dep = (datetime.now(UTC).date() + timedelta(days=30)).isoformat()
                r_search = client.post(
                    f"{base_url}/quotes/search",
                    headers=headers,
                    json={
                        "trip_type": "ONE_WAY",
                        "origins": ["LIM"],
                        "destinations": ["MIA"],
                        "departure_date": dep,
                        "passengers": {"adults": 1, "children": 0, "infants": 0},
                        "cabin": "ECONOMY",
                        "currency": "USD",
                    },
                )
                if r_search.status_code != 200:
                    print(f"Quotes search smoke check failed: {r_search.status_code}")
                    return 1

    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
