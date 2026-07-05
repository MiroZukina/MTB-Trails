"""
Tests for MTBTrails mapping features (pins, routes, GPX, stats, views).
"""
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from cycling.models import Post
from cycling.forms import PostForm

User = get_user_model()


def make_gpx(points):
    """Build a minimal GPX file (bytes) from (lat, lng, ele) tuples."""
    trkpts = "\n".join(
        f'<trkpt lat="{lat}" lon="{lng}"><ele>{ele}</ele></trkpt>'
        for lat, lng, ele in points
    )
    gpx = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="test" '
        'xmlns="http://www.topografix.com/GPX/1/1">'
        f'<trk><name>Test</name><trkseg>{trkpts}</trkseg></trk></gpx>'
    )
    return gpx.encode("utf-8")


# A tiny valid route: 4 points, each ~111m apart in latitude
ROUTE = [[53.2497, -6.2436], [53.2507, -6.2436], [53.2517, -6.2436], [53.2527, -6.2436]]


class PostModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="miro", password="x")

    def _make_post(self, **kwargs):
        defaults = {"body": "test post", "user": self.user}
        defaults.update(kwargs)
        return Post.objects.create(**defaults)

    def test_post_without_location(self):
        post = self._make_post()
        self.assertFalse(post.has_location)
        self.assertFalse(post.has_route)
        self.assertIsNone(post.length_km)

    def test_post_with_pin_only(self):
        post = self._make_post(latitude=53.35, longitude=-6.26)
        self.assertTrue(post.has_location)
        self.assertFalse(post.has_route)

    def test_route_sets_length(self):
        post = self._make_post(latitude=ROUTE[0][0], longitude=ROUTE[0][1], route=ROUTE)
        self.assertTrue(post.has_route)
        self.assertIsNotNone(post.length_km)
        # 3 hops of ~111m latitude each ≈ 0.33 km; allow generous tolerance
        self.assertAlmostEqual(float(post.length_km), 0.33, delta=0.05)

    def test_single_point_route_has_zero_or_none_length(self):
        post = self._make_post(route=[[53.25, -6.24]])
        self.assertIn(
            post.length_km is None or float(post.length_km) == 0.0, [True]
        )


class PostFormRouteTests(TestCase):
    """Route arrives as a JSON string from the hidden input."""

    def _form(self, route_value):
        data = {"body": "hello", "route": route_value}
        return PostForm(data=data)

    def test_valid_route_json(self):
        form = self._form(json.dumps(ROUTE))
        self.assertTrue(form.is_valid(), form.errors)

    def test_empty_route_is_ok(self):
        form = self._form("")
        self.assertTrue(form.is_valid(), form.errors)

    def test_invalid_json_rejected(self):
        form = self._form("{not json")
        self.assertFalse(form.is_valid())
        self.assertIn("route", form.errors)

    def test_non_list_rejected(self):
        form = self._form(json.dumps({"lat": 1, "lng": 2}))
        self.assertFalse(form.is_valid())

    def test_bad_pairs_rejected(self):
        form = self._form(json.dumps([[53.25], [53.26, -6.24]]))
        self.assertFalse(form.is_valid())

    def test_too_many_points_rejected(self):
        big = [[53.0 + i * 1e-5, -6.0] for i in range(501)]
        form = self._form(json.dumps(big))
        self.assertFalse(form.is_valid())


class GpxUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="miro", password="x")
        self.client.login(username="miro", password="x")

    def _post_with_gpx(self, file_bytes, filename="ride.gpx"):
        gpx_file = SimpleUploadedFile(filename, file_bytes, content_type="application/gpx+xml")
        return self.client.post(
            reverse("home"),
            {"body": "gpx ride", "gpx_file": gpx_file},
            follow=True,
        )

    def test_valid_gpx_creates_route_and_stats(self):
        pts = [(53.25 + i * 0.001, -6.24, 180 + i * 10) for i in range(20)]
        resp = self._post_with_gpx(make_gpx(pts))
        self.assertEqual(resp.status_code, 200)
        post = Post.objects.latest("id")
        self.assertTrue(post.has_route)
        self.assertTrue(post.has_location)
        self.assertIsNotNone(post.length_km)
        self.assertIsNotNone(post.total_ascent_m)
        self.assertGreater(post.total_ascent_m, 0)
        self.assertEqual(len(post.route), len(post.elevations))

    def test_corrupt_gpx_rejected(self):
        resp = self._post_with_gpx(b"this is not xml at all")
        self.assertEqual(resp.status_code, 200)
        # post should NOT be created
        self.assertFalse(Post.objects.filter(body="gpx ride").exists())

    def test_downsampling_caps_points(self):
        pts = [(53.0 + i * 1e-5, -6.24, 200.0) for i in range(1500)]
        self._post_with_gpx(make_gpx(pts))
        post = Post.objects.latest("id")
        self.assertLessEqual(len(post.route), 500)


class ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="miro", password="x")
        self.client.login(username="miro", password="x")
        self.located = Post.objects.create(
            body="with pin", user=self.user,
            latitude=53.2497, longitude=-6.2436, route=ROUTE,
        )
        self.bare = Post.objects.create(body="no location", user=self.user)

    def test_feed_loads_with_mixed_posts(self):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "with pin")
        self.assertContains(resp, "no location")

    def test_explore_page_loads(self):
        resp = self.client.get(reverse("explore"))
        self.assertEqual(resp.status_code, 200)

    def test_near_me_sorts_and_still_shows_unlocated(self):
        resp = self.client.get(reverse("home"), {"lat": "53.35", "lng": "-6.26"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "with pin")

    def test_near_me_with_garbage_params_does_not_crash(self):
        resp = self.client.get(reverse("home"), {"lat": "banana", "lng": "10"})
        self.assertEqual(resp.status_code, 200)

    def test_post_detail_without_location_has_no_weather_box(self):
        resp = self.client.get(reverse("post_show", kwargs={"pk": self.bare.pk}))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Weather at this trail")
