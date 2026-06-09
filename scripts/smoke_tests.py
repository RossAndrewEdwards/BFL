import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import app, init_db


PUBLIC_ROUTES = [
    "/",
    "/rules",
]


def assert_ok(condition, message):
    if not condition:
        raise AssertionError(message)


def login_admin(client):
    login_page = client.get("/login")
    assert_ok(login_page.status_code == 200, "Login page did not load")
    csrf_match = re.search(rb'name="_csrf_token" value="([^"]+)"', login_page.data)
    assert_ok(csrf_match, "Could not find CSRF token on login page")

    response = client.post(
        "/login",
        data={
            "_csrf_token": csrf_match.group(1).decode("utf-8"),
            "username": "admin",
            "password": "admin123",
        },
        follow_redirects=True,
    )
    assert_ok(response.status_code == 200, "Admin login failed")
    assert_ok(b"Admin" in response.data or b"Leaderboard" in response.data, "Admin login response did not look authenticated")


def main():
    init_db()
    app.config.update(TESTING=True)

    failures = []
    with app.test_client() as client:
        for route in PUBLIC_ROUTES:
            response = client.get(route)
            try:
                assert_ok(response.status_code == 200, f"{route} returned {response.status_code}")
                assert_ok(b"<html" in response.data.lower(), f"{route} did not render HTML")
                print(f"OK public route: {route}")
            except AssertionError as exc:
                failures.append(str(exc))

        response = client.get("/leaderboard")
        if response.status_code == 302 and "/login" in response.headers.get("Location", ""):
            print("OK legacy redirect: /leaderboard -> /login")
        else:
            failures.append("/leaderboard did not redirect to /login")

        response = client.get("/")
        if response.status_code == 200 and b"Buhurt UK Calendar" in response.data and b"Members Only" in response.data:
            print("OK landing page: /")
        else:
            failures.append("/ did not render the landing page")

        try:
            login_admin(client)
            
            response = client.get("/teams")
            assert_ok(response.status_code == 200, f"/teams returned {response.status_code}")
            assert_ok(b"Upcoming Tournaments" not in response.data and b"League Updates" not in response.data, "Teams page included global updates or tournament clutter")
            print("OK focused teams page")
            
            response = client.get("/admin/teams/new")
            assert_ok(response.status_code == 200, f"/admin/teams/new returned {response.status_code}")
            assert_ok(b"Team Builder Wizard" in response.data, "Team builder page did not render the builder wizard")
            assert_ok(b"selected-fighter-grid" in response.data, "Team builder comparison grid is missing")
            print("OK admin route: /admin/teams/new")
        except AssertionError as exc:
            failures.append(str(exc))

    if failures:
        print("\nFailures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nSmoke tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
