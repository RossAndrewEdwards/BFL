import gc
import re
import sqlite3
import tempfile
import time
import unittest
import uuid
from io import BytesIO
from pathlib import Path

import werkzeug.security
werkzeug.security.generate_password_hash = lambda password, *args, **kwargs: f"plain${password}"
werkzeug.security.check_password_hash = lambda pwhash, password: pwhash == f"plain${password}" or pwhash == password or pwhash.split("$")[-1] == password

import app as app_module
from app import app, init_db


class AppRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._original_connect = sqlite3.connect
        def optimized_connect(*args, **kwargs):
            conn = cls._original_connect(*args, **kwargs)
            try:
                conn.execute("PRAGMA synchronous = OFF")
                conn.execute("PRAGMA journal_mode = MEMORY")
            except Exception:
                pass
            return conn
        sqlite3.connect = optimized_connect

        cls._original_db_path = app_module.DB_PATH
        temp_dir = Path(tempfile.mkdtemp(prefix="invicta_tests_"))
        cls._temp_dir = temp_dir
        app_module.DB_PATH = temp_dir / "league_test.db"
        app.config["SCHEMA_READY"] = False
        init_db()
        app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        sqlite3.connect = cls._original_connect
        app_module.DB_PATH = cls._original_db_path
        app.config["SCHEMA_READY"] = False
        db_file = cls._temp_dir / "league_test.db"
        gc.collect()
        if db_file.exists():
            last_error = None
            for _ in range(5):
                try:
                    db_file.unlink()
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.1)
                    gc.collect()
            if last_error is not None:
                raise last_error
        cls._temp_dir.rmdir()

    def setUp(self):
        self.client = app.test_client()

    def test_logged_out_users_can_only_access_home_and_rules(self):
        expected_markers = {
            "/": b"Buhurt UK Calendar",
            "/rules": b"Fantasy League Rules",
            "/contact": b"Platform Contact",
        }

        for route, marker in expected_markers.items():
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(marker, response.data)

    def test_logged_out_users_are_redirected_from_member_only_pages(self):
        for route in (
            "/events/results",
            "/fighters",
            "/fighters/1",
            "/teams",
            "/teams/compare",
            "/teams/1",
            "/hall-of-fame",
        ):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/login", response.headers["Location"])

    def test_existing_seed_players_have_backfilled_league_memberships(self):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            missing = conn.execute(
                """
                SELECT COUNT(*)
                FROM users u
                WHERE u.role IN ('player', 'league_admin')
                  AND u.league_id IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM league_memberships lm
                      WHERE lm.user_id = u.id
                        AND lm.league_id = u.league_id
                  )
                """
            ).fetchone()[0]

        self.assertEqual(missing, 0)

    def test_default_skins_render_for_fighters_and_teams(self):
        username = f"skins_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        fighters_response = self.client.get("/fighters")
        teams_response = self.client.get("/teams")

        self.assertEqual(fighters_response.status_code, 200)
        self.assertEqual(teams_response.status_code, 200)
        self.assertIn(b"Helmet_-_Medieval_Knight_(PSF).png", fighters_response.data)
        self.assertIn(b"Heraldic_Shield_Argent.svg", teams_response.data)
        self.assertIn(b"shared-team-card", teams_response.data)
        self._delete_player(username)

    def test_legacy_leaderboard_redirects_logged_out_users_to_login(self):
        response = self.client.get("/leaderboard")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_logged_in_users_see_combined_leaderboard_page(self):
        username = f"leaderboard_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/leaderboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"League Leaderboard", response.data)
        self.assertIn(b"Fighter Rankings", response.data)
        self.assertIn(b"Fantasy Team Rankings", response.data)
        self.assertIn(b'href="/leaderboard">Leaderboard</a>', response.data)
        self.assertIn(b"data-overlay-open=", response.data)
        self._delete_player(username)

    def test_leaderboard_highlights_top_entries_and_embeds_popup_cards(self):
        username = f"leaderboard_popup_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/leaderboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"leaderboard-top-1", response.data)
        self.assertIn(b"leaderboard-top-2", response.data)
        self.assertIn(b"leaderboard-top-3", response.data)
        self.assertIn(b'data-overlay-card="fighter-', response.data)
        self.assertIn(b'data-overlay-card="team-', response.data)
        self.assertIn(b"fighter-card-shell", response.data)
        self.assertIn(b"shared-team-card", response.data)
        self.assertIn(b"Edition", response.data)
        self.assertIn(b"collector-chip-row", response.data)
        self._delete_player(username)

    def test_leaderboard_supports_independent_fighter_and_team_search(self):
        username = f"leaderboard_search_{uuid.uuid4().hex[:8]}"
        league_id = 1
        fighter_name = f"Needle Fighter {uuid.uuid4().hex[:6]}"
        team_name = f"Needle Team {uuid.uuid4().hex[:6]}"

        try:
            self._create_player(username, manager_limit=1)
            fighter_id = self._create_fighter(fighter_name, league_id)
            self._create_team_with_roster(team_name, [fighter_id])
            self._login_user(username, "player123")

            fighter_response = self.client.get(f"/leaderboard?fighter_q=Needle&team_q=")
            self.assertEqual(fighter_response.status_code, 200)
            self.assertIn(fighter_name.encode(), fighter_response.data)
            self.assertIn(b"Showing 1 of", fighter_response.data)

            team_response = self.client.get(f"/leaderboard?fighter_q=&team_q=Needle")
            self.assertEqual(team_response.status_code, 200)
            self.assertIn(team_name.encode(), team_response.data)
            self.assertIn(b"Find a team or player", team_response.data)
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("DELETE FROM fantasy_team_fighters WHERE fighter_id=?", (fighter_id,))
                conn.execute("DELETE FROM fantasy_teams WHERE team_name=?", (team_name,))
                conn.execute("DELETE FROM baseline_stats WHERE fighter_id=?", (fighter_id,))
                conn.execute("DELETE FROM fighters WHERE id=?", (fighter_id,))
            self._delete_player(username)

    def test_leaderboard_emphasises_own_team_and_rank_movement(self):
        username = f"leaderboard_story_{uuid.uuid4().hex[:8]}"
        league_id = self._create_league(f"leaderboard-story-{uuid.uuid4().hex[:8]}", "Leaderboard Story League")
        own_fighter_name = f"Story Fighter {uuid.uuid4().hex[:6]}"
        rival_fighter_name = f"Rival Fighter {uuid.uuid4().hex[:6]}"
        own_team_name = f"Story Team {uuid.uuid4().hex[:6]}"
        rival_team_name = f"Rival Team {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(username, role="player", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            rival_fighter_id = self._create_fighter(rival_fighter_name, league_id)
            own_team_id = self._create_team_with_roster(own_team_name, [own_fighter_id])
            self._create_team_with_roster(rival_team_name, [rival_fighter_id])
            with sqlite3.connect(app_module.DB_PATH) as conn:
                player = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
                conn.execute("UPDATE fantasy_teams SET player_user_id=? WHERE id=?", (player[0], own_team_id))
                conn.commit()
            scheduled_event_id = self._create_scheduled_event(f"Leaderboard Story Event {uuid.uuid4().hex[:6]}", "2026-12-31", league_id=league_id)
            self._create_event_result(scheduled_event_id, own_fighter_id, league_id=league_id, gold_medals=1, kills=4)
            self._create_event_result(scheduled_event_id, rival_fighter_id, league_id=league_id, kills=1)
            self._login_user(username, "player123")

            response = self.client.get("/leaderboard")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Your Team Lens", response.data)
            self.assertIn(b"Closest rival", response.data)
            self.assertIn(b"table-inline-tag", response.data)
            self.assertIn(b"rank-movement-badge", response.data)
            self.assertIn(own_team_name.encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_fighters_page_uses_card_led_browse_layout(self):
        username = f"fighter_browse_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/fighters")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Roster Binder", response.data)
        self.assertIn(b"Fighter Collection", response.data)
        self.assertIn(b"fighter-tier-spotlight-strip", response.data)
        self.assertIn(b"fighter-browse-card", response.data)
        self.assertIn(b"shared-fighter-card", response.data)
        self.assertIn(b"fighter-card-track-grid", response.data)
        self.assertIn(b"Quick fighter browse", response.data)
        self.assertIn(b"toolbar-chip-link", response.data)
        self.assertIn(b'return_to=/fighters"', response.data)
        self._delete_player(username)

    def test_fighter_detail_keeps_browse_return_link(self):
        username = f"fighter_return_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/fighters/1?return_to=%2Ffighters%3Fq%3Dalpha")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/fighters?q=alpha"', response.data)
        self.assertIn(b"Back to Fighter Browse", response.data)
        self._delete_player(username)

    def test_logout_redirects_to_homepage(self):
        self._login_admin()

        response = self.client.post(
            "/logout",
            data={"_csrf_token": self._csrf_from("/")},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome to Buhurt Fantasy League", response.data)
        self.assertIn(b"Logged out.", response.data)

    def test_home_renders_landing_page(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Image: Ivan Radic", response.data)
        self.assertIn(b"Buhurt UK Calendar", response.data)
        self.assertIn(b"Welcome to Buhurt Fantasy League", response.data)
        self.assertIn(b"League Rules", response.data)
        self.assertIn(b"Members Only", response.data)
        self.assertIn(b"Next Tournament", response.data)
        self.assertIn(b"Public domain", response.data)
        self.assertNotIn(b"View Rules", response.data)
        self.assertNotIn(b"Top 3 Fighters", response.data)
        self.assertNotIn(b"Top 3 Teams", response.data)

    def test_shared_footer_holds_secondary_navigation_for_guests(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<footer class="site-footer">', response.data)
        self.assertIn(b'footer-heading">Explore<', response.data)
        self.assertIn(b'data-theme-toggle', response.data)
        self.assertIn(b'window.localStorage.getItem("bfl-theme")', response.data)
        self.assertIn(b'href="/rules">Rules</a>', response.data)
        self.assertIn(b'href="/contact">Contact Us</a>', response.data)
        self.assertNotIn(b'href="/hall-of-fame">Hall of Fame</a>', response.data)

    def test_app_shell_exposes_scoped_context_preservation_hooks(self):
        username = f"shell_player_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/leaderboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="app-shell app-shell-authenticated"', response.data)
        self.assertIn(b'data-shell-user="', response.data)
        self.assertIn(b'data-shell-scope="league-1"', response.data)
        self.assertIn(b'data-page-key="/leaderboard"', response.data)
        self.assertIn(b'data-page-frame', response.data)
        self.assertIn(b"bfl-shell-scroll:", response.data)
        self.assertIn(b"bfl-shell-details:", response.data)
        self.assertIn(b"history.scrollRestoration = \"manual\"", response.data)
        self._delete_player(username)

    def test_logged_in_footer_exposes_hall_of_fame_link(self):
        username = f"footer_player_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'href="/hall-of-fame">Hall of Fame</a>', response.data)
        self.assertIn(b'href="/my-notifications">My Notifications</a>', response.data)
        self.assertIn(b'class="link-button nav-button nav-button-logout"', response.data)
        self.assertIn(b'class="link-button footer-link-button footer-link-button-logout"', response.data)
        self._delete_player(username)

    def test_contact_page_is_public_and_safe(self):
        response = self.client.get("/contact")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Platform Contact", response.data)
        self.assertIn(b"support@buhurtfantasyleague.example", response.data)
        self.assertNotIn(b"Top 3 Fighters", response.data)

    def test_rules_page_uses_live_settings_and_scoring(self):
        response = self.client.get("/rules")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"rules-hero", response.data)
        self.assertIn(b"Roster Rules", response.data)
        self.assertIn(b"Points System", response.data)
        self.assertIn(b"Team budget", response.data)
        self.assertIn(b"Cost Adjustments", response.data)
        self.assertIn(b"How the six traits are calculated", response.data)
        self.assertIn(b"Crowd Favourite", response.data)
        self.assertIn(b"Using the Rules", response.data)
        self.assertIn(b"6 headline traits", response.data)
        self.assertIn(b"Back to Home", response.data)

    def test_event_results_uses_shared_fighter_and_team_cards(self):
        username = f"event_cards_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        scheduled_event_id = self._create_scheduled_event(f"Shared Cards {uuid.uuid4().hex[:6]}", "2026-12-31")
        self._create_event_result(scheduled_event_id, 1, gold_medals=1, kills=3)

        response = self.client.get("/events/results")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"fighter-card-shell", response.data)
        self.assertIn(b"shared-team-card", response.data)
        self.assertIn(b"Leaderboard Impact", response.data)
        self.assertIn(b"Readable Result Feed", response.data)
        self._delete_player(username)

    def test_teams_page_stays_focused_without_tournament_panel(self):
        username = f"teams_focus_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        response = self.client.get("/teams")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"Upcoming Tournaments", response.data)
        self.assertNotIn(b"League Updates", response.data)
        self.assertIn(b"shared-team-card", response.data)
        self.assertIn(b"team-card-hero", response.data)
        self._delete_player(username)

    def test_admin_updates_are_only_visible_in_admin_section(self):
        self._login_admin()

        teams_response = self.client.get("/teams")
        admin_response = self.client.get("/admin")
        updates_response = self.client.get("/admin/notifications")

        self.assertEqual(teams_response.status_code, 200)
        self.assertNotIn(b"League Updates", teams_response.data)
        self.assertIn(b"Platform Shortcuts", admin_response.data)
        self.assertIn(b"Admin - Platform Notices", updates_response.data)

    def test_non_admin_cannot_access_audit_log(self):
        username = f"audit_player_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/admin/audit")

        self.assertEqual(response.status_code, 403)
        self._delete_player(username)

    def test_admin_events_page_allows_manual_results_without_scheduled_events(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute("DELETE FROM event_banners")
            conn.execute("UPDATE event_results SET scheduled_event_id=NULL")
            conn.commit()
        response = self.client.get("/admin/events")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Live Scoring Workspace", response.data)
        self.assertIn(b"Quick single-result fallback", response.data)
        self.assertIn(b"No scheduled event", response.data)
        self.assertIn(b"Event Name", response.data)
        self.assertIn(b"Event Date", response.data)

    def test_tournament_date_parser_handles_uk_event_ranges(self):
        start_date, display = app_module.parse_event_date_range("27th & 28th June 2026")

        self.assertEqual(start_date, "2026-06-27")
        self.assertEqual(display, "27-28 June 2026")

    def test_tournament_fallback_is_available_without_network(self):
        events = app_module.fallback_buhurt_uk_tournaments()

        self.assertGreaterEqual(len(events), 1)
        self.assertIn("name", events[0])
        self.assertIn("url", events[0])

    def test_tier_theme_mapping_covers_known_and_unknown_values(self):
        self.assertEqual(app_module.tier_theme("Tier 1")["class_name"], "tier-1")
        self.assertEqual(app_module.tier_theme("Tier 2")["class_name"], "tier-2")
        self.assertEqual(app_module.tier_theme("Tier 3")["class_name"], "tier-3")
        self.assertEqual(app_module.tier_theme("Tier 4")["class_name"], "tier-4")
        self.assertEqual(app_module.tier_theme("Tier 7")["class_name"], "tier-4")
        self.assertEqual(app_module.tier_theme("Unknown")["class_name"], "tier-unknown")
        self.assertEqual(app_module.tier_theme(None)["class_name"], "tier-unknown")

    def test_public_fighter_display_helper_hides_points_and_exposes_ambiguous_summary(self):
        display = app_module.public_fighter_display(
            {
                "rank": 2,
                "nickname": "The Wall",
                "total_points": 999,
                "glory": 88,
                "discipline_rating": 76,
                "lethality": 91,
                "resilience": 64,
                "crowd_favourite": 59,
                "synergy": 73,
            },
            context="home",
        )

        self.assertEqual(display["spotlight_label"], "Top Performer")
        self.assertEqual(display["form_label"], "Elite")
        self.assertEqual(display["summary"], "The Wall")
        self.assertEqual(
            [stat["label"] for stat in display["stats"]],
            ["Glory", "Discipline", "Lethality", "Resilience", "Crowd Favourite", "Synergy"],
        )
        self.assertNotIn("Points", [stat["label"] for stat in display["stats"]])

    def test_public_profile_ratings_match_workbook_style_normalization(self):
        rows = [
            {
                "name": "Alex F",
                "training": 4,
                "competitions": 0,
                "rounds_fought": 0,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 0,
                "silver_medals": 0,
                "bronze_medals": 0,
                "kills": 0,
                "assists": 0,
                "deaths": 0,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0,
                "kd_ratio": 0,
            },
            {
                "name": "Discipline Max",
                "training": 10,
                "competitions": 6,
                "rounds_fought": 0,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 0,
                "silver_medals": 0,
                "bronze_medals": 0,
                "kills": 0,
                "assists": 0,
                "deaths": 0,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0,
                "kd_ratio": 0,
            },
            {
                "name": "Lethality Max",
                "training": 0,
                "competitions": 0,
                "rounds_fought": 1,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 0,
                "silver_medals": 0,
                "bronze_medals": 0,
                "kills": 9,
                "assists": 0,
                "deaths": 1,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0,
                "kd_ratio": 9,
            },
            {
                "name": "Resilience Max",
                "training": 0,
                "competitions": 0,
                "rounds_fought": 22,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 0,
                "silver_medals": 0,
                "bronze_medals": 0,
                "kills": 0,
                "assists": 0,
                "deaths": 0,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0,
                "kd_ratio": 0,
            },
            {
                "name": "Crowd Max",
                "training": 0,
                "competitions": 0,
                "rounds_fought": 0,
                "support": 0,
                "special_awards": 1,
                "gold_medals": 0,
                "silver_medals": 2,
                "bronze_medals": 0,
                "kills": 32,
                "assists": 0,
                "deaths": 0,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0.6,
                "kd_ratio": 0,
            },
            {
                "name": "Synergy Max",
                "training": 0,
                "competitions": 6,
                "rounds_fought": 0,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 0,
                "silver_medals": 0,
                "bronze_medals": 0,
                "kills": 0,
                "assists": 5,
                "deaths": 0,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0,
                "kd_ratio": 0,
            },
            {
                "name": "Bruna",
                "training": 9,
                "competitions": 3,
                "rounds_fought": 13,
                "support": 0,
                "special_awards": 0,
                "gold_medals": 4,
                "silver_medals": 2,
                "bronze_medals": 0,
                "kills": 10,
                "assists": 1,
                "deaths": 4,
                "sit_downs": 0,
                "yellow_cards": 0,
                "red_cards": 0,
                "ownership_percent": 0.6,
                "kd_ratio": 2.5,
            },
        ]

        app_module.apply_public_profile_ratings(rows)
        bruna = next(row for row in rows if row["name"] == "Bruna")

        self.assertEqual(bruna["glory"], 100)
        self.assertEqual(bruna["discipline_rating"], 64)
        self.assertEqual(bruna["lethality"], 28)
        self.assertEqual(bruna["resilience"], 41)
        self.assertEqual(bruna["crowd_favourite"], 94)
        self.assertEqual(bruna["synergy"], 36)

    def test_admin_team_builder_renders_interactive_framework(self):
        self._login_admin()
        response = self.client.get("/admin/teams/new")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Team Builder Wizard", response.data)
        self.assertIn(b"Step 1", response.data)
        self.assertIn(b"Step 2", response.data)
        self.assertIn(b'id="team-builder-form"', response.data)
        self.assertIn(b'id="selected-fighter-grid"', response.data)
        self.assertIn(b'id="available-fighter-grid"', response.data)
        self.assertIn(b'id="team-roster-grid"', response.data)
        self.assertIn(b"const fighterProfiles", response.data)
        self.assertIn(b"refreshBuilder", response.data)

    def test_admin_team_builder_exposes_roster_slots(self):
        self._login_admin()
        response = self.client.get("/admin/teams/new")

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data.count(b'name="fighter_ids"'), 5)
        self.assertIn(b"Continue to Fighter Selection", response.data)
        self.assertIn(b"Back to Team Details", response.data)
        self.assertIn(b"Live Team Summary", response.data)
        self.assertIn(b"Selected Fighter Windows", response.data)
        self.assertIn(b"Add to Team", response.data)
        self.assertIn(b"Drag a fighter card here", response.data)
        self.assertIn(b'id="builder-live-feedback"', response.data)
        self.assertIn(b"Already in your roster.", response.data)
        self.assertIn(b"Remove a fighter before adding another.", response.data)
        self.assertIn(b'id="fighter-search"', response.data)
        self.assertIn(b'id="fighter-tier-filter"', response.data)
        self.assertIn(b'id="fighter-status-filter"', response.data)

    def test_admin_creates_player_with_single_team_access(self):
        self._login_admin()
        username = f"limit_{uuid.uuid4().hex[:8]}"
        token = self._csrf_from("/admin/players/new?league_id=1")

        response = self.client.post(
            "/admin/players/new?league_id=1",
            data={
                "_csrf_token": token,
                "display_name": "Limit Test Player",
                "username": username,
                "password": "player123",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No team yet", response.data)
        self.assertNotIn(b"Manager Slots", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute(
                """
                SELECT lm.manager_limit
                FROM league_memberships lm
                JOIN users u ON u.id = lm.user_id
                WHERE u.username=?
                ORDER BY lm.id DESC
                LIMIT 1
                """,
                (username,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)
        self._delete_player(username)

    def test_admin_team_assignment_respects_one_team_per_player(self):
        self._login_admin()
        username = f"capped_{uuid.uuid4().hex[:8]}"
        token = self._csrf_from("/admin/players/new?league_id=1")
        self.client.post(
            "/admin/players/new?league_id=1",
            data={
                "_csrf_token": token,
                "display_name": "Capped Player",
                "username": username,
                "password": "player123",
            },
        )
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            player_id = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]

        token = self._csrf_from("/admin/teams/new")
        first_response = self.client.post(
            "/admin/teams/new",
            data={
                "_csrf_token": token,
                "team_name": f"First Team {uuid.uuid4().hex[:8]}",
                "manager": f"First Manager {uuid.uuid4().hex[:8]}",
                "player_user_id": str(player_id),
            },
            follow_redirects=True,
        )
        self.assertEqual(first_response.status_code, 200)

        token = self._csrf_from("/admin/teams/new")
        second_response = self.client.post(
            "/admin/teams/new",
            data={
                "_csrf_token": token,
                "team_name": f"Second Team {uuid.uuid4().hex[:8]}",
                "manager": f"Second Manager {uuid.uuid4().hex[:8]}",
                "player_user_id": str(player_id),
            },
        )

        self.assertEqual(second_response.status_code, 400)
        self.assertIn(b"already has a team in this league", second_response.data.lower())
        self._delete_player(username)

    def test_non_admin_cannot_access_end_season_workflow(self):
        username = f"season_player_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/admin/season/end")

        self.assertEqual(response.status_code, 403)
        self._delete_player(username)

    def test_non_admin_cannot_access_season_settings(self):
        username = f"season_settings_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/admin/season/settings")

        self.assertEqual(response.status_code, 403)
        self._delete_player(username)

    def test_hall_of_fame_shows_empty_state_without_completed_seasons(self):
        username = f"hall_empty_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute("DELETE FROM seasons")
            conn.commit()
        response = self.client.get("/hall-of-fame")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No completed seasons yet", response.data)
        self._delete_player(username)

    def test_hall_of_fame_uses_completed_season_snapshots(self):
        self._login_admin()
        self.client.post(
            "/admin/season/end",
            data={
                "_csrf_token": self._csrf_from("/admin/season/end"),
                "confirmation_text": "END SEASON",
            },
            follow_redirects=True,
        )
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            season = conn.execute("SELECT * FROM seasons ORDER BY id DESC LIMIT 1").fetchone()
            fighter_snapshot = conn.execute(
                "SELECT fighter_id, name, tier FROM season_fighter_snapshots WHERE season_id=? ORDER BY rank, name LIMIT 1",
                (season["id"],),
            ).fetchone()
            conn.execute("UPDATE fighters SET tier='Tier 4', current_cost=999 WHERE id=?", (fighter_snapshot["fighter_id"],))
            conn.commit()

        username = f"hall_snapshot_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        response = self.client.get(f"/hall-of-fame?season={season['id']}&fighter={fighter_snapshot['name']}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(season["name"].encode("utf-8"), response.data)
        self.assertIn(fighter_snapshot["name"].encode("utf-8"), response.data)
        self.assertIn(fighter_snapshot["tier"].encode("utf-8"), response.data)
        self.assertNotIn(b"Snapshot score", response.data)

        self._login_admin()
        self._reopen_latest_season()
        self._delete_player(username)

    def test_cost_change_formula_is_predictable_and_clamped(self):
        fighters = [
            {"id": 1, "name": "Alpha", "current_cost": 100},
            {"id": 2, "name": "Beta", "current_cost": 100},
        ]
        teams = [
            {"fighters": [{"id": 1}]},
            {"fighters": [{"id": 1}]},
            {"fighters": [{"id": 2}]},
            {"fighters": []},
        ]
        formula = {
            "target_pick_rate": 0.2,
            "sensitivity": 1.0,
            "adjustment_cap": 0.2,
            "round_unit": 5,
            "min_cost": 25,
            "max_cost": 250,
        }

        changes = {row["fighter_id"]: row for row in app_module.calculate_season_cost_changes(fighters, teams, formula)}

        self.assertEqual(changes[1]["pick_rate"], 0.5)
        self.assertEqual(changes[1]["new_cost"], 120)
        self.assertEqual(changes[2]["pick_rate"], 0.25)
        self.assertEqual(changes[2]["new_cost"], 105)

    def test_admin_can_end_season_and_store_snapshots(self):
        self._login_admin()
        response = self.client.post(
            "/admin/season/end",
            data={
                "_csrf_token": self._csrf_from("/admin/season/end"),
                "confirmation_text": "END SEASON",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ended successfully", response.data.lower())
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            season = conn.execute("SELECT * FROM seasons ORDER BY id DESC LIMIT 1").fetchone()
            self.assertEqual(season["status"], "completed")
            self.assertEqual(season["locked"], 1)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM season_team_snapshots WHERE season_id=?", (season["id"],)).fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM season_fighter_snapshots WHERE season_id=?", (season["id"],)).fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM season_cost_changes WHERE season_id=?", (season["id"],)).fetchone()[0], 0)
            self.assertGreater(conn.execute("SELECT COUNT(*) FROM audit_logs WHERE entity_type='fighter_cost' AND action='season_cost_update'").fetchone()[0], 0)

        self._reopen_latest_season()

    def test_admin_can_update_season_settings_name_and_status_only(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            season = conn.execute("SELECT * FROM seasons WHERE status='active' ORDER BY id DESC LIMIT 1").fetchone()
            original_budget = conn.execute("SELECT value FROM settings WHERE key='team_budget'").fetchone()[0]
            original_training = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]

        response = self.client.post(
            "/admin/season/settings",
            data={
                "_csrf_token": self._csrf_from("/admin/season/settings"),
                "season_name": "Championship Season",
                "season_status": "active",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Season settings updated.", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            updated_season = conn.execute("SELECT * FROM seasons WHERE id=?", (season["id"],)).fetchone()
            settings = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}
            rules = {row["key"]: row["points"] for row in conn.execute("SELECT key, points FROM rules WHERE key IN ('training','support')")}
        self.assertEqual(updated_season["name"], "Championship Season")
        self.assertEqual(settings["team_budget"], original_budget)
        self.assertEqual(rules["training"], original_training)

    def test_admin_can_update_rules_attendance_visibility_and_cost_formula_settings(self):
        self._login_admin()

        response = self.client.post(
            "/admin/rules",
            data={
                "_csrf_token": self._csrf_from("/admin/rules"),
                **self._rule_form_fields(),
                "training_points": "6",
                "support_points": "4",
                "team_budget": "640",
                "minimum_team_size": "5",
                "maximum_team_size": "7",
                "tier_1_cost": "100",
                "tier_2_cost": "75",
                "tier_3_cost": "50",
                "season_pick_rate_target": "0.25",
                "season_cost_sensitivity": "1.5",
                "season_cost_adjustment_cap": "0.15",
                "season_cost_round_unit": "10",
                "season_min_cost": "30",
                "season_max_cost": "260",
                "public_fighter_scores_visible": "1",
                "cost_mode": "Current Season",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Rules and settings updated.", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            settings = {row[0]: row[1] for row in conn.execute("SELECT key, value FROM settings")}
            rules = {row[0]: row[1] for row in conn.execute("SELECT key, points FROM rules WHERE key IN ('training','support')")}
        self.assertEqual(settings["team_budget"], "640")
        self.assertEqual(settings["maximum_team_size"], "7")
        self.assertEqual(settings["season_pick_rate_target"], "0.25")
        self.assertEqual(settings["season_cost_sensitivity"], "1.5")
        self.assertEqual(settings["season_cost_adjustment_cap"], "0.15")
        self.assertEqual(settings["season_cost_round_unit"], "10")
        self.assertEqual(settings["season_min_cost"], "30")
        self.assertEqual(settings["season_max_cost"], "260")
        self.assertEqual(settings["public_fighter_scores_visible"], "1")
        self.assertEqual(rules["training"], 6)
        self.assertEqual(rules["support"], 4)

        self.client.post(
            "/logout",
            data={"_csrf_token": self._csrf_from("/")},
            follow_redirects=True,
        )
        public_response = self.client.get("/fighters/1")
        self.assertEqual(public_response.status_code, 302)
        self.assertIn("/login", public_response.headers["Location"])

    def test_completed_season_locks_rules_results_and_team_changes_until_reopened(self):
        self._login_admin()
        self.client.post(
            "/admin/season/end",
            data={
                "_csrf_token": self._csrf_from("/admin/season/end"),
                "confirmation_text": "END SEASON",
            },
            follow_redirects=True,
        )

        rules_response = self.client.post(
            "/admin/rules",
            data={
                "_csrf_token": self._csrf_from("/admin/rules"),
                "team_budget": "500",
                "minimum_team_size": "5",
                "maximum_team_size": "8",
                "tier_1_cost": "100",
                "tier_2_cost": "75",
                "tier_3_cost": "50",
                "cost_mode": "Current Season",
                "season_pick_rate_target": "0.2",
                "season_cost_sensitivity": "1.0",
                "season_cost_adjustment_cap": "0.2",
                "season_cost_round_unit": "5",
                "season_min_cost": "25",
                "season_max_cost": "250",
                **self._rule_form_fields(),
            },
            follow_redirects=True,
        )
        self.assertIn(b"locked because", rules_response.data.lower())

        team_response = self.client.post(
            "/admin/teams/new",
            data={
                "_csrf_token": self._csrf_from("/admin/teams/new"),
                "team_name": f"Locked Team {uuid.uuid4().hex[:8]}",
                "manager": f"Locked Manager {uuid.uuid4().hex[:8]}",
            },
        )
        self.assertEqual(team_response.status_code, 400)
        self.assertIn(b"locked because", team_response.data.lower())

        event_response = self.client.post(
            "/admin/events",
            data={
                "_csrf_token": self._csrf_from("/admin/events"),
                "scheduled_event_id": "1",
                "fighter_id": "1",
                "gold_medals": "0",
                "silver_medals": "0",
                "bronze_medals": "0",
                "kills": "0",
                "deaths": "0",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )
        self.assertIn(b"locked because", event_response.data.lower())

        reopen_response = self.client.post(
            "/admin/season/reopen",
            data={"_csrf_token": self._csrf_from("/admin/season/end")},
            follow_redirects=True,
        )
        self.assertEqual(reopen_response.status_code, 200)
        self.assertIn(b"reopened", reopen_response.data.lower())

    def test_admin_cannot_create_duplicate_team_name(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            existing_name = conn.execute("SELECT team_name FROM fantasy_teams ORDER BY id LIMIT 1").fetchone()[0]

        token = self._csrf_from("/admin/teams/new")
        response = self.client.post(
            "/admin/teams/new",
            data={
                "_csrf_token": token,
                "team_name": existing_name,
                "manager": f"Unique Manager {uuid.uuid4().hex[:8]}",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"team name is already in use", response.data.lower())

    def test_player_can_create_team_when_manager_slot_available(self):
        username = f"builder_{uuid.uuid4().hex[:8]}"
        player_id = self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/my-team/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Team Builder Wizard", response.data)
        self.assertIn(b'name="player_user_id"', response.data)

        token = self._csrf_from("/my-team/new")
        team_name = f"Player Built {uuid.uuid4().hex[:8]}"
        manager = f"Player Manager {uuid.uuid4().hex[:8]}"
        response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": token,
                "team_name": team_name,
                "manager": manager,
                "player_user_id": "999999",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(team_name.encode("utf-8"), response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            linked = conn.execute("SELECT player_user_id FROM fantasy_teams WHERE team_name=?", (team_name,)).fetchone()
        self.assertEqual(linked[0], player_id)
        self._delete_player(username)

    def test_claim_account_page_shows_assigned_league(self):
        league_id = self._create_league(f"claim-{uuid.uuid4().hex[:8]}", "Claim League")
        username = f"claim_player_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="player", league_id=league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                user_id = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
                invite = app_module.create_claim_token(conn, user_id)
                conn.commit()

            response = self.client.get(f"/claim/{invite['token']}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Claim League", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_logged_in_user_can_join_second_league_with_join_code(self):
        home_league_id = self._create_league(f"join-home-{uuid.uuid4().hex[:8]}", "Join Home League")
        target_league_id = self._create_league(f"join-target-{uuid.uuid4().hex[:8]}", "Join Target League")
        username = f"joiner_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="player", league_id=home_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                join_code = conn.execute("SELECT join_code FROM leagues WHERE id=?", (target_league_id,)).fetchone()[0]

            self._login_user(username, "player123")
            response = self.client.post(
                "/join-league",
                data={
                    "_csrf_token": self._csrf_from("/join-league"),
                    "code": join_code,
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"You joined Join Target League.", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                membership = conn.execute(
                    """
                    SELECT league_memberships.role, league_memberships.manager_limit
                    FROM league_memberships
                    JOIN users u ON u.id = league_memberships.user_id
                    WHERE u.username=? AND league_memberships.league_id=?
                    """,
                    (username, target_league_id),
                ).fetchone()
            self.assertIsNotNone(membership)
            self.assertEqual(membership[0], "player")
            self.assertEqual(membership[1], 1)
            with self.client.session_transaction() as session_state:
                self.assertEqual(session_state["active_league_id"], target_league_id)
        finally:
            self._cleanup_league_data(home_league_id)
            self._cleanup_league_data(target_league_id)
            self._delete_player(username)

    def test_join_league_code_respects_player_quota(self):
        full_league_id = self._create_league(f"join-full-{uuid.uuid4().hex[:8]}", "Join Full League")
        home_league_id = self._create_league(f"join-player-{uuid.uuid4().hex[:8]}", "Join Player League")
        existing_username = f"full_member_{uuid.uuid4().hex[:8]}"
        joiner_username = f"blocked_joiner_{uuid.uuid4().hex[:8]}"

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("UPDATE leagues SET max_players=1 WHERE id=?", (full_league_id,))
                conn.commit()
            self._create_user(existing_username, role="player", league_id=full_league_id)
            self._create_user(joiner_username, role="player", league_id=home_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                join_code = conn.execute("SELECT join_code FROM leagues WHERE id=?", (full_league_id,)).fetchone()[0]

            self._login_user(joiner_username, "player123")
            response = self.client.post(
                "/join-league",
                data={
                    "_csrf_token": self._csrf_from("/join-league"),
                    "code": join_code,
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(b"Player quota reached", response.data)
        finally:
            self._cleanup_league_data(full_league_id)
            self._cleanup_league_data(home_league_id)
            self._delete_player(existing_username)
            self._delete_player(joiner_username)

    def test_player_login_lands_in_their_league_context(self):
        league_id = self._create_league(f"login-{uuid.uuid4().hex[:8]}", "Login League")
        username = f"login_player_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="player", league_id=league_id)
            self._login_user(username, "player123")

            response = self.client.get("/my-team")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Login League", response.data)
            self.assertIn(b"League: Login League", response.data)
            self.assertIn(b"<title>", response.data)
            self.assertIn(b"Login League | Buhurt Fantasy League", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_login_sets_active_league_id_in_session(self):
        self._login_user("gk", "player123")

        with self.client.session_transaction() as session_state:
            self.assertEqual(session_state.get("active_league_id"), 1)

    def test_player_cannot_view_another_leagues_team_by_url(self):
        league_id = self._create_league(f"player-team-view-{uuid.uuid4().hex[:8]}", "Player Team View League")
        username = f"team_view_player_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="player", league_id=league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                foreign_team = conn.execute("SELECT id, team_name FROM fantasy_teams WHERE league_id=1 ORDER BY id LIMIT 1").fetchone()

            self._login_user(username, "player123")

            teams_response = self.client.get("/teams")
            detail_response = self.client.get(f"/teams/{foreign_team[0]}")

            self.assertEqual(teams_response.status_code, 200)
            self.assertNotIn(foreign_team[1].encode("utf-8"), teams_response.data)
            self.assertEqual(detail_response.status_code, 404)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_player_cannot_create_duplicate_team_name(self):
        username = f"dupe_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        with sqlite3.connect(app_module.DB_PATH) as conn:
            existing_name = conn.execute("SELECT team_name FROM fantasy_teams ORDER BY id LIMIT 1").fetchone()[0]

        token = self._csrf_from("/my-team/new")
        response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": token,
                "team_name": existing_name,
                "manager": f"Dupe Manager {uuid.uuid4().hex[:8]}",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"team name is already in use", response.data.lower())
        self._delete_player(username)

    def test_player_can_upload_team_image_when_creating_team(self):
        username = f"image_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        token = self._csrf_from("/my-team/new")
        team_name = f"Image Team {uuid.uuid4().hex[:8]}"
        response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": token,
                "team_name": team_name,
                "manager": f"Image Manager {uuid.uuid4().hex[:8]}",
                "team_image": (BytesIO(b"fake png content"), "crest.png"),
                "image_credit": "Test Photographer",
                "image_source_url": "https://example.com/team-photo",
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"team-hero-image", response.data)
        self.assertIn(b"Test Photographer", response.data)
        self.assertIn(b"https://example.com/team-photo", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute("SELECT image_path, image_credit, image_source_url FROM fantasy_teams WHERE team_name=?", (team_name,)).fetchone()
        self.assertTrue(row[0].startswith("uploads/teams/team-"))
        self.assertEqual(row[1], "Test Photographer")
        self.assertEqual(row[2], "https://example.com/team-photo")
        self._delete_player(username)

    def test_admin_can_add_fighter_image_attribution(self):
        self._login_admin()
        fighter_name = f"Credit Fighter {uuid.uuid4().hex[:8]}"
        token = self._csrf_from("/admin/fighters/new")

        response = self.client.post(
            "/admin/fighters/new",
            data={
                "_csrf_token": token,
                "name": fighter_name,
                "tier": "Tier 3",
                "age": "29",
                "joined_year": "2021",
                "height": "",
                "weight": "",
                "current_cost": "50",
                "training": "0",
                "support": "0",
                "nickname": "The Wall",
                "fighting_style": "",
                "preferred_role": "",
                "role_or_weapon": "Poleaxe",
                "known_for": "Relentless defence",
                "why_buhurt": "For the challenge and team spirit",
                "reputation": "",
                "image_url": "https://example.com/fighter.jpg",
                "image_credit": "Fighter Photographer",
                "image_source_url": "https://example.com/fighter-source",
                "hero_quote": "",
                "notes": "Steady presence",
                "bio": "An experienced league veteran.",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, age, joined_year, role_or_weapon, known_for, why_buhurt, image_credit, image_source_url FROM fighters WHERE name=?",
                (fighter_name,),
            ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 29)
        self.assertEqual(row[2], 2021)
        self.assertEqual(row[3], "Poleaxe")
        self.assertEqual(row[4], "Relentless defence")
        self.assertEqual(row[5], "For the challenge and team spirit")
        self.assertEqual(row[6], "Fighter Photographer")
        self.assertEqual(row[7], "https://example.com/fighter-source")

        detail_response = self.client.get(f"/fighters/{row[0]}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(b"fighter-card-shell", detail_response.data)
        self.assertIn(b"Current Fantasy Read", detail_response.data)
        self.assertIn(b"Lifetime Fighter History", detail_response.data)
        self.assertIn(b"Event-by-Event History", detail_response.data)
        self.assertNotIn(b"Performance Snapshot", detail_response.data)
        self.assertIn(b"The Wall", detail_response.data)
        self.assertIn(b"Poleaxe", detail_response.data)
        self.assertIn(b"Relentless defence", detail_response.data)
        self.assertIn(b"For the challenge and team spirit", detail_response.data)
        self.assertIn(b"2021", detail_response.data)
        self.assertIn(b"Fighter Photographer", detail_response.data)
        self.assertIn(b"https://example.com/fighter-source", detail_response.data)

        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute("DELETE FROM baseline_stats WHERE fighter_id=?", (row[0],))
            conn.execute("DELETE FROM fighters WHERE id=?", (row[0],))

    def test_admin_fighters_page_exposes_quick_attendance_controls(self):
        self._login_admin()
        response = self.client.get("/admin/fighters")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Training Workspace", response.data)
        self.assertIn(b"+ Training", response.data)
        self.assertIn(b"+ Support", response.data)
        self.assertIn(b"Session note", response.data)
        self.assertIn(b"Quick upkeep", response.data)
        self.assertIn(b"Bulk Import Fighters", response.data)
        self.assertNotIn(b"<th>Cost</th>", response.data)
        self.assertNotIn(b"<th>Total</th>", response.data)
        self.assertNotIn(b"Reviewing fighters for", response.data)

    def test_admin_can_add_training_from_fighter_page(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            fighter = conn.execute("SELECT id, name FROM fighters ORDER BY id LIMIT 1").fetchone()
            training_rule = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
            baseline_before = conn.execute("SELECT training FROM baseline_stats WHERE fighter_id=?", (fighter["id"],)).fetchone()[0]
        before_conn = sqlite3.connect(app_module.DB_PATH)
        before_conn.row_factory = sqlite3.Row
        before_rows = {row["id"]: row for row in app_module.leaderboard_rows(before_conn)}
        before_conn.close()

        response = self.client.post(
            f"/admin/fighters/{fighter['id']}/attendance",
            data={
                "_csrf_token": self._csrf_from("/admin/fighters"),
                "score_type": "training",
                "attendance_date": "2026-05-05",
                "score_units": "1",
                "note": f"Quick session {uuid.uuid4().hex[:6]}",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Training added", response.data)
        after_conn = sqlite3.connect(app_module.DB_PATH)
        after_conn.row_factory = sqlite3.Row
        after_rows = {row["id"]: row for row in app_module.leaderboard_rows(after_conn)}
        after_conn.close()
        self.assertEqual(after_rows[fighter["id"]]["training"], before_rows[fighter["id"]]["training"] + 1)
        self.assertEqual(after_rows[fighter["id"]]["total_points"], before_rows[fighter["id"]]["total_points"] + training_rule)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            baseline_after = conn.execute("SELECT training FROM baseline_stats WHERE fighter_id=?", (fighter["id"],)).fetchone()[0]
            self.assertEqual(baseline_after, baseline_before + 1)
            audit = conn.execute(
                "SELECT message FROM audit_logs WHERE entity_type='fighter' AND entity_id=? ORDER BY id DESC LIMIT 1",
                (fighter["id"],),
            ).fetchone()
            self.assertIsNotNone(audit)

    def test_admin_can_add_support_from_fighter_page(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            fighter = conn.execute("SELECT id FROM fighters ORDER BY id LIMIT 1").fetchone()
            support_rule = conn.execute("SELECT points FROM rules WHERE key='support'").fetchone()[0]
            baseline_before = conn.execute("SELECT support FROM baseline_stats WHERE fighter_id=?", (fighter["id"],)).fetchone()[0]
        before_conn = sqlite3.connect(app_module.DB_PATH)
        before_conn.row_factory = sqlite3.Row
        before_rows = {row["id"]: row for row in app_module.leaderboard_rows(before_conn)}
        before_conn.close()

        response = self.client.post(
            f"/admin/fighters/{fighter['id']}/attendance",
            data={
                "_csrf_token": self._csrf_from("/admin/fighters"),
                "score_type": "support",
                "attendance_date": "2026-05-06",
                "score_units": "1",
                "note": f"Pit crew {uuid.uuid4().hex[:6]}",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Support added", response.data)
        after_conn = sqlite3.connect(app_module.DB_PATH)
        after_conn.row_factory = sqlite3.Row
        after_rows = {row["id"]: row for row in app_module.leaderboard_rows(after_conn)}
        after_conn.close()
        self.assertEqual(after_rows[fighter["id"]]["support"], before_rows[fighter["id"]]["support"] + 1)
        self.assertEqual(after_rows[fighter["id"]]["total_points"], before_rows[fighter["id"]]["total_points"] + support_rule)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            baseline_after = conn.execute("SELECT support FROM baseline_stats WHERE fighter_id=?", (fighter["id"],)).fetchone()[0]
            self.assertEqual(baseline_after, baseline_before + 1)

    def test_edit_fighter_page_shows_updated_training_value(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            baseline_before = conn.execute("SELECT training FROM baseline_stats WHERE fighter_id=1").fetchone()[0]
        payload = {
            "_csrf_token": self._csrf_from("/admin/fighters"),
            "score_type": "training",
            "attendance_date": "2026-05-09",
            "score_units": "1",
            "note": "",
        }
        self.client.post("/admin/fighters/1/attendance", data=payload, follow_redirects=True)

        response = self.client.get("/admin/fighters/1")

        self.assertEqual(response.status_code, 200)
        expected = f'name="training" value="{baseline_before + 1}"'.encode()
        self.assertIn(expected, response.data)

    def test_non_admin_cannot_add_attendance_records(self):
        username = f"attendance_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.post(
            "/admin/fighters/1/attendance",
            data={
                "_csrf_token": self._csrf_from("/"),
                "score_type": "training",
                "attendance_date": "2026-05-07",
                "score_units": "1",
            },
        )

        self.assertEqual(response.status_code, 403)
        self._delete_player(username)

    def test_repeated_quick_training_updates_continue_to_increment_baseline(self):
        self._login_admin()
        note = f"Duplicate guard {uuid.uuid4().hex[:6]}"
        payload = {
            "_csrf_token": self._csrf_from("/admin/fighters"),
            "score_type": "training",
            "attendance_date": "2026-05-08",
            "score_units": "1",
            "note": note,
        }

        first = self.client.post("/admin/fighters/1/attendance", data=payload, follow_redirects=True)
        second = self.client.post(
            "/admin/fighters/1/attendance",
            data={**payload, "_csrf_token": self._csrf_from("/admin/fighters")},
            follow_redirects=True,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn(b"Training added", first.data)
        self.assertIn(b"Training added", second.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            total = conn.execute("SELECT training FROM baseline_stats WHERE fighter_id=1").fetchone()[0]
        self.assertGreaterEqual(total, 6)

    def test_training_workspace_supports_groups_and_fast_attendance_updates(self):
        league_id = self._create_league(f"training-{uuid.uuid4().hex[:8]}", "Training League")
        admin_username = f"training_admin_{uuid.uuid4().hex[:8]}"
        fighter_one_name = f"Training Fighter {uuid.uuid4().hex[:6]}"
        fighter_two_name = f"Training Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            fighter_one_id = self._create_fighter(fighter_one_name, league_id)
            fighter_two_id = self._create_fighter(fighter_two_name, league_id)
            self._login_user(admin_username, "player123")

            create_response = self.client.post(
                "/admin/training/groups",
                data={
                    "_csrf_token": self._csrf_from("/admin/training"),
                    "name": "Monday Drills",
                    "notes": "Core contact session",
                    "fighter_ids": [str(fighter_one_id), str(fighter_two_id)],
                },
                follow_redirects=True,
            )

            self.assertEqual(create_response.status_code, 200)
            self.assertIn(b"Training group Monday Drills created.", create_response.data)
            self.assertIn(b"Monday Drills", create_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                group_id = conn.execute(
                    "SELECT id FROM training_groups WHERE league_id=? AND name='Monday Drills'",
                    (league_id,),
                ).fetchone()[0]

            group_mark_response = self.client.post(
                f"/admin/training/groups/{group_id}/mark",
                data={
                    "_csrf_token": self._csrf_from("/admin/training"),
                    "score_type": "training",
                    "attendance_date": "2026-05-25",
                    "score_units": "1",
                    "note": "Team warmup",
                },
                follow_redirects=True,
            )

            self.assertEqual(group_mark_response.status_code, 200)
            self.assertIn(b"Training added for 2 fighters in Monday Drills.", group_mark_response.data)

            single_mark_response = self.client.post(
                f"/admin/training/groups/{group_id}/fighters/{fighter_one_id}/mark",
                data={
                    "_csrf_token": self._csrf_from("/admin/training"),
                    "score_type": "support",
                    "attendance_date": "2026-05-25",
                    "score_units": "1",
                    "note": "Equipment support",
                },
                follow_redirects=True,
            )

            self.assertEqual(single_mark_response.status_code, 200)
            self.assertIn(f"Support added for {fighter_one_name}.".encode(), single_mark_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                baseline_one = conn.execute(
                    "SELECT training, support FROM baseline_stats WHERE fighter_id=?",
                    (fighter_one_id,),
                ).fetchone()
                baseline_two = conn.execute(
                    "SELECT training, support FROM baseline_stats WHERE fighter_id=?",
                    (fighter_two_id,),
                ).fetchone()
            self.assertEqual(tuple(baseline_one), (1, 1))
            self.assertEqual(tuple(baseline_two), (1, 0))
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_training_workspace_is_scoped_to_current_league(self):
        own_league_id = self._create_league(f"training-own-{uuid.uuid4().hex[:8]}", "Own Training League")
        other_league_id = self._create_league(f"training-other-{uuid.uuid4().hex[:8]}", "Other Training League")
        admin_username = f"training_scope_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Own Training Fighter {uuid.uuid4().hex[:6]}"
        other_fighter_name = f"Other Training Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=own_league_id)
            self._create_fighter(own_fighter_name, own_league_id)
            other_fighter_id = self._create_fighter(other_fighter_name, other_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO training_groups(league_id, name, notes, sort_order, created_at, updated_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (other_league_id, "Other League Group", "", 1, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
                )
                other_group_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO training_group_members(training_group_id, fighter_id, position, created_at)
                    VALUES(?,?,?,?)
                    """,
                    (other_group_id, other_fighter_id, 1, "2026-01-01T00:00:00"),
                )
                conn.commit()

            self._login_user(admin_username, "player123")
            page = self.client.get("/admin/training")

            self.assertEqual(page.status_code, 200)
            self.assertIn(own_fighter_name.encode(), page.data)
            self.assertNotIn(other_fighter_name.encode(), page.data)
            self.assertNotIn(b"Other League Group", page.data)

            blocked = self.client.post(
                f"/admin/training/groups/{other_group_id}/mark",
                data={
                    "_csrf_token": self._csrf_from("/admin/training"),
                    "score_type": "training",
                    "attendance_date": "2026-05-25",
                    "score_units": "1",
                },
            )
            self.assertEqual(blocked.status_code, 404)
        finally:
            self._cleanup_league_data(own_league_id)
            self._cleanup_league_data(other_league_id)
            self._delete_player(admin_username)

    def test_admin_can_record_ad_hoc_fighter_award_without_event_workspace(self):
        league_id = self._create_league(f"awards-{uuid.uuid4().hex[:8]}", "Awards League")
        admin_username = f"awards_admin_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Award Fighter {uuid.uuid4().hex[:6]}"
        title = f"Captain Pick {uuid.uuid4().hex[:6]}"
        notes = "Recognised for exceptional team leadership."

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            fighter_id = self._create_fighter(fighter_name, league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/fighters/awards",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighters/awards"),
                    "fighter_id": str(fighter_id),
                    "honour_type": "gold_medals",
                    "units": "2",
                    "awarded_on": "2026-05-25",
                    "title": title,
                    "notes": notes,
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Award recorded.", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    """
                    SELECT honour_type, units, title, notes
                    FROM fighter_honours
                    WHERE fighter_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (fighter_id,),
                ).fetchone()
            self.assertEqual(row[0], "gold_medals")
            self.assertEqual(row[1], 2)
            self.assertEqual(row[2], title)
            self.assertEqual(row[3], notes)

            detail = self.client.get(f"/fighters/{fighter_id}")
            self.assertEqual(detail.status_code, 200)
            self.assertIn(title.encode(), detail.data)
            self.assertIn(b"Ad Hoc Honours", detail.data)
            self.assertIn(b"Gold 2", detail.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_cannot_record_award_for_another_leagues_fighter(self):
        league_id = self._create_league(f"awards-own-{uuid.uuid4().hex[:8]}", "Own Awards League")
        other_league_id = self._create_league(f"awards-other-{uuid.uuid4().hex[:8]}", "Other Awards League")
        admin_username = f"awards_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Own Award Fighter {uuid.uuid4().hex[:6]}"
        other_fighter_name = f"Other Award Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_fighter(own_fighter_name, league_id)
            other_fighter_id = self._create_fighter(other_fighter_name, other_league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/fighters/awards",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighters/awards"),
                    "fighter_id": str(other_fighter_id),
                    "honour_type": "special_awards",
                    "units": "1",
                    "awarded_on": "2026-05-25",
                    "title": "Should not land",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(b"Choose a fighter from this league.", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM fighter_honours WHERE fighter_id=?",
                    (other_fighter_id,),
                ).fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            self._cleanup_league_data(league_id)
            self._cleanup_league_data(other_league_id)
            self._delete_player(admin_username)

    def test_team_image_upload_rejects_non_images(self):
        username = f"badimage_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        token = self._csrf_from("/my-team/new")
        response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": token,
                "team_name": f"Bad Image {uuid.uuid4().hex[:8]}",
                "manager": f"Bad Image Manager {uuid.uuid4().hex[:8]}",
                "team_image": (BytesIO(b"not an image"), "notes.txt"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Team image must be", response.data)
        self._delete_player(username)

    def test_admin_can_delete_team_from_admin_page(self):
        self._login_admin()
        image_path = "uploads/teams/delete-test.webp"
        image_file = app_module.BASE_DIR / "static" / image_path
        image_file.parent.mkdir(parents=True, exist_ok=True)
        image_file.write_bytes(b"delete me")
        with sqlite3.connect(app_module.DB_PATH) as conn:
            cursor = conn.execute(
                "INSERT INTO fantasy_teams(team_name,manager,image_path) VALUES(?,?,?)",
                (f"Delete Team {uuid.uuid4().hex[:8]}", f"Delete Manager {uuid.uuid4().hex[:8]}", image_path),
            )
            team_id = cursor.lastrowid
            fighter_id = conn.execute("SELECT id FROM fighters ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("INSERT INTO fantasy_team_fighters(team_id,fighter_id,slot) VALUES(?,?,?)", (team_id, fighter_id, 1))
            conn.execute("INSERT INTO team_share_links(team_id,token,created_at) VALUES(?,?,?)", (team_id, f"delete-{uuid.uuid4().hex}", "2026-01-01T00:00:00"))

        token = self._csrf_from("/admin/teams")
        response = self.client.post(f"/admin/teams/{team_id}/delete", data={"_csrf_token": token}, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"deleted", response.data.lower())
        with sqlite3.connect(app_module.DB_PATH) as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM fantasy_teams WHERE id=?", (team_id,)).fetchone())
            self.assertIsNone(conn.execute("SELECT 1 FROM fantasy_team_fighters WHERE team_id=?", (team_id,)).fetchone())
            self.assertIsNone(conn.execute("SELECT 1 FROM team_share_links WHERE team_id=?", (team_id,)).fetchone())
        self.assertFalse(image_file.exists())

    def test_player_my_team_route_renders_my_teams_dashboard(self):
        username = f"myteams_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/my-team")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"My Team", response.data)
        self.assertIn(b"Create Team", response.data)
        self.assertNotIn(b'name="q"', response.data)
        self.assertNotIn(b'name="status"', response.data)
        self.assertNotEqual(response.request.path, "/teams")
        self._delete_player(username)

    def test_player_dashboard_route_renders_personal_home(self):
        username = f"playerdash_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")

        response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player Dashboard", response.data)
        self.assertIn(b"Next Live Event", response.data)
        self.assertIn(b"Next Actions", response.data)
        self.assertIn(b"My Team Snapshot", response.data)
        self.assertIn(b"Latest League Signal", response.data)
        self.assertIn(b'href="/dashboard">Dashboard</a>', response.data)
        self._delete_player(username)

    def test_player_team_views_use_six_trait_totals(self):
        username = f"teamtraits_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        team_name = f"Trait Team {uuid.uuid4().hex[:8]}"
        manager = f"Trait Manager {uuid.uuid4().hex[:8]}"
        create_response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": self._csrf_from("/my-team/new"),
                "team_name": team_name,
                "manager": manager,
                "fighter_ids": ["1", "2", "3", "4", "5"],
            },
            follow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn(b"Team Traits", create_response.data)
        self.assertIn(b"Glory", create_response.data)
        self.assertIn(b"Synergy", create_response.data)

        my_teams_response = self.client.get("/my-team")
        self.assertEqual(my_teams_response.status_code, 200)
        self.assertIn(b"shared-team-card", my_teams_response.data)
        self.assertIn(b"team-card-hero", my_teams_response.data)
        self.assertNotIn(b'name="q"', my_teams_response.data)
        self.assertNotIn(b'name="status"', my_teams_response.data)
        self.assertIn(b"Glory", my_teams_response.data)
        self.assertIn(b"Discipline", my_teams_response.data)
        self.assertIn(b"Crowd Favourite", my_teams_response.data)
        self._delete_player(username)

    def test_team_detail_shows_event_gains_history(self):
        username = f"eventgains_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        team_name = f"Gain Team {uuid.uuid4().hex[:8]}"
        manager = f"Gain Manager {uuid.uuid4().hex[:8]}"
        create_response = self.client.post(
            "/my-team/new",
            data={
                "_csrf_token": self._csrf_from("/my-team/new"),
                "team_name": team_name,
                "manager": manager,
                "fighter_ids": ["1", "2", "3", "4", "5"],
            },
            follow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn(b"Event Gains", create_response.data)
        self.assertIn(b"fighter-card-shell", create_response.data)
        self.assertTrue(
            b"No scored events yet." in create_response.data
            or b"Latest event gain" in self.client.get("/my-team").data
        )
        self._delete_player(username)

    def test_admin_nav_does_not_show_player_my_teams_link(self):
        self._login_admin()
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'href="/my-team">My Teams</a>', response.data)

    def test_player_cannot_create_team_without_manager_slots(self):
        username = f"blocked_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=0)
        self._login_user(username, "player123")

        response = self.client.get("/my-team/new", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"team creation is not enabled", response.data.lower())
        self.assertNotIn(b"Live Team Builder", response.data)
        self._delete_player(username)

    def test_fighters_page_supports_case_insensitive_search_and_filters(self):
        username = f"fighter_search_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        with sqlite3.connect(app_module.DB_PATH) as conn:
            fighters = conn.execute("SELECT name, tier FROM fighters ORDER BY name LIMIT 2").fetchall()
        target_name, target_tier = fighters[0]
        other_name = fighters[1][0]

        response = self.client.get(f"/fighters?q={target_name.lower()}&tier={target_tier}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(target_name.encode("utf-8"), response.data)
        self.assertNotIn(other_name.encode("utf-8"), response.data)
        self.assertIn(b'name="q"', response.data)
        self.assertIn(b'name="tier"', response.data)
        self.assertIn(b"Clear Filters", response.data)
        self.assertIn(b'data-filter-status', response.data)
        self.assertIn(b"toolbar-chip", response.data)
        self._delete_player(username)

    def test_homepage_highlights_latest_event_results(self):
        self._login_admin()
        scheduled_event_id = self._create_scheduled_event("York Grand Melee", "2026-12-31")
        alpha_team_id = self._create_team_with_roster(f"Event Alpha {uuid.uuid4().hex[:6]}", [1, 2])
        beta_team_id = self._create_team_with_roster(f"Event Beta {uuid.uuid4().hex[:6]}", [3])
        self._create_event_result(scheduled_event_id, 1, gold_medals=1, kills=5, deaths=1)
        self._create_event_result(scheduled_event_id, 2, silver_medals=1, kills=2, deaths=1)
        self._create_event_result(scheduled_event_id, 3, bronze_medals=1, kills=1, deaths=0)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"York Grand Melee", response.data)
        self.assertIn(b"Latest Completed Event", response.data)
        self.assertIn(b"Top 3 Fighters", response.data)
        self.assertIn(b"Top 3 Teams", response.data)
        self.assertIn(b"Best Event Gains", response.data)
        self.assertIn(b"Event Winner", response.data)
        self.assertIn(b"Event Alpha", response.data)
        self.assertIn(b"Event points", response.data)
        self.assertIn(b"Fantasy Team", response.data)
        self.assertIn(b"home-team-card", response.data)
        self.assertNotIn(b"Top ranked fighter by current points.", response.data)

    def test_homepage_hides_league_featured_content_for_logged_out_users(self):
        league_id = self._create_league(f"home-default-{uuid.uuid4().hex[:8]}", "Home Default League")
        own_fighter_name = f"Home Fighter {uuid.uuid4().hex[:6]}"
        own_team_name = f"Home Team {uuid.uuid4().hex[:6]}"

        try:
            fighter_id = self._create_fighter(own_fighter_name, league_id)
            team_id = self._create_team_with_roster(own_team_name, [fighter_id])
            scheduled_event_id = self._create_scheduled_event(f"Home Event {uuid.uuid4().hex[:6]}", "2026-12-30", league_id=league_id)
            self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=4)

            response = self.client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Welcome to Buhurt Fantasy League", response.data)
            self.assertIn(b"Members Only", response.data)
            self.assertNotIn(b"View Rules", response.data)
            self.assertNotIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertNotIn(own_team_name.encode("utf-8"), response.data)
            self.assertNotIn(b"Top 3 Fighters", response.data)
            self.assertNotIn(b"Top 3 Teams", response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_homepage_featured_content_switches_to_logged_in_league_context(self):
        league_id = self._create_league(f"home-switch-{uuid.uuid4().hex[:8]}", "Home Switch League")
        username = f"player_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Switch Fighter {uuid.uuid4().hex[:6]}"
        own_team_name = f"Switch Team {uuid.uuid4().hex[:6]}"
        own_event_name = f"Switch Event {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(username, role="player", league_id=league_id)
            fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._create_team_with_roster(own_team_name, [fighter_id])
            scheduled_event_id = self._create_scheduled_event(own_event_name, "2026-12-31", league_id=league_id)
            self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=5)
            self._login_user(username, "player123")

            response = self.client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League spotlight: Home Switch League", response.data)
            self.assertIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertIn(own_team_name.encode("utf-8"), response.data)
            self.assertIn(own_event_name.encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_homepage_can_switch_to_membership_based_active_league_context(self):
        league_id = self._create_league(f"home-membership-{uuid.uuid4().hex[:8]}", "Home Membership League")
        own_fighter_name = f"Membership Fighter {uuid.uuid4().hex[:6]}"
        own_team_name = f"Membership Team {uuid.uuid4().hex[:6]}"
        own_event_name = f"Membership Event {uuid.uuid4().hex[:6]}"

        try:
            fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._create_team_with_roster(own_team_name, [fighter_id])
            scheduled_event_id = self._create_scheduled_event(own_event_name, "2026-12-31", league_id=league_id)
            self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=5)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?, ?, 'player', 'active', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (2, league_id),
                )
                conn.commit()

            self._login_user("gk", "player123")
            with self.client.session_transaction() as session_state:
                session_state["active_league_id"] = league_id

            response = self.client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League spotlight: Home Membership League", response.data)
            self.assertIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertIn(own_team_name.encode("utf-8"), response.data)
            self.assertIn(own_event_name.encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_multi_league_member_can_switch_context_from_header(self):
        player_league_id = self._create_league(f"switch-player-{uuid.uuid4().hex[:8]}", "Switch Player League")
        admin_league_id = self._create_league(f"switch-admin-{uuid.uuid4().hex[:8]}", "Switch Admin League")
        username = f"switcher_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="player", league_id=player_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?, ?, 'league_admin', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (user_id, admin_league_id),
                )
                conn.commit()

            self._login_user(username, "player123")
            home_response = self.client.get("/")
            self.assertEqual(home_response.status_code, 200)
            self.assertIn(b'id="league-switcher"', home_response.data)
            self.assertIn(b"My Teams", home_response.data)
            self.assertNotIn(b"My League", home_response.data)

            switch_response = self.client.post(
                "/switch-league",
                data={
                    "_csrf_token": self._csrf_from("/"),
                    "league_id": str(admin_league_id),
                },
                follow_redirects=True,
            )

            self.assertEqual(switch_response.status_code, 200)
            self.assertIn(b"Switched to Switch Admin League.", switch_response.data)
            self.assertIn(b"My League", switch_response.data)
            self.assertIn(b"Admin", switch_response.data)
            self.assertNotIn(b"My Teams", switch_response.data)

            with self.client.session_transaction() as session_state:
                self.assertEqual(session_state["active_league_id"], admin_league_id)
        finally:
            self._cleanup_league_data(player_league_id)
            self._cleanup_league_data(admin_league_id)
            self._delete_player(username)

    def test_login_redirects_multi_league_member_to_select_league(self):
        first_league_id = self._create_league(f"choose-first-{uuid.uuid4().hex[:8]}", "Choose First League")
        second_league_id = self._create_league(f"choose-second-{uuid.uuid4().hex[:8]}", "Choose Second League")
        username = f"chooser_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="player", league_id=first_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?, ?, 'player', 'active', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (user_id, second_league_id),
                )
                conn.commit()

            response = self.client.post(
                "/login",
                data={
                    "_csrf_token": self._csrf_from("/login"),
                    "username": username,
                    "password": "player123",
                },
                follow_redirects=False,
            )

            self.assertEqual(response.status_code, 302)
            self.assertIn("/select-league", response.headers["Location"])
            with self.client.session_transaction() as session_state:
                self.assertNotIn("active_league_id", session_state)
                self.assertTrue(session_state.get("pending_league_selection"))
        finally:
            self._cleanup_league_data(first_league_id)
            self._cleanup_league_data(second_league_id)
            self._delete_player(username)

    def test_select_league_sets_active_context_after_login(self):
        player_league_id = self._create_league(f"pick-player-{uuid.uuid4().hex[:8]}", "Pick Player League")
        admin_league_id = self._create_league(f"pick-admin-{uuid.uuid4().hex[:8]}", "Pick Admin League")
        username = f"picker_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="player", league_id=player_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?, ?, 'league_admin', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (user_id, admin_league_id),
                )
                conn.commit()

            self.client.post(
                "/login",
                data={
                    "_csrf_token": self._csrf_from("/login"),
                    "username": username,
                    "password": "player123",
                },
                follow_redirects=False,
            )
            chooser_page = self.client.get("/select-league")
            self.assertEqual(chooser_page.status_code, 200)
            self.assertIn(b"Select a league to continue", chooser_page.data)
            self.assertIn(b"Pick Admin League", chooser_page.data)

            response = self.client.post(
                "/select-league",
                data={
                    "_csrf_token": self._csrf_from("/select-league"),
                    "league_id": str(admin_league_id),
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Switched to Pick Admin League.", response.data)
            self.assertIn(b"My League", response.data)
            with self.client.session_transaction() as session_state:
                self.assertEqual(session_state["active_league_id"], admin_league_id)
                self.assertNotIn("pending_league_selection", session_state)
        finally:
            self._cleanup_league_data(player_league_id)
            self._cleanup_league_data(admin_league_id)
            self._delete_player(username)

    def test_single_league_player_login_lands_on_player_dashboard(self):
        username = f"singleplayer_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)

        response = self.client.post(
            "/login",
            data={
                "_csrf_token": self._csrf_from("/login"),
                "username": username,
                "password": "player123",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Player Dashboard", response.data)
        self.assertIn(b"Welcome back,", response.data)
        self.assertIn(b"Next Live Event", response.data)
        self._delete_player(username)

    def test_single_league_admin_login_lands_on_my_league(self):
        league_id = self._create_league(f"single-admin-{uuid.uuid4().hex[:8]}", "Single Admin League")
        username = f"singleleagueadmin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            response = self.client.post(
                "/login",
                data={
                    "_csrf_token": self._csrf_from("/login"),
                    "username": username,
                    "password": "player123",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"My League Workspace", response.data)
            self.assertIn(b"League Dashboard", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_switching_to_player_membership_blocks_admin_routes(self):
        player_league_id = self._create_league(f"switch-down-{uuid.uuid4().hex[:8]}", "Switch Down League")
        admin_league_id = self._create_league(f"switch-up-{uuid.uuid4().hex[:8]}", "Switch Up League")
        username = f"switchback_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="league_admin", league_id=admin_league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?, ?, 'player', 'active', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (user_id, player_league_id),
                )
                conn.commit()

            self._login_user(username, "player123")
            with self.client.session_transaction() as session_state:
                session_state["active_league_id"] = player_league_id

            admin_response = self.client.get("/admin/fighters")
            my_team_response = self.client.get("/my-team")

            self.assertEqual(admin_response.status_code, 403)
            self.assertEqual(my_team_response.status_code, 200)
            self.assertIn(b"League: Switch Down League", my_team_response.data)
        finally:
            self._cleanup_league_data(player_league_id)
            self._cleanup_league_data(admin_league_id)
            self._delete_player(username)

    def test_site_admin_homepage_uses_default_league_featured_content(self):
        league_id = self._create_league(f"home-site-admin-{uuid.uuid4().hex[:8]}", "Home Site Admin League")
        own_fighter_name = f"Site Admin Fighter {uuid.uuid4().hex[:6]}"
        own_team_name = f"Site Admin Team {uuid.uuid4().hex[:6]}"

        try:
            fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._create_team_with_roster(own_team_name, [fighter_id])
            scheduled_event_id = self._create_scheduled_event(f"Site Admin Event {uuid.uuid4().hex[:6]}", "2026-12-31", league_id=league_id)
            self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=5)
            self._login_admin()

            response = self.client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League spotlight: Invicta Fantasy League", response.data)
            self.assertNotIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertNotIn(own_team_name.encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_homepage_shows_empty_state_without_event_results(self):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute("SELECT * FROM event_results").fetchall()]
            conn.execute("DELETE FROM event_results")
            conn.commit()
        try:
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Members Only", response.data)
            self.assertIn(b"available after login", response.data)
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                for row in rows:
                    conn.execute(
                        """
                        INSERT INTO event_results(id,scheduled_event_id,league_id,event_date,event_name,fighter_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            row["id"],
                            row["scheduled_event_id"],
                            row["league_id"],
                            row["event_date"],
                            row["event_name"],
                            row["fighter_id"],
                            row["rounds_fought"],
                            row["special_awards"],
                            row["gold_medals"],
                            row["silver_medals"],
                            row["bronze_medals"],
                            row["kills"],
                            row["assists"],
                            row["deaths"],
                            row["sit_downs"],
                            row["yellow_cards"],
                            row["red_cards"],
                        ),
                    )
                conn.commit()

    def test_public_fighter_views_hide_raw_point_totals_while_admin_retains_scoring(self):
        username = f"fighter_view_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        fighters_response = self.client.get("/fighters")

        self.assertEqual(fighters_response.status_code, 200)
        self.assertNotIn(b"<span>Total</span><strong>", fighters_response.data)
        self.assertIn(b"Top Performer", fighters_response.data)
        self.assertIn(b"Glory", fighters_response.data)
        self.assertIn(b"Discipline", fighters_response.data)
        self.assertIn(b"Top 3 Fighters", fighters_response.data)
        self.assertIn(b"Current Leader", fighters_response.data)

        self._login_admin()
        admin_response = self.client.get("/admin/fighters")

        self.assertEqual(admin_response.status_code, 200)
        self.assertIn(b"Total Points", admin_response.data)
        self._delete_player(username)

    def test_fighter_lists_render_tier_legend_and_tier_classes(self):
        username = f"fighter_legend_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        response = self.client.get("/fighters")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Tier legend", response.data)
        self.assertIn(b"fighter-card-shell", response.data)
        self.assertIn(b"Tier 1", response.data)
        self.assertIn(b"tier-1", response.data)
        self._delete_player(username)

    def test_fighters_page_shows_top_three_section_empty_state_without_scores(self):
        username = f"fighter_empty_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            baseline_rows = [dict(row) for row in conn.execute("SELECT * FROM baseline_stats").fetchall()]
            event_rows = [dict(row) for row in conn.execute("SELECT * FROM event_results").fetchall()]
            conn.execute("UPDATE baseline_stats SET training=0, support=0")
            conn.execute("DELETE FROM attendance_scores")
            conn.execute("DELETE FROM event_results")
            conn.commit()
        try:
            response = self.client.get("/fighters")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"No fighter rankings yet.", response.data)
            self.assertIn(b"Top 3 Fighters", response.data)
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("DELETE FROM event_results")
                conn.execute("DELETE FROM attendance_scores")
                for row in baseline_rows:
                    conn.execute(
                        "INSERT INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?) ON CONFLICT(fighter_id) DO UPDATE SET training=excluded.training,support=excluded.support",
                        (row["fighter_id"], row["training"], row["support"]),
                    )
                for row in event_rows:
                    conn.execute(
                        """
                        INSERT INTO event_results(id,scheduled_event_id,league_id,event_date,event_name,fighter_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            row["id"],
                            row["scheduled_event_id"],
                            row["league_id"],
                            row["event_date"],
                            row["event_name"],
                            row["fighter_id"],
                            row["rounds_fought"],
                            row["special_awards"],
                            row["gold_medals"],
                            row["silver_medals"],
                            row["bronze_medals"],
                            row["kills"],
                            row["assists"],
                            row["deaths"],
                            row["sit_downs"],
                            row["yellow_cards"],
                            row["red_cards"],
                        ),
                    )
                conn.commit()
            self._delete_player(username)

    def test_public_teams_page_shows_empty_state_when_filters_match_nothing(self):
        username = f"teams_empty_{uuid.uuid4().hex[:8]}"
        self._create_player(username, manager_limit=1)
        self._login_user(username, "player123")
        response = self.client.get("/teams?q=__definitely_no_team_matches_this__")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No teams match your filters.", response.data)
        self.assertIn(b'name="status"', response.data)
        self.assertIn(b'name="sort"', response.data)
        self._delete_player(username)

    def test_admin_media_uses_independent_toolbar_query_prefixes(self):
        self._login_admin()
        response = self.client.get("/admin/media")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="banner_q"', response.data)
        self.assertIn(b'name="fighter_q"', response.data)
        self.assertIn(b'name="banner_sort"', response.data)
        self.assertIn(b'name="fighter_sort"', response.data)

    def test_admin_event_results_use_scheduled_event_and_prevent_duplicate_fighter_entries(self):
        self._login_admin()
        scheduled_event_id = self._create_scheduled_event("Leodis Cup", "2026-05-16")
        token = self._csrf_from("/admin/events")

        first_response = self.client.post(
            "/admin/events",
            data={
                "_csrf_token": token,
                "target_league_id": "1",
                "scheduled_event_id": str(scheduled_event_id),
                "fighter_id": "1",
                "gold_medals": "1",
                "silver_medals": "0",
                "bronze_medals": "0",
                "kills": "2",
                "deaths": "0",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertIn(b"Event result added.", first_response.data)
        self.assertIn(b"Leodis Cup", first_response.data)

        duplicate_response = self.client.post(
            "/admin/events",
            data={
                "_csrf_token": self._csrf_from("/admin/events"),
                "target_league_id": "1",
                "scheduled_event_id": str(scheduled_event_id),
                "fighter_id": "1",
                "gold_medals": "0",
                "silver_medals": "0",
                "bronze_medals": "0",
                "kills": "0",
                "deaths": "0",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(duplicate_response.status_code, 200)
        self.assertIn(b"already has results recorded", duplicate_response.data)

    def test_admin_can_add_manual_event_result_without_scheduled_event(self):
        self._login_admin()
        page_response = self.client.get("/admin/events")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn(b"Live Scoring Workspace", page_response.data)
        self.assertIn(b"Quick single-result fallback", page_response.data)
        self.assertNotIn(b"<h2>Add Result</h2>", page_response.data)
        self.assertNotIn(b"Record results and keep this league", page_response.data)

        response = self.client.post(
            "/admin/events",
            data={
                "_csrf_token": self._csrf_from("/admin/events"),
                "target_league_id": "1",
                "scheduled_event_id": "",
                "event_name": "Manual League Clash",
                "event_date": "2026-05-24",
                "fighter_id": "1",
                "gold_medals": "1",
                "kills": "2",
                "deaths": "0",
                "rounds_fought": "1",
                "special_awards": "0",
                "silver_medals": "0",
                "bronze_medals": "0",
                "assists": "0",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Event result added.", response.data)
        self.assertIn(b"Manual League Clash", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT scheduled_event_id, event_name, event_date FROM event_results WHERE event_name='Manual League Clash' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNotNone(row[0])
            self.assertEqual(row[1], "Manual League Clash")
            self.assertEqual(row[2], "2026-05-24")

    def test_event_result_edit_is_audited_with_before_after_values(self):
        self._login_admin()
        scheduled_event_id = self._create_scheduled_event("Durham Clash", "2026-05-18")
        self._create_event_result(scheduled_event_id, 1, gold_medals=1, kills=2, deaths=0)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            event_row = conn.execute("SELECT id FROM event_results WHERE scheduled_event_id=? AND fighter_id=1 ORDER BY id DESC LIMIT 1", (scheduled_event_id,)).fetchone()

        response = self.client.post(
            f"/admin/events/{event_row['id']}/edit",
            data={
                "_csrf_token": self._csrf_from(f"/admin/events/{event_row['id']}/edit"),
                "scheduled_event_id": str(scheduled_event_id),
                "fighter_id": "1",
                "gold_medals": "0",
                "silver_medals": "1",
                "bronze_medals": "0",
                "kills": "4",
                "deaths": "1",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Event result updated.", response.data)
        audit_response = self.client.get("/admin/audit?entity=event_result&action=update")
        self.assertEqual(audit_response.status_code, 200)
        self.assertIn(b"View change", audit_response.data)
        self.assertIn(b"Before", audit_response.data)
        self.assertIn(b"After", audit_response.data)

    def test_manual_event_result_can_be_edited_without_scheduled_event(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO event_results(
                    scheduled_event_id,league_id,event_date,event_name,fighter_id,
                    rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,
                    kills,assists,deaths,sit_downs,yellow_cards,red_cards
                ) VALUES(NULL,1,'2026-05-20','Manual Edit Event',1,1,0,0,0,0,1,0,0,0,0,0)
                """
            )
            event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.commit()

        response = self.client.post(
            f"/admin/events/{event_id}/edit",
            data={
                "_csrf_token": self._csrf_from(f"/admin/events/{event_id}/edit"),
                "scheduled_event_id": "",
                "event_name": "Manual Edit Event Updated",
                "event_date": "2026-05-21",
                "fighter_id": "1",
                "gold_medals": "0",
                "silver_medals": "1",
                "bronze_medals": "0",
                "kills": "4",
                "deaths": "1",
                "rounds_fought": "1",
                "special_awards": "0",
                "assists": "0",
                "sit_downs": "0",
                "yellow_cards": "0",
                "red_cards": "0",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Event result updated.", response.data)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT scheduled_event_id, event_name, event_date, silver_medals, kills FROM event_results WHERE id=?",
                (event_id,),
            ).fetchone()
            self.assertIsNotNone(row[0])
            self.assertEqual(row[1], "Manual Edit Event Updated")
            self.assertEqual(row[2], "2026-05-21")
            self.assertEqual(row[3], 1)
            self.assertEqual(row[4], 4)

    def test_league_scoped_audit_entries_record_their_league(self):
        league_id = self._create_league(f"audit-league-{uuid.uuid4().hex[:8]}", "Audit League")
        player_username = f"league_player_{uuid.uuid4().hex[:8]}"

        try:
            self._login_admin()
            response = self.client.post(
                f"/admin/players/new?league_id={league_id}",
                data={
                    "_csrf_token": self._csrf_from(f"/admin/players/new?league_id={league_id}"),
                    "display_name": "Audit Player",
                    "username": player_username,
                    "manager_limit": "1",
                    "password": "player123",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    """
                    SELECT league_id, entity_type, action
                    FROM audit_logs
                    WHERE message LIKE 'Created player Audit Player%'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], league_id)
            self.assertEqual(row[1], "user")
            self.assertEqual(row[2], "create")
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)

    def test_audit_page_can_filter_by_league_including_platform_entries(self):
        league_id = self._create_league(f"audit-filter-{uuid.uuid4().hex[:8]}", "Audit Filter League")
        player_username = f"audit_filter_player_{uuid.uuid4().hex[:8]}"
        original_training = None

        try:
            self._login_admin()
            self.client.post(
                f"/admin/players/new?league_id={league_id}",
                data={
                    "_csrf_token": self._csrf_from(f"/admin/players/new?league_id={league_id}"),
                    "display_name": "Audit Filter Player",
                    "username": player_username,
                    "manager_limit": "1",
                    "password": "player123",
                },
                follow_redirects=True,
            )
            with sqlite3.connect(app_module.DB_PATH) as conn:
                original_training = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
            self.client.post(
                "/admin/rules",
                data={
                    "_csrf_token": self._csrf_from("/admin/rules"),
                    **self._rule_form_fields(),
                    "rule_training": "12",
                    "minimum_team_size": "5",
                    "maximum_team_size": "8",
                    "team_budget": "500",
                    "tier_1_cost": "100",
                    "tier_2_cost": "75",
                    "tier_3_cost": "50",
                    "season_cost_round_unit": "5",
                    "season_min_cost": "25",
                    "season_max_cost": "250",
                    "season_pick_rate_target": "0.2",
                    "season_cost_sensitivity": "1.0",
                    "season_cost_adjustment_cap": "0.2",
                    "cost_mode": "Current Season",
                },
                follow_redirects=True,
            )

            league_response = self.client.get("/admin/audit?league=Audit+Filter+League")
            platform_response = self.client.get("/admin/audit?league=Platform")

            self.assertEqual(league_response.status_code, 200)
            self.assertIn(b"Audit Filter League", league_response.data)
            self.assertIn(b"Created player Audit Filter Player", league_response.data)
            self.assertNotIn(b"Updated platform-wide rules and settings.", league_response.data)

            self.assertEqual(platform_response.status_code, 200)
            self.assertIn(b"Platform", platform_response.data)
            self.assertIn(b"Updated platform-wide rules and settings.", platform_response.data)
            self.assertNotIn(b"Created player Audit Filter Player", platform_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    """
                    SELECT league_id
                    FROM audit_logs
                    WHERE message='Updated platform-wide rules and settings.'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertIsNone(row[0])
        finally:
            if original_training is not None:
                with sqlite3.connect(app_module.DB_PATH) as conn:
                    conn.execute("UPDATE rules SET points=? WHERE key='training'", (original_training,))
                    conn.commit()
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)

    def test_admin_players_can_filter_to_empty_state(self):
        self._login_admin()
        response = self.client.get("/admin/players?q=__no_player_should_match__")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No players match your filters.", response.data)
        self.assertIn(b'name="claim"', response.data)

    def test_site_admin_can_create_and_edit_leagues(self):
        self._login_admin()
        slug = f"club-{uuid.uuid4().hex[:8]}"
        initial_logo = "https://example.com/club-logo-initial.png"
        updated_logo = "https://example.com/club-logo-updated.png"
        create_response = self.client.post(
            "/admin/leagues/new",
            data={
                "_csrf_token": self._csrf_from("/admin/leagues/new"),
                "slug": slug,
                "name": "Club League",
                "club_name": "Club League",
                "status": "active",
                "description": "Initial setup",
                "contact_email": "club@example.com",
                "logo_url": initial_logo,
                "max_players": "12",
            },
            follow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn(b"League created.", create_response.data)
        self.assertIn(b"Club League", create_response.data)

        with sqlite3.connect(app_module.DB_PATH) as conn:
            league = conn.execute("SELECT id, max_players, max_teams, status, logo_url FROM leagues WHERE slug=?", (slug,)).fetchone()
            league_id = league[0]
            self.assertEqual(league[1], 12)
            self.assertEqual(league[2], 12)
            self.assertEqual(league[3], "active")
            self.assertEqual(league[4], initial_logo)

        try:
            edit_response = self.client.post(
                f"/admin/leagues/{league_id}",
                data={
                    "_csrf_token": self._csrf_from(f"/admin/leagues/{league_id}"),
                    "slug": slug,
                    "name": "Club League Updated",
                    "club_name": "Club League Updated",
                    "status": "inactive",
                    "description": "Updated setup",
                    "contact_email": "updated@example.com",
                    "logo_url": updated_logo,
                    "max_players": "15",
                },
                follow_redirects=True,
            )

            self.assertEqual(edit_response.status_code, 200)
            self.assertIn(b"League updated.", edit_response.data)
            self.assertIn(b"Club League Updated", edit_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                updated = conn.execute(
                    "SELECT name, status, max_players, max_teams, logo_url FROM leagues WHERE id=?",
                    (league_id,),
                ).fetchone()
                self.assertEqual(updated[0], "Club League Updated")
                self.assertEqual(updated[1], "inactive")
                self.assertEqual(updated[2], 15)
                self.assertEqual(updated[3], 15)
                self.assertEqual(updated[4], updated_logo)
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("DELETE FROM leagues WHERE id=?", (league_id,))
                conn.commit()

    def test_site_admin_league_edit_does_not_offer_direct_league_admin_creation(self):
        self._login_admin()
        league_id = self._create_league(f"owners-{uuid.uuid4().hex[:8]}", "Owners League")

        try:
            edit_response = self.client.get(f"/admin/leagues/{league_id}")
            self.assertEqual(edit_response.status_code, 200)
            self.assertIn(b"Promote players from the league players page", edit_response.data)
            self.assertNotIn(b"Create New League Admin", edit_response.data)
            self.assertNotIn(b"Maximum Teams", edit_response.data)
            self.assertNotIn(b"League Members", edit_response.data)
            self.assertIn(b"Team capacity", edit_response.data)

            post_response = self.client.post(
                f"/admin/leagues/{league_id}",
                data={
                    "_csrf_token": self._csrf_from(f"/admin/leagues/{league_id}"),
                    "action": "create_league_admin",
                    "display_name": "League Owner",
                    "username": f"owner_{uuid.uuid4().hex[:8]}",
                    "password": "owner123",
                },
            )

            self.assertEqual(post_response.status_code, 400)
            self.assertIn(b"Choose a valid league management action.", post_response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_site_admin_can_create_league_from_starter_template(self):
        self._login_admin()
        slug = f"template-{uuid.uuid4().hex[:8]}"

        create_response = self.client.post(
            "/admin/leagues/new",
            data={
                "_csrf_token": self._csrf_from("/admin/leagues/new"),
                "starter_template": "club_launch",
                "slug": slug,
                "name": "Template League",
                "club_name": "Template League",
                "contact_email": "template@example.com",
                "logo_url": "",
                "max_players": "",
                "description": "",
            },
            follow_redirects=True,
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertIn(b"League created.", create_response.data)

        with sqlite3.connect(app_module.DB_PATH) as conn:
            league = conn.execute(
                """
                SELECT id, status, max_players, max_teams, description
                FROM leagues
                WHERE slug=?
                """,
                (slug,),
            ).fetchone()
            league_id = league[0]
            self.assertEqual(league[1], "active")
            self.assertEqual(league[2], 24)
            self.assertEqual(league[3], 24)
            self.assertIn("Starter setup for a new club league", league[4])
            fighter_count = conn.execute("SELECT COUNT(*) FROM fighters WHERE league_id=?", (league_id,)).fetchone()[0]
            self.assertEqual(fighter_count, 0)

        self._cleanup_league_data(league_id)

    def test_site_admin_dashboard_shows_per_league_summary_metrics(self):
        self._login_admin()
        league_id = self._create_league(f"dashboard-{uuid.uuid4().hex[:8]}", "Dashboard League")
        username = f"dashboard_player_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Dashboard Fighter {uuid.uuid4().hex[:6]}"
        event_name = f"Dashboard Event {uuid.uuid4().hex[:6]}"

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("UPDATE leagues SET max_players=3, max_teams=2, status='active' WHERE id=?", (league_id,))
                conn.commit()
            self._create_user(username, role="player", league_id=league_id)
            fighter_id = self._create_fighter(fighter_name, league_id)
            self._create_team_with_roster(f"Dashboard Team {uuid.uuid4().hex[:6]}", [fighter_id])
            scheduled_event_id = self._create_scheduled_event(event_name, "2026-11-30", league_id=league_id)
            self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=3)

            response = self.client.get("/admin")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League Health", response.data)
            self.assertIn(b"Dashboard League", response.data)
            self.assertIn(b"Active", response.data)
            self.assertIn(b"Players 1 / 3", response.data)
            self.assertIn(b"Teams 1 / 2", response.data)
            self.assertIn(b"2026-11-30", response.data)
            self.assertNotIn(b"Fighters & Baseline Stats", response.data)
            self.assertNotIn(b"Fantasy Teams", response.data)
            self.assertNotIn(b"League Updates", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_site_admin_dashboard_highlights_attention_leagues(self):
        self._login_admin()
        attention_league_id = self._create_league(f"attention-{uuid.uuid4().hex[:8]}", "Attention League")

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    UPDATE leagues
                    SET status='inactive',
                        updated_at='2026-01-01T10:00:00'
                    WHERE id=?
                    """,
                    (attention_league_id,),
                )
                conn.commit()

            response = self.client.get("/admin")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Needs Attention", response.data)
            self.assertIn(b"Attention League", response.data)
            self.assertIn(b"No league admin assigned.", response.data)
            self.assertIn(b"Status is inactive.", response.data)
        finally:
            self._cleanup_league_data(attention_league_id)

    def test_site_admin_dashboard_simplifies_platform_overview(self):
        self._login_admin()
        pending_league_id = self._create_league(f"pending-{uuid.uuid4().hex[:8]}", "Pending League")
        inactive_league_id = self._create_league(f"inactive-{uuid.uuid4().hex[:8]}", "Inactive Queue League")

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    "UPDATE leagues SET status='pending', updated_at='2026-05-10T10:00:00' WHERE id=?",
                    (pending_league_id,),
                )
                conn.execute(
                    "UPDATE leagues SET status='inactive', updated_at='2026-05-01T10:00:00' WHERE id=?",
                    (inactive_league_id,),
                )
                conn.commit()

            response = self.client.get("/admin")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Platform Shortcuts", response.data)
            self.assertIn(b"Leagues", response.data)
            self.assertIn(b"Season Settings", response.data)
            self.assertIn(b"Rules & Settings", response.data)
            self.assertIn(b"Needs Attention", response.data)
            self.assertIn(b"Pending League", response.data)
            self.assertIn(b"Inactive Queue League", response.data)
            self.assertNotIn(b"Launch Queue", response.data)
            self.assertNotIn(b"Inactive Leagues", response.data)
        finally:
            self._cleanup_league_data(pending_league_id)
            self._cleanup_league_data(inactive_league_id)

    def test_site_admin_dashboard_hides_low_value_reporting_sections(self):
        self._login_admin()
        league_id = self._create_league(f"activity-{uuid.uuid4().hex[:8]}", "Activity League")

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO notifications(league_id,title,body,kind,created_at,expires_at,is_active)
                    VALUES(?,?,?,?,?,?,1)
                    """,
                    (
                        None,
                        "Activity Feed Test",
                        "Recent activity should surface here.",
                        "update",
                        "2026-12-31T23:59:59",
                        None,
                    ),
                )
                conn.commit()

            response = self.client.get("/admin")

            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b"Recent Platform Activity", response.data)
            self.assertNotIn(b"Operational Signals", response.data)
            self.assertNotIn(b"7-Day Trends", response.data)
            self.assertNotIn(b"Launch Queue", response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_admin_notifications_page_only_shows_platform_notices(self):
        self._login_admin()
        league_id = self._create_league(f"notice-filter-{uuid.uuid4().hex[:8]}", "Notice Filter League")

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO notifications(league_id,title,body,kind,created_at,expires_at,is_active)
                    VALUES(?,?,?,?,?,?,1)
                    """,
                    (
                        None,
                        "Platform Notice Test",
                        "Platform level notice body.",
                        "update",
                        "2026-12-31T23:59:59",
                        None,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO notifications(league_id,title,body,kind,created_at,expires_at,is_active)
                    VALUES(?,?,?,?,?,?,1)
                    """,
                    (
                        league_id,
                        "League Notice Test",
                        "League scoped notice body.",
                        "event",
                        "2026-12-31T23:59:59",
                        None,
                    ),
                )
                conn.commit()

            response = self.client.get("/admin/notifications")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Admin - Platform Notices", response.data)
            self.assertIn(b"Platform Notice Test", response.data)
            self.assertNotIn(b"League Notice Test", response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_site_admin_dashboard_supports_report_filters(self):
        self._login_admin()
        inactive_league_id = self._create_league(f"inactive-report-{uuid.uuid4().hex[:8]}", "Inactive Report League")
        active_league_id = self._create_league(f"active-report-{uuid.uuid4().hex[:8]}", "Active Report League")

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    "UPDATE leagues SET status='inactive', updated_at='2026-05-22T09:00:00' WHERE id=?",
                    (inactive_league_id,),
                )
                conn.execute(
                    """
                    INSERT INTO audit_logs(actor_user_id,league_id,entity_type,entity_id,action,message,rollback_type,created_at)
                    VALUES(NULL,?,?,?, ?, ?, NULL, ?)
                    """,
                    (
                        inactive_league_id,
                        "league",
                        inactive_league_id,
                        "update",
                        "Inactive league follow-up.",
                        "2026-05-22T11:00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO audit_logs(actor_user_id,league_id,entity_type,entity_id,action,message,rollback_type,created_at)
                    VALUES(NULL,?,?,?, ?, ?, NULL, ?)
                    """,
                    (
                        active_league_id,
                        "league",
                        active_league_id,
                        "update",
                        "Old active league follow-up.",
                        "2026-01-10T11:00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO seasons(name,status,locked,started_at,ended_at,completed_at)
                    VALUES(?,?,?,?,?,?)
                    """,
                    (
                        "Historic Reporting Season",
                        "completed",
                        1,
                        "2025-01-01T00:00:00",
                        "2025-12-31T23:59:59",
                        "2025-12-31T23:59:59",
                    ),
                )
                season_id = conn.execute("SELECT id FROM seasons WHERE name=?", ("Historic Reporting Season",)).fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO season_cost_changes(
                        season_id,fighter_id,fighter_name,old_cost,new_cost,pick_count,team_count,pick_rate,target_pick_rate,
                        sensitivity,raw_adjustment,applied_adjustment,clamp_limit,round_unit,min_cost,max_cost,created_at
                    )
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        season_id,
                        1,
                        "Sir Roland",
                        100,
                        110,
                        2,
                        4,
                        0.5,
                        0.25,
                        1.0,
                        0.1,
                        0.1,
                        0.15,
                        5,
                        25,
                        250,
                        "2026-05-22T12:00:00",
                    ),
                )
                conn.commit()

            response = self.client.get(f"/admin?status=inactive&window=7&season={season_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Inactive Report League", response.data)
            self.assertNotIn(b"Active Report League", response.data)
            self.assertIn(b"Historic Reporting Season", response.data)
            self.assertNotIn(b"Most Active Leagues In 7 Days", response.data)
            self.assertNotIn(b"Sir Roland", response.data)
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("DELETE FROM season_cost_changes WHERE fighter_name='Sir Roland'")
                conn.execute("DELETE FROM seasons WHERE name='Historic Reporting Season'")
                conn.commit()
            self._cleanup_league_data(inactive_league_id)
            self._cleanup_league_data(active_league_id)

    def test_site_admin_can_promote_existing_player_to_league_admin_from_players_page(self):
        self._login_admin()
        target_league_id = self._create_league(f"target-{uuid.uuid4().hex[:8]}", "Target League")
        username = f"promote_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="player", league_id=target_league_id)
            listing_response = self.client.get(f"/admin/players?league_id={target_league_id}")
            self.assertEqual(listing_response.status_code, 200)
            self.assertIn(b"Promote to League Admin", listing_response.data)
            self.assertNotIn(b"Promote Existing User", self.client.get(f"/admin/leagues/{target_league_id}").data)

            response = self.client.post(
                f"/admin/players/{user_id}/promote-admin",
                data={
                    "_csrf_token": self._csrf_from(f"/admin/players?league_id={target_league_id}"),
                    "league_id": str(target_league_id),
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League admin assigned.", response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    "SELECT role, league_id FROM users WHERE id=?",
                    (user_id,),
                ).fetchone()
                self.assertEqual(row[0], "league_admin")
                self.assertEqual(row[1], target_league_id)
                target_membership = conn.execute(
                    """
                    SELECT role
                    FROM league_memberships
                    WHERE user_id=? AND league_id=?
                    """,
                    (user_id, target_league_id),
                ).fetchone()
                self.assertIsNotNone(target_membership)
                self.assertEqual(target_membership[0], "league_admin")
        finally:
            self._cleanup_league_data(target_league_id)
            self._delete_player(username)

    def test_legacy_league_admin_routes_redirect_to_league_management(self):
        self._login_admin()
        league_id = self._create_league(f"legacy-admin-{uuid.uuid4().hex[:8]}", "Legacy Admin League")
        username = f"legacy_admin_{uuid.uuid4().hex[:8]}"

        try:
            user_id = self._create_user(username, role="league_admin", league_id=league_id)

            list_response = self.client.get("/admin/league-admins", follow_redirects=True)
            new_response = self.client.get("/admin/league-admins/new", follow_redirects=True)
            edit_response = self.client.get(f"/admin/league-admins/{user_id}", follow_redirects=True)

            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(new_response.status_code, 200)
            self.assertEqual(edit_response.status_code, 200)
            self.assertIn(b"League admins are now managed from the league workspace.", list_response.data)
            self.assertIn(b"Leagues", list_response.data)
            self.assertIn(b"Legacy Admin League", edit_response.data)
            self.assertIn(b"League Workspace", edit_response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_edit_uses_operations_links_instead_of_duplicate_member_tables(self):
        self._login_admin()
        league_id = self._create_league(f"review-{uuid.uuid4().hex[:8]}", "Review League")
        player_username = f"review_player_{uuid.uuid4().hex[:8]}"
        admin_username = f"review_admin_{uuid.uuid4().hex[:8]}"
        team_name = f"Review Team {uuid.uuid4().hex[:6]}"

        try:
            player_id = self._create_user(player_username, role="player", league_id=league_id)
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO fantasy_teams(team_name, manager, player_user_id, league_id) VALUES(?,?,?,?)",
                    (team_name, "Review Manager", player_id, league_id),
                )
                conn.commit()

            response = self.client.get(f"/admin/leagues/{league_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League Admins", response.data)
            self.assertIn(b"League Operations", response.data)
            self.assertIn(b"Promote players from the league players page", response.data)
            self.assertIn(b"Open Players", response.data)
            self.assertIn(b"Open Teams", response.data)
            self.assertNotIn(team_name.encode("utf-8"), response.data)
            self.assertNotIn(player_username.replace("_", " ").title().encode("utf-8"), response.data)
            self.assertIn(admin_username.replace("_", " ").title().encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)
            self._delete_player(admin_username)

    def test_site_admin_league_workspace_links_open_scoped_admin_pages(self):
        self._login_admin()
        league_id = self._create_league(f"workspace-scope-{uuid.uuid4().hex[:8]}", "Workspace Scope League")
        fighter_name = f"Workspace Scope Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_fighter(fighter_name, league_id)

            workspace_response = self.client.get(f"/admin/leagues/{league_id}")
            fighters_response = self.client.get(f"/admin/fighters?league_id={league_id}")
            events_response = self.client.get(f"/admin/events?league_id={league_id}")

            self.assertEqual(workspace_response.status_code, 200)
            self.assertIn(f"/admin/fighters?league_id={league_id}".encode("utf-8"), workspace_response.data)
            self.assertIn(f"/admin/events?league_id={league_id}".encode("utf-8"), workspace_response.data)

            self.assertEqual(fighters_response.status_code, 200)
            self.assertIn(b"Back to League Workspace", fighters_response.data)
            self.assertIn(b"Workspace Scope League", fighters_response.data)
            self.assertIn(fighter_name.encode("utf-8"), fighters_response.data)

            self.assertEqual(events_response.status_code, 200)
            self.assertIn(b"Back to League Workspace", events_response.data)
            self.assertIn(b"Workspace Scope League", events_response.data)
        finally:
            self._cleanup_league_data(league_id)

    def test_site_admin_can_access_admin_pages_for_any_league_records(self):
        self._login_admin()
        league_id = self._create_league(f"site-admin-access-{uuid.uuid4().hex[:8]}", "Site Admin Access League")
        username = f"site_admin_player_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Site Admin Fighter {uuid.uuid4().hex[:6]}"
        event_name = f"Site Admin Event {uuid.uuid4().hex[:6]}"

        try:
            player_id = self._create_user(username, role="player", league_id=league_id)
            fighter_id = self._create_fighter(fighter_name, league_id)
            team_id = self._create_team_with_roster(f"Site Admin Team {uuid.uuid4().hex[:6]}", [fighter_id])
            scheduled_event_id = self._create_scheduled_event(event_name, "2026-08-01", league_id=league_id)
            event_id = self._create_event_result(scheduled_event_id, fighter_id, league_id=league_id, gold_medals=1, kills=2)

            fighter_response = self.client.get(f"/admin/fighters/{fighter_id}")
            player_response = self.client.get(f"/admin/players/{player_id}")
            team_response = self.client.get(f"/admin/teams/{team_id}")
            event_response = self.client.get(f"/admin/events/{event_id}/edit")

            self.assertEqual(fighter_response.status_code, 200)
            self.assertEqual(player_response.status_code, 200)
            self.assertEqual(team_response.status_code, 200)
            self.assertEqual(event_response.status_code, 200)
            self.assertIn(fighter_name.encode("utf-8"), fighter_response.data)
            self.assertIn(username.replace("_", " ").title().encode("utf-8"), player_response.data)
            self.assertIn(event_name.encode("utf-8"), event_response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_can_update_their_league_logo_for_header_branding(self):
        league_id = self._create_league(f"league-logo-{uuid.uuid4().hex[:8]}", "League Logo League")
        username = f"league_logo_admin_{uuid.uuid4().hex[:8]}"
        logo_url = "https://example.com/league-logo-header.png"

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            self._login_user(username, "player123")

            response = self.client.post(
                "/admin/my-league",
                data={
                    "_csrf_token": self._csrf_from("/admin/my-league"),
                    "logo_url": logo_url,
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"League branding updated.", response.data)
            self.assertIn(logo_url.encode("utf-8"), response.data)

            fighters_response = self.client.get("/admin/fighters")
            self.assertEqual(fighters_response.status_code, 200)
            self.assertIn(logo_url.encode("utf-8"), fighters_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute("SELECT logo_url FROM leagues WHERE id=?", (league_id,)).fetchone()
                self.assertEqual(row[0], logo_url)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_can_regenerate_join_code_and_enable_self_participation(self):
        league_id = self._create_league(f"league-join-{uuid.uuid4().hex[:8]}", "League Join League")
        username = f"league_join_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="league_admin", league_id=league_id, manager_limit=0)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                original_code = conn.execute("SELECT join_code FROM leagues WHERE id=?", (league_id,)).fetchone()[0]

            self._login_user(username, "player123")
            regenerate_response = self.client.post(
                "/admin/my-league",
                data={
                    "_csrf_token": self._csrf_from("/admin/my-league"),
                    "action": "regenerate_join_code",
                },
                follow_redirects=True,
            )

            self.assertEqual(regenerate_response.status_code, 200)
            self.assertIn(b"League join code regenerated.", regenerate_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                updated_code = conn.execute("SELECT join_code FROM leagues WHERE id=?", (league_id,)).fetchone()[0]
            self.assertNotEqual(original_code, updated_code)

            participation_response = self.client.post(
                "/admin/my-league",
                data={
                    "_csrf_token": self._csrf_from("/admin/my-league"),
                    "action": "enable_self_participation",
                },
                follow_redirects=True,
            )

            self.assertEqual(participation_response.status_code, 200)
            self.assertIn(b"You can now participate as a player in this league.", participation_response.data)
            self.assertIn(b"My Teams", participation_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                membership = conn.execute(
                    """
                    SELECT league_memberships.manager_limit
                    FROM league_memberships
                    JOIN users u ON u.id = league_memberships.user_id
                    WHERE u.username=? AND league_memberships.league_id=?
                    """,
                    (username, league_id),
                ).fetchone()
            self.assertEqual(membership[0], 1)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_players_page_uses_join_code_flow_instead_of_direct_player_actions(self):
        league_id = self._create_league(f"league-players-{uuid.uuid4().hex[:8]}", "League Players League")
        admin_username = f"league_players_admin_{uuid.uuid4().hex[:8]}"
        player_username = f"league_players_member_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_user(player_username, role="player", league_id=league_id)
            self._login_user(admin_username, "player123")

            response = self.client.get("/admin/players")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Use your league join code", response.data)
            self.assertNotIn(b"Add Player", response.data)
            self.assertNotIn(b"Generate Invite", response.data)
            self.assertNotIn(b">Edit</a>", response.data)
            self.assertIn(b"Remove from League", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)
            self._delete_player(player_username)

    def test_league_admin_cannot_edit_player_account_details(self):
        league_id = self._create_league(f"league-player-edit-{uuid.uuid4().hex[:8]}", "League Player Edit")
        admin_username = f"league_player_edit_admin_{uuid.uuid4().hex[:8]}"
        player_username = f"league_player_edit_member_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            player_id = self._create_user(player_username, role="player", league_id=league_id)
            self._login_user(admin_username, "player123")

            get_response = self.client.get(f"/admin/players/{player_id}")
            post_response = self.client.post(
                f"/admin/players/{player_id}",
                data={
                    "_csrf_token": self._csrf_from("/admin/players"),
                    "display_name": "Blocked Edit",
                    "username": player_username,
                    "manager_limit": "1",
                    "password": "",
                },
            )

            self.assertEqual(get_response.status_code, 403)
            self.assertEqual(post_response.status_code, 403)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)
            self._delete_player(player_username)

    def test_league_admin_can_remove_player_from_league_without_deleting_account(self):
        league_id = self._create_league(f"league-remove-{uuid.uuid4().hex[:8]}", "League Remove")
        admin_username = f"league_remove_admin_{uuid.uuid4().hex[:8]}"
        player_username = f"league_remove_member_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            player_id = self._create_user(player_username, role="player", league_id=league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                f"/admin/players/{player_id}/remove",
                data={
                    "_csrf_token": self._csrf_from("/admin/players"),
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Player removed from league.", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                membership = conn.execute(
                    """
                    SELECT status
                    FROM league_memberships
                    WHERE user_id=? AND league_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (player_id, league_id),
                ).fetchone()
                user_row = conn.execute(
                    "SELECT id FROM users WHERE id=?",
                    (player_id,),
                ).fetchone()
            self.assertIsNotNone(user_row)
            self.assertEqual(membership[0], "inactive")
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)
            self._delete_player(player_username)

    def test_my_league_workspace_shows_quota_and_primary_admin_shortcuts(self):
        league_id = self._create_league(f"league-workspace-{uuid.uuid4().hex[:8]}", "League Workspace League")
        username = f"league_workspace_admin_{uuid.uuid4().hex[:8]}"
        player_username = f"league_workspace_player_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Workspace Fighter {uuid.uuid4().hex[:6]}"

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("UPDATE leagues SET max_players=9, max_teams=7 WHERE id=?", (league_id,))
                conn.commit()
            self._create_user(username, role="league_admin", league_id=league_id, manager_limit=0)
            self._create_user(player_username, role="player", league_id=league_id)
            self._create_fighter(fighter_name, league_id)
            self._create_team_in_league(f"Workspace Team {uuid.uuid4().hex[:6]}", league_id)
            self._create_scheduled_event(f"Workspace Event {uuid.uuid4().hex[:6]}", "2026-09-01", league_id=league_id)

            self._login_user(username, "player123")
            response = self.client.get("/admin/my-league")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"My League Workspace", response.data)
            self.assertIn(b"League Dashboard", response.data)
            self.assertIn(b"Open Fighters", response.data)
            self.assertIn(b"Open Events", response.data)
            self.assertIn(b"Open Players", response.data)
            self.assertIn(b"Open Teams", response.data)
            self.assertNotIn(b"Recent Signals", response.data)
            self.assertIn(b"Player usage", response.data)
            self.assertIn(b"Team usage", response.data)
            self.assertIn(b"1 / 9", response.data)
            self.assertIn(b"1 / 7", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)
            self._delete_player(player_username)

    def test_core_league_admin_pages_link_back_to_my_league(self):
        league_id = self._create_league(f"league-nav-{uuid.uuid4().hex[:8]}", "League Nav League")
        username = f"league_nav_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            self._login_user(username, "player123")

            for route in ("/admin/fighters", "/admin/events", "/admin/players", "/admin/teams"):
                with self.subTest(route=route):
                    response = self.client.get(route)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b"Back to My League", response.data)
                    self.assertIn(b"My League", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_cannot_access_direct_player_creation(self):
        league_id = self._create_league(f"quota-players-{uuid.uuid4().hex[:8]}", "Quota Players")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._login_user(admin_username, "player123")

            get_response = self.client.get(f"/admin/players/new?league_id={league_id}")
            post_response = self.client.post(
                f"/admin/players/new?league_id={league_id}",
                data={
                    "_csrf_token": self._csrf_from("/admin/players"),
                    "display_name": "Extra Player",
                    "username": f"overflow_{uuid.uuid4().hex[:8]}",
                    "manager_limit": "1",
                    "password": "player123",
                },
            )

            self.assertEqual(get_response.status_code, 403)
            self.assertEqual(post_response.status_code, 403)
        finally:
            self._cleanup_league_data(league_id)

    def test_league_admin_cannot_create_team_when_team_quota_is_reached(self):
        league_id = self._create_league(f"quota-teams-{uuid.uuid4().hex[:8]}", "Quota Teams")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("UPDATE leagues SET status='active', max_teams=1 WHERE id=?", (league_id,))
                conn.commit()
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_team_in_league(f"Quota Team {uuid.uuid4().hex[:6]}", league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/teams/new",
                data={
                    "_csrf_token": self._csrf_from("/admin/teams/new"),
                    "team_name": f"Overflow Team {uuid.uuid4().hex[:8]}",
                    "manager": f"Overflow Manager {uuid.uuid4().hex[:8]}",
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(b"team quota reached", response.data.lower())
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_cannot_access_site_admin_league_management(self):
        username = f"league_admin_{uuid.uuid4().hex[:8]}"
        self._create_user(username, role="league_admin")

        try:
            self._login_user(username, "player123")
            response = self.client.get("/admin/leagues")
            self.assertEqual(response.status_code, 403)
            admins_response = self.client.get("/admin/league-admins")
            self.assertEqual(admins_response.status_code, 403)
        finally:
            self._delete_player(username)

    def test_league_admin_header_uses_my_league_without_redundant_admin_link(self):
        league_id = self._create_league(f"league-admin-header-{uuid.uuid4().hex[:8]}", "League Admin Header")
        username = f"league_admin_header_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            self._login_user(username, "player123")

            response = self.client.get("/")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b'href="/admin/my-league">My League</a>', response.data)
            self.assertNotIn(b'href="/admin/fighters">Admin</a>', response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_inactive_league_user_cannot_log_in_to_protected_league_area(self):
        league_id = self._create_league(f"inactive-{uuid.uuid4().hex[:8]}", "Inactive League")
        username = f"inactive_player_{uuid.uuid4().hex[:8]}"
        self._create_user(username, role="player", league_id=league_id)

        try:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute("UPDATE leagues SET status='inactive' WHERE id=?", (league_id,))
                conn.commit()

            login_response = self.client.post(
                "/login",
                data={
                    "_csrf_token": self._csrf_from("/login"),
                    "username": username,
                    "password": "player123",
                },
                follow_redirects=False,
            )

            self.assertEqual(login_response.status_code, 403)
            self.assertIn(b"not currently active", login_response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_can_access_league_admin_routes_but_not_site_admin_routes(self):
        username = f"league_admin_{uuid.uuid4().hex[:8]}"
        league_id = self._create_league(f"league-admin-nav-{uuid.uuid4().hex[:8]}", "League Admin Nav")
        self._create_user(username, role="league_admin", league_id=league_id)

        try:
            self._login_user(username, "player123")

            fighters_response = self.client.get("/admin/fighters")
            dashboard_response = self.client.get("/admin")
            rules_response = self.client.get("/admin/rules")

            self.assertEqual(fighters_response.status_code, 200)
            self.assertIn(b"League: League Admin Nav", fighters_response.data)
            self.assertIn(b"League Admin Nav | Buhurt Fantasy League", fighters_response.data)
            self.assertEqual(dashboard_response.status_code, 403)
            self.assertEqual(rules_response.status_code, 403)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_site_admin_shell_shows_platform_admin_context(self):
        self._login_admin()

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Platform Admin", response.data)
        self.assertIn(b"Platform Admin | Buhurt Fantasy League", response.data)

    def test_league_admin_cannot_change_site_wide_rules_or_season_lifecycle(self):
        league_id = self._create_league(f"site-guard-{uuid.uuid4().hex[:8]}", "Site Guard League")
        username = f"league_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                original_training = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
                original_season = conn.execute("SELECT id, status, locked FROM seasons ORDER BY id DESC LIMIT 1").fetchone()

            self._login_user(username, "player123")
            csrf_token = self._csrf_from("/")

            rules_response = self.client.post(
                "/admin/rules",
                data={
                    "_csrf_token": csrf_token,
                    "rule_training": "99",
                    "minimum_team_size": "5",
                    "maximum_team_size": "8",
                    "team_budget": "500",
                    "tier_1_cost": "100",
                    "tier_2_cost": "75",
                    "tier_3_cost": "50",
                    "season_cost_round_unit": "5",
                    "season_min_cost": "25",
                    "season_max_cost": "250",
                    "season_pick_rate_target": "0.2",
                    "season_cost_sensitivity": "1.0",
                    "season_cost_adjustment_cap": "0.2",
                    "cost_mode": "Current Season",
                },
            )
            season_settings_response = self.client.post(
                "/admin/season/settings",
                data={
                    "_csrf_token": csrf_token,
                    "season_name": "Blocked Season Update",
                    "season_status": "active",
                },
            )
            reopen_response = self.client.post(
                "/admin/season/reopen",
                data={"_csrf_token": csrf_token},
            )

            self.assertEqual(rules_response.status_code, 403)
            self.assertEqual(season_settings_response.status_code, 403)
            self.assertEqual(reopen_response.status_code, 403)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                current_training = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
                current_season = conn.execute("SELECT id, status, locked FROM seasons ORDER BY id DESC LIMIT 1").fetchone()

            self.assertEqual(current_training, original_training)
            self.assertEqual(tuple(current_season), tuple(original_season))
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_site_admin_rules_remain_platform_wide_across_leagues(self):
        league_id = self._create_league(f"shared-rules-{uuid.uuid4().hex[:8]}", "Shared Rules League")
        username = f"league_admin_{uuid.uuid4().hex[:8]}"
        original_training = None

        try:
            self._create_user(username, role="league_admin", league_id=league_id)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                original_training = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
            self._login_admin()
            response = self.client.post(
                "/admin/rules",
                data={
                    "_csrf_token": self._csrf_from("/admin/rules"),
                    **self._rule_form_fields(),
                    "rule_training": "11",
                    "minimum_team_size": "5",
                    "maximum_team_size": "8",
                    "team_budget": "500",
                    "tier_1_cost": "100",
                    "tier_2_cost": "75",
                    "tier_3_cost": "50",
                    "season_cost_round_unit": "5",
                    "season_min_cost": "25",
                    "season_max_cost": "250",
                    "season_pick_rate_target": "0.2",
                    "season_cost_sensitivity": "1.0",
                    "season_cost_adjustment_cap": "0.2",
                    "cost_mode": "Current Season",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)

            self.client.post(
                "/logout",
                data={"_csrf_token": self._csrf_from("/")},
                follow_redirects=True,
            )
            self._login_user(username, "player123")
            rules_response = self.client.get("/rules")

            self.assertEqual(rules_response.status_code, 200)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                training_points = conn.execute("SELECT points FROM rules WHERE key='training'").fetchone()[0]
            self.assertEqual(training_points, 11)
        finally:
            if original_training is not None:
                with sqlite3.connect(app_module.DB_PATH) as conn:
                    conn.execute("UPDATE rules SET points=? WHERE key='training'", (original_training,))
                    conn.commit()
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_site_admin_can_update_trait_formula_settings(self):
        self._login_admin()
        with sqlite3.connect(app_module.DB_PATH) as conn:
            original_value = conn.execute("SELECT value FROM settings WHERE key='glory_gold_weight'").fetchone()[0]

        try:
            response = self.client.post(
                "/admin/rules",
                data={
                    "_csrf_token": self._csrf_from("/admin/rules"),
                    **self._rule_form_fields(),
                    "minimum_team_size": "5",
                    "maximum_team_size": "8",
                    "team_budget": "500",
                    "tier_1_cost": "100",
                    "tier_2_cost": "75",
                    "tier_3_cost": "50",
                    "season_cost_round_unit": "5",
                    "season_min_cost": "25",
                    "season_max_cost": "250",
                    "season_pick_rate_target": "0.2",
                    "season_cost_sensitivity": "1.0",
                    "season_cost_adjustment_cap": "0.2",
                    "cost_mode": "Current Season",
                    "glory_gold_weight": "9",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Six-Trait Formula Controls", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                saved_value = conn.execute("SELECT value FROM settings WHERE key='glory_gold_weight'").fetchone()[0]
            self.assertEqual(saved_value, "9.0")
        finally:
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO settings(key,value) VALUES('glory_gold_weight', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (original_value,),
                )
                conn.commit()

    def test_rules_page_owns_attendance_visibility_and_cost_formula_controls(self):
        self._login_admin()

        rules_response = self.client.get("/admin/rules")
        season_response = self.client.get("/admin/season/settings")

        self.assertEqual(rules_response.status_code, 200)
        self.assertEqual(season_response.status_code, 200)
        self.assertIn(b"Training Attendance Score Value", rules_response.data)
        self.assertIn(b"Support Attendance Score Value", rules_response.data)
        self.assertIn(b"Public Fighter Score Visibility", rules_response.data)
        self.assertIn(b"Season End Cost Formula", rules_response.data)
        self.assertNotIn(b"Training Attendance Score Value", season_response.data)
        self.assertNotIn(b"Support Attendance Score Value", season_response.data)
        self.assertNotIn(b"Public Fighter Score Visibility", season_response.data)
        self.assertNotIn(b"Target Pick Rate", season_response.data)

    def test_player_can_submit_fighter_edit_request_and_league_admin_can_approve_it(self):
        league_id = self._create_league(f"fighter-review-{uuid.uuid4().hex[:8]}", "Fighter Review League")
        player_username = f"fighter_player_{uuid.uuid4().hex[:8]}"
        admin_username = f"fighter_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(player_username, role="player", league_id=league_id)
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            fighter_id = self._create_fighter(f"Review Fighter {uuid.uuid4().hex[:6]}", league_id)

            self._login_user(player_username, "player123")
            response = self.client.post(
                f"/fighters/{fighter_id}/request-edit",
                data={
                    "_csrf_token": self._csrf_from(f"/fighters/{fighter_id}/request-edit"),
                    "nickname": "The Review",
                    "role_or_weapon": "Axe and Shield",
                    "known_for": "Huge pressure",
                    "why_buhurt": "For the love of the sport",
                    "joined_year": "2020",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Fighter update request submitted.", response.data)

            self.client.post("/logout", data={"_csrf_token": self._csrf_from("/")}, follow_redirects=True)
            self._login_user(admin_username, "player123")

            review_page = self.client.get("/admin/fighter-requests")
            self.assertEqual(review_page.status_code, 200)
            self.assertIn(b"The Review", review_page.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                request_id = conn.execute(
                    "SELECT id FROM fighter_change_requests WHERE fighter_id=? ORDER BY id DESC LIMIT 1",
                    (fighter_id,),
                ).fetchone()[0]

            approve_response = self.client.post(
                f"/admin/fighter-requests/{request_id}/approve",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighter-requests"),
                    "review_notes": "Looks good.",
                },
                follow_redirects=True,
            )

            self.assertEqual(approve_response.status_code, 200)
            self.assertIn(b"Fighter request approved.", approve_response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    "SELECT nickname, role_or_weapon, known_for, why_buhurt, joined_year FROM fighters WHERE id=?",
                    (fighter_id,),
                ).fetchone()
                request_row = conn.execute(
                    "SELECT status, review_notes FROM fighter_change_requests WHERE id=?",
                    (request_id,),
                ).fetchone()
            self.assertEqual(row[0], "The Review")
            self.assertEqual(row[1], "Axe and Shield")
            self.assertEqual(row[2], "Huge pressure")
            self.assertEqual(row[3], "For the love of the sport")
            self.assertEqual(row[4], 2020)
            self.assertEqual(request_row[0], "approved")
            self.assertEqual(request_row[1], "Looks good.")
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)
            self._delete_player(admin_username)

    def test_player_can_submit_new_fighter_request_and_league_admin_can_approve_it(self):
        league_id = self._create_league(f"new-fighter-review-{uuid.uuid4().hex[:8]}", "New Fighter Review League")
        player_username = f"newfighter_player_{uuid.uuid4().hex[:8]}"
        admin_username = f"newfighter_admin_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Requested Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(player_username, role="player", league_id=league_id)
            self._create_user(admin_username, role="league_admin", league_id=league_id)

            self._login_user(player_username, "player123")
            response = self.client.post(
                "/fighters/request-new",
                data={
                    "_csrf_token": self._csrf_from("/fighters/request-new"),
                    "name": fighter_name,
                    "nickname": "Fresh Blood",
                    "role_or_weapon": "Longsword",
                    "known_for": "Fast entries",
                    "why_buhurt": "To compete nationally",
                    "joined_year": "2023",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"New fighter request submitted.", response.data)

            self.client.post("/logout", data={"_csrf_token": self._csrf_from("/")}, follow_redirects=True)
            self._login_user(admin_username, "player123")

            with sqlite3.connect(app_module.DB_PATH) as conn:
                request_id = conn.execute(
                    "SELECT id FROM fighter_change_requests WHERE request_type='create' AND league_id=? ORDER BY id DESC LIMIT 1",
                    (league_id,),
                ).fetchone()[0]

            approve_response = self.client.post(
                f"/admin/fighter-requests/{request_id}/approve",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighter-requests"),
                    "review_notes": "Added to the league.",
                },
                follow_redirects=True,
            )

            self.assertEqual(approve_response.status_code, 200)
            self.assertIn(b"Fighter request approved.", approve_response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                fighter_row = conn.execute(
                    "SELECT league_id, name, nickname, role_or_weapon, known_for, why_buhurt, joined_year FROM fighters WHERE name=?",
                    (fighter_name,),
                ).fetchone()
                request_row = conn.execute(
                    "SELECT status FROM fighter_change_requests WHERE id=?",
                    (request_id,),
                ).fetchone()
            self.assertIsNotNone(fighter_row)
            self.assertEqual(fighter_row[0], league_id)
            self.assertEqual(fighter_row[1], fighter_name)
            self.assertEqual(fighter_row[2], "Fresh Blood")
            self.assertEqual(fighter_row[3], "Longsword")
            self.assertEqual(fighter_row[4], "Fast entries")
            self.assertEqual(fighter_row[5], "To compete nationally")
            self.assertEqual(fighter_row[6], 2023)
            self.assertEqual(request_row[0], "approved")
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)
            self._delete_player(admin_username)

    def test_player_notifications_page_only_shows_own_request_outcomes(self):
        league_id = self._create_league(f"notify-review-{uuid.uuid4().hex[:8]}", "Notify Review League")
        player_username = f"notify_player_{uuid.uuid4().hex[:8]}"
        other_username = f"notify_other_{uuid.uuid4().hex[:8]}"
        admin_username = f"notify_admin_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Notify Fighter {uuid.uuid4().hex[:6]}"
        requested_name = f"Request Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(player_username, role="player", league_id=league_id)
            self._create_user(other_username, role="player", league_id=league_id)
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            fighter_id = self._create_fighter(fighter_name, league_id)

            self._login_user(player_username, "player123")
            self.client.post(
                f"/fighters/{fighter_id}/request-edit",
                data={
                    "_csrf_token": self._csrf_from(f"/fighters/{fighter_id}/request-edit"),
                    "nickname": "Approved Nickname",
                },
                follow_redirects=True,
            )
            self.client.post(
                "/fighters/request-new",
                data={
                    "_csrf_token": self._csrf_from("/fighters/request-new"),
                    "name": requested_name,
                    "role_or_weapon": "Poleaxe",
                },
                follow_redirects=True,
            )
            self.client.post("/logout", data={"_csrf_token": self._csrf_from("/")}, follow_redirects=True)

            self._login_user(other_username, "player123")
            self.client.post(
                "/fighters/request-new",
                data={
                    "_csrf_token": self._csrf_from("/fighters/request-new"),
                    "name": f"Other Request {uuid.uuid4().hex[:6]}",
                },
                follow_redirects=True,
            )
            self.client.post("/logout", data={"_csrf_token": self._csrf_from("/")}, follow_redirects=True)

            self._login_user(admin_username, "player123")
            with sqlite3.connect(app_module.DB_PATH) as conn:
                edit_request_id = conn.execute(
                    "SELECT id FROM fighter_change_requests WHERE requester_user_id=(SELECT id FROM users WHERE username=?) AND request_type='edit' ORDER BY id DESC LIMIT 1",
                    (player_username,),
                ).fetchone()[0]
                create_request_id = conn.execute(
                    "SELECT id FROM fighter_change_requests WHERE requester_user_id=(SELECT id FROM users WHERE username=?) AND request_type='create' ORDER BY id DESC LIMIT 1",
                    (player_username,),
                ).fetchone()[0]

            self.client.post(
                f"/admin/fighter-requests/{edit_request_id}/approve",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighter-requests"),
                    "review_notes": "Looks good.",
                },
                follow_redirects=True,
            )
            self.client.post(
                f"/admin/fighter-requests/{create_request_id}/deny",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighter-requests"),
                    "review_notes": "Needs more detail.",
                },
                follow_redirects=True,
            )
            self.client.post("/logout", data={"_csrf_token": self._csrf_from("/")}, follow_redirects=True)

            self._login_user(player_username, "player123")
            response = self.client.get("/my-notifications")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"My Notifications", response.data)
            self.assertIn(b"Approved", response.data)
            self.assertIn(b"Denied", response.data)
            self.assertIn(b"Looks good.", response.data)
            self.assertIn(b"Needs more detail.", response.data)
            self.assertIn(requested_name.encode(), response.data)
            self.assertNotIn(b"Other Request", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(player_username)
            self._delete_player(other_username)
            self._delete_player(admin_username)

    def test_league_admin_only_sees_and_edits_fighters_in_their_own_league(self):
        league_id = self._create_league(f"league-{uuid.uuid4().hex[:8]}", "Second League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"League Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)
        own_fighter_id = None

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)

            self._login_user(admin_username, "player123")

            list_response = self.client.get("/admin/fighters")
            own_response = self.client.get(f"/admin/fighters/{own_fighter_id}")
            foreign_response = self.client.get(f"/admin/fighters/{default_fighter['id']}")

            self.assertEqual(list_response.status_code, 200)
            self.assertIn(own_fighter_name.encode("utf-8"), list_response.data)
            self.assertNotIn(default_fighter["name"].encode("utf-8"), list_response.data)
            self.assertEqual(own_response.status_code, 200)
            self.assertEqual(foreign_response.status_code, 404)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_can_bulk_import_fighters_into_their_own_league(self):
        league_id = self._create_league(f"fighter-import-{uuid.uuid4().hex[:8]}", "Fighter Import League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Import Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/fighters/import",
                data={
                    "_csrf_token": self._csrf_from("/admin/fighters"),
                    "csv_payload": f"name,tier,current_cost,training,support,nickname,role_or_weapon,known_for,joined_year\n{fighter_name},A,125,3,2,The Importer,Sword and Shield,Crowd control,2022\n",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"fighter import complete", response.data.lower())

            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    """
                    SELECT f.league_id, f.current_cost, f.nickname, f.role_or_weapon, f.known_for, f.joined_year, bs.training, bs.support
                    FROM fighters f
                    JOIN baseline_stats bs ON bs.fighter_id = f.id
                    WHERE f.name=?
                    """,
                    (fighter_name,),
                ).fetchone()
                self.assertEqual(row[0], league_id)
                self.assertEqual(row[1], 125)
                self.assertEqual(row[2], "The Importer")
                self.assertEqual(row[3], "Sword and Shield")
                self.assertEqual(row[4], "Crowd control")
                self.assertEqual(row[5], 2022)
                self.assertEqual(row[6], 3)
                self.assertEqual(row[7], 2)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_exports_only_their_league_fighters(self):
        league_id = self._create_league(f"fighter-export-{uuid.uuid4().hex[:8]}", "Fighter Export League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Export Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_fighter(own_fighter_name, league_id)
            self._login_user(admin_username, "player123")

            response = self.client.get("/admin/fighters/export.csv")

            self.assertEqual(response.status_code, 200)
            self.assertIn("text/csv", response.content_type)
            self.assertIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertNotIn(default_fighter["name"].encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_cannot_use_another_leagues_scheduled_event(self):
        league_id = self._create_league(f"events-guard-{uuid.uuid4().hex[:8]}", "Events Guard League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Guard Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            foreign_scheduled_event_id = self._create_scheduled_event(
                f"Foreign Event {uuid.uuid4().hex[:6]}",
                "2026-06-03",
                league_id=1,
            )
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/events",
                data={
                    "_csrf_token": self._csrf_from("/admin/events"),
                    "scheduled_event_id": str(foreign_scheduled_event_id),
                    "fighter_id": str(own_fighter_id),
                    "rounds_fought": "0",
                    "special_awards": "0",
                    "gold_medals": "0",
                    "silver_medals": "0",
                    "bronze_medals": "0",
                    "kills": "0",
                    "assists": "0",
                    "deaths": "0",
                    "sit_downs": "0",
                    "yellow_cards": "0",
                    "red_cards": "0",
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"choose a valid scheduled event from your league", response.data.lower())
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_can_bulk_import_and_export_event_results_in_their_own_league(self):
        league_id = self._create_league(f"event-import-{uuid.uuid4().hex[:8]}", "Event Import League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Event Import Fighter {uuid.uuid4().hex[:6]}"
        foreign_event_name = f"Foreign Event {uuid.uuid4().hex[:6]}"
        own_event_name = f"League Event {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_fighter(own_fighter_name, league_id)
            self._create_scheduled_event(own_event_name, "2026-06-12", league_id=league_id)
            self._create_scheduled_event(foreign_event_name, "2026-06-13", league_id=1)
            self._login_user(admin_username, "player123")

            import_response = self.client.post(
                "/admin/events/import",
                data={
                    "_csrf_token": self._csrf_from("/admin/events"),
                    "csv_payload": f"event_name,event_date,fighter_name,rounds_fought,gold_medals,kills\n{own_event_name},2026-06-12,{own_fighter_name},1,1,3\n",
                },
                follow_redirects=True,
            )

            self.assertEqual(import_response.status_code, 200)
            self.assertIn(b"event import complete", import_response.data.lower())

            export_response = self.client.get("/admin/events/export.csv")

            self.assertEqual(export_response.status_code, 200)
            self.assertIn("text/csv", export_response.content_type)
            self.assertIn(own_event_name.encode("utf-8"), export_response.data)
            self.assertIn(own_fighter_name.encode("utf-8"), export_response.data)
            self.assertNotIn(foreign_event_name.encode("utf-8"), export_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    """
                    SELECT league_id, rounds_fought, gold_medals, kills
                    FROM event_results
                    WHERE league_id=? AND event_name=? 
                    """,
                    (league_id, own_event_name),
                ).fetchone()
                self.assertEqual(row[0], league_id)
                self.assertEqual(row[1], 1)
                self.assertEqual(row[2], 1)
                self.assertEqual(row[3], 3)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_admin_events_page_syncs_calendar_events_into_active_league_schedule(self):
        league_id = self._create_league(f"calendar-sync-{uuid.uuid4().hex[:8]}", "Calendar Sync League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        original_calendar_loader = app_module.buhurt_uk_calendar_events

        try:
            def fake_calendar_loader(_conn):
                return [
                    {
                        "name": "York Spring Clash",
                        "date": "10 May 2026",
                        "location": "York",
                        "summary": "Past event inside the same calendar year.",
                        "url": "https://example.com/shared-calendar-feed",
                        "start_date": "2026-05-10",
                    },
                    {
                        "name": "York Autumn Clash",
                        "date": "4 October 2026",
                        "location": "York",
                        "summary": "Upcoming event inside the same calendar year.",
                        "url": "https://example.com/shared-calendar-feed",
                        "start_date": "2026-10-04",
                    },
                ]

            app_module.buhurt_uk_calendar_events = fake_calendar_loader
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._login_user(admin_username, "player123")

            response = self.client.get("/admin/events")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Live Scoring Workspace", response.data)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                synced_rows = conn.execute(
                    """
                    SELECT event_name, event_date
                    FROM event_banners
                    WHERE league_id=? AND source_kind='calendar'
                    ORDER BY event_date
                    """,
                    (league_id,),
                ).fetchall()
            self.assertEqual(
                synced_rows,
                [("York Spring Clash", "2026-05-10"), ("York Autumn Clash", "2026-10-04")],
            )
        finally:
            app_module.buhurt_uk_calendar_events = original_calendar_loader
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_can_score_grouped_event_results_in_workspace(self):
        league_id = self._create_league(f"workspace-{uuid.uuid4().hex[:8]}", "Workspace League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        fighter_one = f"Workspace Fighter {uuid.uuid4().hex[:6]}"
        fighter_two = f"Workspace Fighter {uuid.uuid4().hex[:6]}"
        fighter_three = f"Workspace Fighter {uuid.uuid4().hex[:6]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            fighter_one_id = self._create_fighter(fighter_one, league_id)
            fighter_two_id = self._create_fighter(fighter_two, league_id)
            fighter_three_id = self._create_fighter(fighter_three, league_id)
            self._login_user(admin_username, "player123")

            start_response = self.client.post(
                "/admin/events/workspace/start",
                data={
                    "_csrf_token": self._csrf_from("/admin/events"),
                    "event_name": "Leeds Open",
                    "event_date": "2026-07-12",
                },
                follow_redirects=False,
            )

            self.assertEqual(start_response.status_code, 302)
            workspace_path = start_response.headers["Location"]
            workspace_response = self.client.get(workspace_path)
            self.assertEqual(workspace_response.status_code, 200)
            self.assertIn(b"Leeds Open", workspace_response.data)
            self.assertIn(b"Create or Extend a Group", workspace_response.data)
            self.assertIn(b"data-confirm-complete", workspace_response.data)

            create_group_response = self.client.post(
                workspace_path,
                data={
                    "_csrf_token": self._csrf_from(workspace_path),
                    "workspace_action": "add_group_fighters",
                    "group_name": "Group A",
                    "fighter_ids": [str(fighter_one_id), str(fighter_two_id)],
                },
                follow_redirects=True,
            )

            with sqlite3.connect(app_module.DB_PATH) as conn:
                rows = conn.execute(
                    """
                    SELECT id, group_name, entry_status, fighter_id
                    FROM event_results
                    WHERE league_id=? AND event_name='Leeds Open'
                    ORDER BY fighter_id
                    """,
                    (league_id,),
                ).fetchall()

            score_group_response = self.client.post(
                workspace_path,
                data={
                    "_csrf_token": self._csrf_from(f"{workspace_path}?group_name=Group%20A"),
                    "workspace_action": "save_group_scores",
                    "group_name": "Group A",
                    f"result_{rows[0][0]}_rounds_fought": "2",
                    f"result_{rows[0][0]}_special_awards": "0",
                    f"result_{rows[0][0]}_gold_medals": "1",
                    f"result_{rows[0][0]}_silver_medals": "0",
                    f"result_{rows[0][0]}_bronze_medals": "0",
                    f"result_{rows[0][0]}_kills": "3",
                    f"result_{rows[0][0]}_assists": "0",
                    f"result_{rows[0][0]}_deaths": "0",
                    f"result_{rows[0][0]}_sit_downs": "1",
                    f"result_{rows[0][0]}_yellow_cards": "0",
                    f"result_{rows[0][0]}_red_cards": "0",
                    f"result_{rows[1][0]}_rounds_fought": "1",
                    f"result_{rows[1][0]}_special_awards": "1",
                    f"result_{rows[1][0]}_gold_medals": "0",
                    f"result_{rows[1][0]}_silver_medals": "1",
                    f"result_{rows[1][0]}_bronze_medals": "0",
                    f"result_{rows[1][0]}_kills": "1",
                    f"result_{rows[1][0]}_assists": "1",
                    f"result_{rows[1][0]}_deaths": "0",
                    f"result_{rows[1][0]}_sit_downs": "0",
                    f"result_{rows[1][0]}_yellow_cards": "0",
                    f"result_{rows[1][0]}_red_cards": "0",
                    "submit_action": "complete",
                },
                follow_redirects=True,
            )

            self.assertEqual(create_group_response.status_code, 200)
            self.assertEqual(score_group_response.status_code, 200)
            self.assertIn(b"Group A", score_group_response.data)
            self.assertIn(b"Add More Fighters", score_group_response.data)
            self.assertIn(b"Save Group Draft", score_group_response.data)
            self.assertIn(b"Mark Group Complete", score_group_response.data)
            self.assertIn(b"Rounds fought", score_group_response.data)
            self.assertIn(b"workspace-stat-button", score_group_response.data)
            self.assertIn(b"workspace-sticky-col", score_group_response.data)

            extend_group_response = self.client.post(
                workspace_path,
                data={
                    "_csrf_token": self._csrf_from(workspace_path),
                    "workspace_action": "add_group_fighters",
                    "group_name": "Group A",
                    "fighter_ids": [str(fighter_three_id)],
                },
                follow_redirects=True,
            )
            self.assertEqual(extend_group_response.status_code, 200)
            self.assertIn(b"<strong>3 / 3</strong>", extend_group_response.data)

            with sqlite3.connect(app_module.DB_PATH) as conn:
                updated_rows = conn.execute(
                    """
                    SELECT group_name, entry_status, rounds_fought, kills, assists, gold_medals, silver_medals, fighter_id
                    FROM event_results
                    WHERE league_id=? AND event_name='Leeds Open'
                    ORDER BY fighter_id
                    """,
                    (league_id,),
                ).fetchall()
            self.assertEqual(len(updated_rows), 3)
            self.assertEqual(updated_rows[0][0], "Group A")
            self.assertEqual(updated_rows[0][1], "complete")
            self.assertEqual(updated_rows[0][2], 2)
            self.assertEqual(updated_rows[0][3], 3)
            self.assertEqual(updated_rows[0][5], 1)
            self.assertEqual(updated_rows[1][0], "Group A")
            self.assertEqual(updated_rows[1][1], "complete")
            self.assertEqual(updated_rows[1][2], 1)
            self.assertEqual(updated_rows[1][3], 1)
            self.assertEqual(updated_rows[1][4], 1)
            self.assertEqual(updated_rows[1][6], 1)
            self.assertEqual(updated_rows[2][0], "Group A")
            self.assertEqual(updated_rows[2][1], "draft")
            self.assertEqual(updated_rows[2][7], fighter_three_id)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_event_workspace_shows_full_year_calendar_with_past_and_upcoming_events(self):
        league_id = self._create_league(f"workspace-calendar-{uuid.uuid4().hex[:8]}", "Workspace Calendar League")
        admin_username = f"workspace_calendar_admin_{uuid.uuid4().hex[:8]}"

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._login_user(admin_username, "player123")
            with sqlite3.connect(app_module.DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO event_banners(league_id,event_name,event_date,location,source_kind)
                    VALUES(?,?,?,?,?)
                    """,
                    (league_id, "York Spring Clash", "2026-03-10", "York", "calendar"),
                )
                conn.execute(
                    """
                    INSERT INTO event_banners(league_id,event_name,event_date,location,source_kind)
                    VALUES(?,?,?,?,?)
                    """,
                    (league_id, "Leeds Summer Grand", "2026-07-20", "Leeds", "calendar"),
                )
                conn.execute(
                    """
                    INSERT INTO event_banners(league_id,event_name,event_date,location,source_kind)
                    VALUES(?,?,?,?,?)
                    """,
                    (league_id, "Legacy Cup", "2025-11-01", "Leeds", "calendar"),
                )
                conn.commit()
                current_banner_id = conn.execute(
                    """
                    SELECT id
                    FROM event_banners
                    WHERE league_id=? AND event_name='Leeds Summer Grand'
                    """,
                    (league_id,),
                ).fetchone()[0]

            response = self.client.get(f"/admin/events/workspace/{current_banner_id}")

            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Buhurt Calendar 2026", response.data)
            self.assertIn(b"York Spring Clash", response.data)
            self.assertIn(b"Leeds Summer Grand", response.data)
            self.assertNotIn(b"Legacy Cup", response.data)
            self.assertIn(b"Past", response.data)
            self.assertIn(b"Upcoming", response.data)
            self.assertIn(b"Current Workspace", response.data)
            self.assertIn(b"Open Workspace", response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_public_fighter_views_use_their_league_context(self):
        league_id = self._create_league(f"fighter-public-{uuid.uuid4().hex[:8]}", "Public Fighter League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Public Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._login_user(admin_username, "player123")

            fighters_response = self.client.get("/fighters")
            own_detail_response = self.client.get(f"/fighters/{own_fighter_id}")
            foreign_detail_response = self.client.get(f"/fighters/{default_fighter['id']}")

            self.assertEqual(fighters_response.status_code, 200)
            self.assertIn(own_fighter_name.encode("utf-8"), fighters_response.data)
            self.assertNotIn(default_fighter["name"].encode("utf-8"), fighters_response.data)
            self.assertEqual(own_detail_response.status_code, 200)
            self.assertEqual(foreign_detail_response.status_code, 404)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_team_builder_only_lists_fighters_from_their_league(self):
        league_id = self._create_league(f"builder-{uuid.uuid4().hex[:8]}", "Builder League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Builder Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            self._create_fighter(own_fighter_name, league_id)
            self._login_user(admin_username, "player123")

            response = self.client.get("/admin/teams/new")

            self.assertEqual(response.status_code, 200)
            self.assertIn(own_fighter_name.encode("utf-8"), response.data)
            self.assertNotIn(default_fighter["name"].encode("utf-8"), response.data)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_league_admin_cannot_create_team_with_another_leagues_fighter_ids(self):
        league_id = self._create_league(f"teams-guard-{uuid.uuid4().hex[:8]}", "Teams Guard League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Guard Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._login_user(admin_username, "player123")

            response = self.client.post(
                "/admin/teams/new",
                data={
                    "_csrf_token": self._csrf_from("/admin/teams/new"),
                    "team_name": f"Guard Team {uuid.uuid4().hex[:6]}",
                    "manager": f"Guard Manager {uuid.uuid4().hex[:6]}",
                    "fighter_ids": [str(own_fighter_id), str(default_fighter["id"])],
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(b"must belong to the same league", response.data.lower())
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def test_player_cannot_create_team_with_another_leagues_fighter_ids(self):
        league_id = self._create_league(f"player-team-{uuid.uuid4().hex[:8]}", "Player Teams League")
        username = f"player_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Player Fighter {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)

        try:
            self._create_user(username, role="player", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            self._login_user(username, "player123")

            response = self.client.post(
                "/my-team/new",
                data={
                    "_csrf_token": self._csrf_from("/my-team/new"),
                    "team_name": f"Player Team {uuid.uuid4().hex[:6]}",
                    "manager": f"Player Manager {uuid.uuid4().hex[:6]}",
                    "fighter_ids": [str(own_fighter_id), str(default_fighter["id"])],
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn(b"must belong to the same league", response.data.lower())
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_site_admin_team_assignment_uses_selected_players_league(self):
        league_id = self._create_league(f"site-team-{uuid.uuid4().hex[:8]}", "Site Team League")
        username = f"player_{uuid.uuid4().hex[:8]}"
        fighter_name = f"Site Team Fighter {uuid.uuid4().hex[:6]}"

        try:
            player_id = self._create_user(username, role="player", league_id=league_id)
            fighter_id = self._create_fighter(fighter_name, league_id)
            team_name = f"Assigned Team {uuid.uuid4().hex[:6]}"
            self._login_admin()

            response = self.client.post(
                "/admin/teams/new",
                data={
                    "_csrf_token": self._csrf_from("/admin/teams/new"),
                    "team_name": team_name,
                    "manager": f"Assigned Manager {uuid.uuid4().hex[:6]}",
                    "player_user_id": str(player_id),
                    "fighter_ids": [str(fighter_id)],
                },
                follow_redirects=True,
            )

            self.assertEqual(response.status_code, 200)
            with sqlite3.connect(app_module.DB_PATH) as conn:
                row = conn.execute(
                    "SELECT league_id, player_user_id FROM fantasy_teams WHERE team_name=?",
                    (team_name,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], league_id)
            self.assertEqual(row[1], player_id)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(username)

    def test_league_admin_only_sees_and_edits_events_in_their_own_league(self):
        league_id = self._create_league(f"events-{uuid.uuid4().hex[:8]}", "Events League")
        admin_username = f"league_admin_{uuid.uuid4().hex[:8]}"
        own_fighter_name = f"Event Fighter {uuid.uuid4().hex[:6]}"
        own_event_name = f"Own Event {uuid.uuid4().hex[:6]}"
        default_fighter = self._first_fighter_in_league(1)
        default_event_name = f"Default Event {uuid.uuid4().hex[:6]}"
        own_event_id = None
        default_event_id = None

        try:
            self._create_user(admin_username, role="league_admin", league_id=league_id)
            own_fighter_id = self._create_fighter(own_fighter_name, league_id)
            own_scheduled_event_id = self._create_scheduled_event(own_event_name, "2026-06-01", league_id=league_id)
            default_scheduled_event_id = self._create_scheduled_event(default_event_name, "2026-06-02", league_id=1)
            own_event_id = self._create_event_result(own_scheduled_event_id, own_fighter_id, league_id=league_id)
            default_event_id = self._create_event_result(default_scheduled_event_id, default_fighter["id"], league_id=1)

            self._login_user(admin_username, "player123")

            list_response = self.client.get("/admin/events")
            own_response = self.client.get(f"/admin/events/{own_event_id}/edit")
            foreign_response = self.client.get(f"/admin/events/{default_event_id}/edit")

            self.assertEqual(list_response.status_code, 200)
            self.assertIn(own_event_name.encode("utf-8"), list_response.data)
            self.assertNotIn(default_fighter["name"].encode("utf-8"), list_response.data)
            self.assertEqual(own_response.status_code, 200)
            self.assertEqual(foreign_response.status_code, 404)
        finally:
            self._cleanup_league_data(league_id)
            self._delete_player(admin_username)

    def _login_admin(self):
        self._login_user("admin", "admin123")

    def _login_user(self, username, password):
        login_response = self.client.post(
            "/login",
            data={
                "_csrf_token": self._csrf_from("/login"),
                "username": username,
                "password": password,
            },
            follow_redirects=True,
        )
        self.assertEqual(login_response.status_code, 200)

    def _csrf_from(self, route):
        response = self.client.get(route)
        token_match = re.search(rb'name="_csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(token_match)
        return token_match.group(1).decode("utf-8")

    def _create_player(self, username, manager_limit=1):
        return self._create_user(username, role="player", manager_limit=manager_limit)

    def _create_user(self, username, role="player", manager_limit=1, league_id=None):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            if league_id is None:
                league = conn.execute("SELECT id FROM leagues ORDER BY id LIMIT 1").fetchone()
                league_id = league[0] if league else None
            cursor = conn.execute(
                """
                INSERT INTO users(username,display_name,password_hash,role,manager_limit,league_id)
                VALUES(?,?,?,?,?,?)
                """,
                (
                    username,
                    username.replace("_", " ").title(),
                    app_module.generate_password_hash("player123"),
                    role,
                    manager_limit,
                    league_id,
                ),
            )
            user_id = cursor.lastrowid
            if league_id is not None and role in {"player", "league_admin"}:
                conn.execute(
                    """
                    INSERT INTO league_memberships(user_id, league_id, role, status, manager_limit, joined_at, created_at, updated_at)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        user_id,
                        league_id,
                        role,
                        "active",
                        manager_limit,
                        "2026-01-01T00:00:00",
                        "2026-01-01T00:00:00",
                        "2026-01-01T00:00:00",
                    ),
                )
            return user_id

    def _create_league(self, slug, name):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            cursor = conn.execute(
                """
                INSERT INTO leagues(slug,name,club_name,status,join_code,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                """,
                (slug, name, name, "active", uuid.uuid4().hex[:8].upper(), "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
            )
            return cursor.lastrowid

    def _first_fighter_in_league(self, league_id):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            row = conn.execute(
                "SELECT id, name FROM fighters WHERE league_id=? ORDER BY id LIMIT 1",
                (league_id,),
            ).fetchone()
            return {"id": row[0], "name": row[1]}

    def _create_fighter(self, name, league_id):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            cursor = conn.execute(
                """
                INSERT INTO fighters(name,league_id,tier,current_cost)
                VALUES(?,?,?,?)
                """,
                (name, league_id, "A", 100),
            )
            fighter_id = cursor.lastrowid
            conn.execute(
                "INSERT INTO baseline_stats(fighter_id,training,support) VALUES(?,?,?)",
                (fighter_id, 0, 0),
            )
            conn.commit()
            return fighter_id

    def _rule_form_fields(self):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            rows = conn.execute("SELECT key, points FROM rules").fetchall()
        return {f"rule_{row[0]}": str(row[1]) for row in rows}

    def _create_scheduled_event(self, event_name, event_date, league_id=1):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM event_banners
                WHERE league_id=? AND event_name=? AND event_date=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (league_id, event_name, event_date),
            ).fetchone()
            if existing:
                return existing[0]
            cursor = conn.execute(
                """
                INSERT INTO event_banners(league_id,event_name,event_date,headline,subheading,image_url)
                VALUES(?,?,?,?,?,?)
                """,
                (league_id, event_name, event_date, "", "", ""),
            )
            return cursor.lastrowid

    def _create_event_result(self, scheduled_event_id, fighter_id, league_id=None, **stats):
        defaults = {
            "rounds_fought": 0,
            "special_awards": 0,
            "gold_medals": 0,
            "silver_medals": 0,
            "bronze_medals": 0,
            "kills": 0,
            "assists": 0,
            "deaths": 0,
            "sit_downs": 0,
            "yellow_cards": 0,
            "red_cards": 0,
        }
        defaults.update(stats)
        with sqlite3.connect(app_module.DB_PATH) as conn:
            event = conn.execute("SELECT event_name, event_date FROM event_banners WHERE id=?", (scheduled_event_id,)).fetchone()
            if league_id is None:
                fighter = conn.execute("SELECT league_id FROM fighters WHERE id=?", (fighter_id,)).fetchone()
                league_id = fighter[0] if fighter else None
            conn.execute(
                """
                INSERT INTO event_results(scheduled_event_id,league_id,event_date,event_name,fighter_id,rounds_fought,special_awards,gold_medals,silver_medals,bronze_medals,kills,assists,deaths,sit_downs,yellow_cards,red_cards)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    scheduled_event_id,
                    league_id,
                    event[1],
                    event[0],
                    fighter_id,
                    defaults["rounds_fought"],
                    defaults["special_awards"],
                    defaults["gold_medals"],
                    defaults["silver_medals"],
                    defaults["bronze_medals"],
                    defaults["kills"],
                    defaults["assists"],
                    defaults["deaths"],
                    defaults["sit_downs"],
                    defaults["yellow_cards"],
                    defaults["red_cards"],
                ),
            )
            conn.commit()
            return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def _create_team_with_roster(self, team_name, fighter_ids):
        manager_name = f"Manager {uuid.uuid4().hex[:8]}"
        with sqlite3.connect(app_module.DB_PATH) as conn:
            fighter = conn.execute("SELECT league_id FROM fighters WHERE id=?", (fighter_ids[0],)).fetchone()
            league_id = fighter[0] if fighter else None
            cursor = conn.execute(
                "INSERT INTO fantasy_teams(team_name,manager,league_id) VALUES(?,?,?)",
                (team_name, manager_name, league_id),
            )
            team_id = cursor.lastrowid
            for slot, fighter_id in enumerate(fighter_ids, start=1):
                conn.execute(
                    "INSERT INTO fantasy_team_fighters(team_id,fighter_id,slot) VALUES(?,?,?)",
                    (team_id, fighter_id, slot),
                )
            conn.commit()
            return team_id

    def _create_team_in_league(self, team_name, league_id):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            cursor = conn.execute(
                "INSERT INTO fantasy_teams(team_name,manager,league_id) VALUES(?,?,?)",
                (team_name, f"Manager {uuid.uuid4().hex[:8]}", league_id),
            )
            conn.commit()
            return cursor.lastrowid

    def _cleanup_league_data(self, league_id):
        if not league_id:
            return
        with sqlite3.connect(app_module.DB_PATH) as conn:
            fighter_ids = [row[0] for row in conn.execute("SELECT id FROM fighters WHERE league_id=?", (league_id,)).fetchall()]
            team_ids = [row[0] for row in conn.execute("SELECT id FROM fantasy_teams WHERE league_id=?", (league_id,)).fetchall()]
            user_ids = [row[0] for row in conn.execute("SELECT id FROM users WHERE league_id=?", (league_id,)).fetchall()]
            if team_ids:
                for team_id in team_ids:
                    conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (team_id,))
                    conn.execute("DELETE FROM team_share_links WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM fantasy_teams WHERE league_id=?", (league_id,))
            if fighter_ids:
                conn.executemany("DELETE FROM event_results WHERE fighter_id=?", [(fighter_id,) for fighter_id in fighter_ids])
                conn.executemany("DELETE FROM baseline_stats WHERE fighter_id=?", [(fighter_id,) for fighter_id in fighter_ids])
                conn.executemany("DELETE FROM fighters WHERE id=?", [(fighter_id,) for fighter_id in fighter_ids])
            if user_ids:
                conn.executemany("DELETE FROM claim_tokens WHERE user_id=?", [(user_id,) for user_id in user_ids])
                conn.executemany("DELETE FROM users WHERE id=?", [(user_id,) for user_id in user_ids])
            conn.execute("DELETE FROM event_results WHERE league_id=?", (league_id,))
            conn.execute("DELETE FROM leagues WHERE id=?", (league_id,))
            conn.commit()

    def _reopen_latest_season(self):
        self.client.post(
            "/admin/season/reopen",
            data={"_csrf_token": self._csrf_from("/admin/season/end")},
            follow_redirects=True,
        )

    def _delete_player(self, username):
        with sqlite3.connect(app_module.DB_PATH) as conn:
            user = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if user:
                teams = conn.execute("SELECT id, image_path FROM fantasy_teams WHERE player_user_id=?", (user[0],)).fetchall()
                for team_id, image_path in teams:
                    conn.execute("DELETE FROM fantasy_team_fighters WHERE team_id=?", (team_id,))
                    conn.execute("DELETE FROM team_share_links WHERE team_id=?", (team_id,))
                    if image_path:
                        image_file = app_module.BASE_DIR / "static" / image_path
                        if image_file.exists():
                            image_file.unlink()
                conn.execute("DELETE FROM fantasy_teams WHERE player_user_id=?", (user[0],))
                conn.execute("DELETE FROM claim_tokens WHERE user_id=?", (user[0],))
                conn.execute("DELETE FROM users WHERE id=?", (user[0],))


if __name__ == "__main__":
    unittest.main()
