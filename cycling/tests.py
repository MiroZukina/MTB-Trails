import os
import unittest
from io import BytesIO
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, RequestFactory, override_settings
from django.contrib.auth.models import User
from cycling.models import Post, Comment, Profile, create_profile
from django.db.models.signals import post_save
from django.utils import timezone
from cycling.forms import PostForm, CommentForm
from cycling.views import home, profile_list
from django.urls import reverse
from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from PIL import Image
from media_utils import validate_attachment_file
from media_storage import post_media_storage, attachment_storage

# A syntactically valid but fake Cloudinary URL: enough for the SDK's own
# credential parsing to succeed so django-cloudinary-storage's storage
# classes can be constructed, without ever making a real network call
# (every test that activates this also mocks cloudinary.uploader.upload).
FAKE_CLOUDINARY_URL = 'cloudinary://123456789012345:abcdefghijklmnopqrstuvwxyz12@demo'


def _tiny_jpeg_bytes():
    """A real, tiny, Pillow-decodable JPEG — used wherever a test needs
    genuine image content rather than an extension-only stand-in."""
    buf = BytesIO()
    Image.new('RGB', (2, 2), (200, 50, 50)).save(buf, format='JPEG')
    return buf.getvalue()


def _tiny_heic_bytes():
    """A real, tiny, pillow-heif-encoded HEIC file."""
    import pillow_heif
    buf = BytesIO()
    pillow_heif.from_pillow(Image.new('RGB', (4, 4), (10, 20, 30))).save(buf, quality=90)
    return buf.getvalue()


class PostTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test-user', password='test-12345')
        self.post = Post.objects.create(user=self.user, body='Test Body', created_at=timezone.now())

    def test_number_of_likes(self):
        self.assertEqual(self.post.number_of_likes(), 0)  

    def test_str_representation(self):
        expected_str = f"{self.user}({self.post.created_at:%Y-%m-%d %H:%M}):Test Body..."
        self.assertEqual(str(self.post), expected_str)

if __name__ == '__main__':
    unittest.main()


class CommentTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test-user', password='test12344')
        self.post = Post.objects.create(user=self.user, body='Test Post Body', created_at=timezone.now())
        self.comment = Comment.objects.create(user=self.user, post=self.post, text='Test Comment Text', created_at=timezone.now())

    def test_comment_str_representation(self):
        expected_str = f"{self.user} on {self.post} at {self.comment.created_at:%Y-%m-%d %H:%M}"
        self.assertEqual(str(self.comment), expected_str)

    def test_comment_user_relationship(self):
        self.assertEqual(self.comment.user, self.user)

class ProfileModelTestCase(TestCase):
    def test_profile_creation(self):
        user = User.objects.create_user(username='test_user', password='test_password')
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.user, user)
        self.assertIsNotNone(profile.date_modified)
        self.assertEqual(profile.follows.count(), 1)  

    def test_create_profile_signal_handler(self):
        user = User.objects.create_user(username='test_user', password='test_password')
        self.assertTrue(Profile.objects.filter(user=user).exists())
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.user, user)
        self.assertEqual(profile.follows.count(), 1)  

if __name__ == '__main__':
    unittest.main()

class HomeViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='test-user', password='test1234')
        self.post = Post.objects.create(user=self.user, body='Test Post Body')
        self.comment = Comment.objects.create(user=self.user, post=self.post, text='Test Comment Text')

    def test_home_view_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')
        self.assertTrue('posts' in response.context)
        self.assertTrue('form' in response.context)
        self.assertTrue('comments' in response.context)
        self.assertTrue('comment_form' in response.context)

    def test_home_view_post(self):
        self.client.force_login(self.user)
        data = {'text': 'Test Comment Text', 'post_id': self.post.id}
        response = self.client.post(reverse('home'), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Comment.objects.count(), 2)

if __name__ == '__main__':
    unittest.main()

    class ProfileListViewTestCase(TestCase):
        def setUp(self):
            self.factory = RequestFactory()
            self.user = User.objects.create_user(username='test-user', password='test1234')
            if not hasattr(self.user, 'profile'):
                self.profile = Profile.objects.create(user=self.user)

        def test_authenticated_user_profile_list(self):
            request = self.factory.get(reverse('profile_list'))
            request.user = self.user

            # Required to test messages in the view
            setattr(request, 'session', 'session')
            messages = FallbackStorage(request)
            setattr(request, '_messages', messages)

            response = profile_list(request)
            self.assertEqual(response.status_code, 200)
            self.assertTrue('profiles' in response.context)
            if hasattr(self.user, 'profile'):
                self.assertNotIn(self.user.profile, response.context['profiles'])

        def test_unauthenticated_user_profile_list(self):
            request = self.factory.get(reverse('profile_list'))
            request.user = User.objects.create_user(username='unauthenticated_user', password='password123')

            response = profile_list(request)
            self.assertEqual(response.status_code, 302)  # Redirect expected for unauthenticated user

    if __name__ == '__main__':
        unittest.main()


class ProfileCommentViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.viewer = User.objects.create_user(username='viewer', password='viewerpass123')
        self.rider = User.objects.create_user(username='rider', password='riderpass123')
        self.client.force_login(self.viewer)

    def test_comment_on_profile_with_zero_posts_does_not_crash(self):
        response = self.client.post(
            reverse('profile', args=[self.rider.id]), {'text': 'Nice profile!'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 0)

    def test_comment_attaches_to_the_post_its_form_was_submitted_for(self):
        older_post = Post.objects.create(user=self.rider, body='Older post')
        newer_post = Post.objects.create(user=self.rider, body='Newer post')

        response = self.client.post(
            reverse('profile', args=[self.rider.id]),
            {'text': 'Comment on the older post', 'post_id': older_post.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        comment = Comment.objects.get(text='Comment on the older post')
        self.assertEqual(comment.post_id, older_post.id)
        self.assertNotEqual(comment.post_id, newer_post.id)

    def test_comment_with_unknown_post_id_does_not_crash(self):
        response = self.client.post(
            reverse('profile', args=[self.rider.id]),
            {'text': 'Nice profile!', 'post_id': 999999},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 0)


class HomeCommentViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='feed-viewer', password='viewerpass123')
        self.client.force_login(self.user)

    def test_comment_on_empty_feed_does_not_crash(self):
        response = self.client.post(reverse('home'), {'text': 'Nice feed!'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Comment.objects.count(), 0)

    def test_comment_attaches_to_the_post_its_form_was_submitted_for(self):
        older_post = Post.objects.create(user=self.user, body='Older post')
        newer_post = Post.objects.create(user=self.user, body='Newer post')

        response = self.client.post(
            reverse('home'),
            {'text': 'Comment on the older post', 'post_id': older_post.id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        comment = Comment.objects.get(text='Comment on the older post')
        self.assertEqual(comment.post_id, older_post.id)
        self.assertNotEqual(comment.post_id, newer_post.id)

    def test_comment_with_unknown_post_id_does_not_crash(self):
        Post.objects.create(user=self.user, body='Some post')
        response = self.client.post(
            reverse('home'),
            {'text': 'Nice feed!', 'post_id': 999999},
        )
        self.assertEqual(response.status_code, 200)


class PostAttachmentValidationTestCase(TestCase):
    def test_valid_pdf_accepted(self):
        pdf = SimpleUploadedFile('trailmap.pdf', b'%PDF-1.4\n%rest of a fake but valid-looking pdf', content_type='application/pdf')
        validate_attachment_file(pdf)  # should not raise

    def test_oversized_attachment_rejected(self):
        big = SimpleUploadedFile(
            'trailmap.pdf', b'%PDF-1.4\n' + b'A' * (10 * 1024 * 1024 + 1), content_type='application/pdf'
        )
        with self.assertRaises(ValidationError):
            validate_attachment_file(big)

    def test_double_extension_exe_rejected(self):
        fake = SimpleUploadedFile('map.pdf.exe', b'MZ\x90\x00fake-exe-body', content_type='application/octet-stream')
        with self.assertRaises(ValidationError):
            validate_attachment_file(fake)

    def test_html_renamed_to_pdf_rejected(self):
        html_as_pdf = SimpleUploadedFile(
            'notes.pdf', b'<!doctype html><html><body><script>alert(1)</script></body></html>', content_type='application/pdf'
        )
        with self.assertRaises(ValidationError):
            validate_attachment_file(html_as_pdf)


class PostAttachmentFormAndRenderTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='attach-user', password='attachpass123')
        self.client.force_login(self.user)

    def test_form_rejects_oversized_attachment(self):
        big = SimpleUploadedFile(
            'trailmap.pdf', b'%PDF-1.4\n' + b'A' * (10 * 1024 * 1024 + 1), content_type='application/pdf'
        )
        form = PostForm(data={'body': 'Ride with map'}, files={'attachment': big})
        self.assertFalse(form.is_valid())
        self.assertIn('attachment', form.errors)

    def test_attachment_renders_as_download_link_on_feed_and_detail(self):
        pdf = SimpleUploadedFile('trailmap.pdf', b'%PDF-1.4\nreal-enough-pdf-body', content_type='application/pdf')
        post = Post.objects.create(user=self.user, body='Ride with a map', attachment=pdf)

        home_response = self.client.get(reverse('home'))
        self.assertContains(home_response, 'attachment-chip')
        self.assertContains(home_response, 'trailmap')

        detail_response = self.client.get(reverse('post_show', args=[post.id]))
        self.assertContains(detail_response, 'attachment-chip')
        self.assertContains(detail_response, 'download')


class PostMediaValidationTestCase(TestCase):
    """Covers the iPhone HEIC upload bug: content-sniffing must never 500,
    HEIC/HEIF must be accepted, and existing jpg/png behavior must be
    unchanged."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='media-user', password='mediapass123')
        self.client.force_login(self.user)

    def test_real_jpeg_post_media_accepted_and_stored_unchanged(self):
        jpeg_bytes = _tiny_jpeg_bytes()
        image = SimpleUploadedFile('ride.jpg', jpeg_bytes, content_type='image/jpeg')
        form = PostForm(data={'body': 'Ride'}, files={'post_media': image})
        self.assertTrue(form.is_valid(), form.errors)
        stored = form.cleaned_data['post_media']
        self.assertEqual(stored.name, 'ride.jpg')
        self.assertEqual(stored.read(), jpeg_bytes)

    def test_heic_post_media_accepted_and_converted_to_jpeg(self):
        heic = SimpleUploadedFile('IMG_0001.heic', _tiny_heic_bytes(), content_type='image/heic')
        form = PostForm(data={'body': 'Ride'}, files={'post_media': heic})
        self.assertTrue(form.is_valid(), form.errors)
        converted = form.cleaned_data['post_media']
        self.assertTrue(converted.name.endswith('.jpg'))
        converted.seek(0)
        image = Image.open(converted)
        self.assertEqual(image.format, 'JPEG')

    def test_corrupt_image_post_media_rejected_as_form_error_not_500(self):
        junk = SimpleUploadedFile('ride.jpg', b'\xff\xd8\xffnotreallyajpeg', content_type='image/jpeg')
        form = PostForm(data={'body': 'Ride'}, files={'post_media': junk})
        self.assertFalse(form.is_valid())
        self.assertIn('post_media', form.errors)

    def test_corrupt_image_post_media_via_view_returns_200_not_500(self):
        junk = SimpleUploadedFile('ride.jpg', b'\xff\xd8\xffnotreallyajpeg', content_type='image/jpeg')
        response = self.client.post(reverse('home'), {'body': 'Ride', 'post_media': junk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Post.objects.filter(body='Ride').exists())

    def test_heic_post_media_via_view_creates_post_with_jpeg(self):
        heic = SimpleUploadedFile('IMG_0002.heic', _tiny_heic_bytes(), content_type='image/heic')
        response = self.client.post(reverse('home'), {'body': 'iPhone ride', 'post_media': heic})
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(body='iPhone ride')
        self.assertTrue(post.post_media.name.endswith('.jpg'))


class AvatarUploadValidationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='avatar-user', password='avatarpass123')
        self.client.force_login(self.user)

    def test_heic_profile_image_accepted_and_converted_to_jpeg(self):
        from cycling.forms import ProfilePicForm
        heic = SimpleUploadedFile('selfie.heic', _tiny_heic_bytes(), content_type='image/heic')
        form = ProfilePicForm(
            data={'profile_bio': 'Rider'},
            files={'profile_image': heic},
            instance=self.user.profile,
        )
        self.assertTrue(form.is_valid(), form.errors)
        converted = form.cleaned_data['profile_image']
        self.assertTrue(converted.name.endswith('.jpg'))

    def test_corrupt_profile_image_rejected_cleanly(self):
        from cycling.forms import ProfilePicForm
        junk = SimpleUploadedFile('selfie.jpg', b'\xff\xd8\xffnotreallyajpeg', content_type='image/jpeg')
        form = ProfilePicForm(
            data={'profile_bio': 'Rider'},
            files={'profile_image': junk},
            instance=self.user.profile,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('profile_image', form.errors)


class WeatherPageRemovalTestCase(TestCase):
    def test_old_weather_url_redirects_permanently_to_home(self):
        response = self.client.get(reverse('weather'))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, reverse('home'))

    def test_navbar_no_longer_links_to_weather_page(self):
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'Weather</a>')

    def test_navbar_has_single_marketplace_dropdown(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'navMarketplaceDropdown')
        self.assertContains(response, 'Browse items')


class NavbarMarketplaceDropdownTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='nav-user', password='navpass123')

    def test_anonymous_sees_only_browse_items(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Browse items')
        self.assertNotContains(response, 'Sell item')
        self.assertNotContains(response, 'My listings')
        self.assertNotContains(response, 'Inbox')

    def test_authenticated_sees_full_marketplace_dropdown(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Browse items')
        self.assertContains(response, 'Sell item')
        self.assertContains(response, 'My listings')
        self.assertContains(response, 'Inbox')

    def test_inbox_link_lives_inside_marketplace_dropdown_not_top_level(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('home'))
        self.assertContains(
            response,
            f'<a class="dropdown-item" href="{reverse("conversation:inbox")}">Inbox</a>',
            html=True,
        )
        self.assertNotContains(
            response,
            f'<a class="nav-link" href="{reverse("conversation:inbox")}">Inbox</a>',
            html=True,
        )


class CommentMediaValidationTestCase(TestCase):
    def test_text_only_comment_still_valid(self):
        form = CommentForm(data={'text': 'Nice ride!'})
        self.assertTrue(form.is_valid())

    def test_media_only_comment_is_valid(self):
        image = SimpleUploadedFile('photo.jpg', _tiny_jpeg_bytes(), content_type='image/jpeg')
        form = CommentForm(data={'text': ''}, files={'media': image})
        self.assertTrue(form.is_valid())

    def test_corrupt_image_comment_media_rejected_cleanly(self):
        junk = SimpleUploadedFile('photo.jpg', b'\xff\xd8\xffnotreallyajpeg', content_type='image/jpeg')
        form = CommentForm(data={'text': ''}, files={'media': junk})
        self.assertFalse(form.is_valid())
        self.assertIn('media', form.errors)

    def test_heic_comment_media_accepted_and_converted_to_jpeg(self):
        heic = SimpleUploadedFile('photo.heic', _tiny_heic_bytes(), content_type='image/heic')
        form = CommentForm(data={'text': ''}, files={'media': heic})
        self.assertTrue(form.is_valid(), form.errors)
        converted = form.cleaned_data['media']
        self.assertTrue(converted.name.endswith('.jpg'))
        converted.seek(0)
        image = Image.open(converted)
        self.assertEqual(image.format, 'JPEG')

    def test_completely_empty_comment_rejected(self):
        form = CommentForm(data={'text': ''})
        self.assertFalse(form.is_valid())

    def test_oversized_comment_media_rejected(self):
        big_video = SimpleUploadedFile(
            'clip.mp4', b'A' * (100 * 1024 * 1024 + 1), content_type='video/mp4'
        )
        form = CommentForm(data={'text': ''}, files={'media': big_video})
        self.assertFalse(form.is_valid())
        self.assertIn('media', form.errors)

    def test_disallowed_comment_attachment_type_rejected(self):
        exe = SimpleUploadedFile('malware.exe', b'MZ\x90\x00fake-exe-body', content_type='application/octet-stream')
        form = CommentForm(data={'text': ''}, files={'attachment': exe})
        self.assertFalse(form.is_valid())
        self.assertIn('attachment', form.errors)

    def test_dangerous_media_url_scheme_rejected(self):
        form = CommentForm(data={'text': '', 'media_url': 'javascript:alert(1)'})
        self.assertFalse(form.is_valid())
        self.assertIn('media_url', form.errors)


class CommentMediaEndpointTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='comment-media-user', password='commentpass123')
        self.post = Post.objects.create(user=self.user, body='Ride post')
        self.client.force_login(self.user)

    def test_home_accepts_multipart_media_only_comment(self):
        image = SimpleUploadedFile('feedshot.jpg', _tiny_jpeg_bytes(), content_type='image/jpeg')
        response = self.client.post(
            reverse('home'), {'text': '', 'post_id': self.post.id, 'media': image}
        )
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(post=self.post)
        self.assertTrue(comment.media)

    def test_profile_accepts_multipart_media_only_comment(self):
        image = SimpleUploadedFile('profileshot.jpg', _tiny_jpeg_bytes(), content_type='image/jpeg')
        response = self.client.post(
            reverse('profile', args=[self.user.id]),
            {'text': '', 'post_id': self.post.id, 'media': image},
        )
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(post=self.post)
        self.assertTrue(comment.media)

    def test_home_accepts_multipart_heic_comment_media_and_stores_jpeg(self):
        heic = SimpleUploadedFile('feedshot.heic', _tiny_heic_bytes(), content_type='image/heic')
        response = self.client.post(
            reverse('home'), {'text': '', 'post_id': self.post.id, 'media': heic}
        )
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(post=self.post)
        self.assertTrue(comment.media)
        self.assertTrue(comment.media.name.endswith('.jpg'))

    def test_post_show_accepts_multipart_media_only_comment(self):
        image = SimpleUploadedFile('detailshot.jpg', _tiny_jpeg_bytes(), content_type='image/jpeg')
        response = self.client.post(
            reverse('post_show', args=[self.post.id]), {'text': '', 'media': image}
        )
        self.assertEqual(response.status_code, 302)
        comment = Comment.objects.get(post=self.post)
        self.assertTrue(comment.media)

    def test_comment_attachment_renders_as_download_link_on_post_detail(self):
        pdf = SimpleUploadedFile('notes.pdf', b'%PDF-1.4\nreal-enough-pdf-body', content_type='application/pdf')
        Comment.objects.create(user=self.user, post=self.post, text='', attachment=pdf)
        response = self.client.get(reverse('post_show', args=[self.post.id]))
        self.assertContains(response, 'attachment-chip')
        self.assertContains(response, 'notes')
        self.assertContains(response, 'download')

    def test_comment_attachment_renders_on_home_feed(self):
        pdf = SimpleUploadedFile('trailnotes.pdf', b'%PDF-1.4\nreal-enough-pdf-body', content_type='application/pdf')
        Comment.objects.create(user=self.user, post=self.post, text='', attachment=pdf)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'attachment-chip')
        self.assertContains(response, 'trailnotes')


class HomeWeatherWidgetGeolocationFallbackTestCase(TestCase):
    """Regression coverage for the widget's client-side script actually being
    rendered: home.html's <script> blocks previously sat after
    {% endblock content %}, so Django silently dropped them and the "Detecting
    location…" state could never resolve. These assertions fail loudly if
    that happens again."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='geo-fallback-user', password='geopass123')
        self.client.force_login(self.user)

    def test_geolocation_script_is_actually_rendered_in_page(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'showLocalFallback')
        self.assertContains(response, 'getCurrentPosition')

    def test_fallback_covers_denied_timeout_and_missing_api(self):
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        self.assertIn('Location off — search a city instead.', content)
        self.assertIn('Location not available — search a city instead.', content)

    def test_geolocation_uses_a_timeout_so_it_cannot_hang_forever(self):
        response = self.client.get(reverse('home'))
        content = response.content.decode()
        self.assertIn('GEO_TIMEOUT_MS', content)
        self.assertIn('setTimeout', content)

    def test_city_search_markup_independent_of_geolocation_state(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'id="hw-city-input"')
        self.assertContains(response, 'id="hw-city-btn"')


class CloudinaryStorageSelectionTestCase(TestCase):
    """These never touch the network: without CLOUDINARY_URL they must
    resolve to Django's local default_storage, and cloudinary_storage.storage
    is never even imported. With a (fake) CLOUDINARY_URL, they must resolve
    to the right Cloudinary storage class/resource_type — checked by class,
    not by uploading anything.

    Note: cloudinary_storage's credential check reads os.environ directly
    (not Django settings), so activating it here needs both override_settings
    (for our own media_storage.py, which checks settings.CLOUDINARY_URL) and
    a real os.environ patch (for cloudinary_storage.app_settings)."""

    def test_local_storage_used_without_cloudinary_url(self):
        with override_settings(CLOUDINARY_URL=''):
            self.assertIs(post_media_storage(), default_storage)
            self.assertIs(attachment_storage(), default_storage)

    def test_post_media_storage_is_cloudinary_auto_resource_when_url_set(self):
        with override_settings(CLOUDINARY_URL=FAKE_CLOUDINARY_URL), \
                patch.dict(os.environ, {'CLOUDINARY_URL': FAKE_CLOUDINARY_URL}):
            storage = post_media_storage()
            self.assertEqual(storage.__class__.__name__, 'MediaCloudinaryStorage')
            self.assertEqual(storage.RESOURCE_TYPE, 'auto')

    def test_attachment_storage_is_cloudinary_raw_when_url_set(self):
        with override_settings(CLOUDINARY_URL=FAKE_CLOUDINARY_URL), \
                patch.dict(os.environ, {'CLOUDINARY_URL': FAKE_CLOUDINARY_URL}):
            storage = attachment_storage()
            self.assertEqual(storage.__class__.__name__, 'RawMediaCloudinaryStorage')
            self.assertEqual(storage.RESOURCE_TYPE, 'raw')


class CloudinaryUploadPipelineTestCase(TestCase):
    """Django resolves a FileField's callable `storage=` exactly once, at
    field-definition time (see django.db.models.fields.files.FileField.__init__)
    — not per save. That's correct for production (CLOUDINARY_URL is fixed
    for a process's whole lifetime), but it does mean override_settings in a
    test can't retroactively swap Post.post_media's already-cached storage
    instance. So instead of going through Post.save(), these tests exercise
    the exact same Cloudinary storage classes/instances the fields would use
    in production, directly — with cloudinary.uploader.upload mocked so
    nothing hits the network. This covers the real Storage._save() path."""

    def _cloudinary_env(self):
        return patch.dict(os.environ, {'CLOUDINARY_URL': FAKE_CLOUDINARY_URL})

    @patch('cloudinary.uploader.upload')
    def test_video_file_uploads_with_auto_resource_type(self, mock_upload):
        mock_upload.return_value = {'public_id': 'post_media/clip', 'resource_type': 'video'}
        with self._cloudinary_env():
            from cloudinary_storage.storage import MediaCloudinaryStorage
            storage = MediaCloudinaryStorage(resource_type='auto')
            video = ContentFile(b'\x00\x00\x00\x18ftypmp42fake-mp4-bytes', name='clip.mp4')
            storage.save('post_media/clip.mp4', video)

        self.assertTrue(mock_upload.called)
        _, kwargs = mock_upload.call_args
        self.assertEqual(kwargs.get('resource_type'), 'auto')

    @patch('cloudinary.uploader.upload')
    def test_image_file_still_uploads_with_auto_resource_type(self, mock_upload):
        # post_media_storage() always requests 'auto' for this field (never
        # a hardcoded 'image'), since one field holds both images and video.
        mock_upload.return_value = {'public_id': 'post_media/shot', 'resource_type': 'image'}
        with self._cloudinary_env():
            from cloudinary_storage.storage import MediaCloudinaryStorage
            storage = MediaCloudinaryStorage(resource_type='auto')
            image = ContentFile(b'\xff\xd8\xfffakejpegbytes', name='shot.jpg')
            storage.save('post_media/shot.jpg', image)

        self.assertTrue(mock_upload.called)
        _, kwargs = mock_upload.call_args
        self.assertEqual(kwargs.get('resource_type'), 'auto')

    @patch('cloudinary.uploader.upload')
    def test_pdf_attachment_uploads_via_raw_resource_type(self, mock_upload):
        mock_upload.return_value = {'public_id': 'attachments/notes', 'resource_type': 'raw'}
        with self._cloudinary_env():
            from cloudinary_storage.storage import RawMediaCloudinaryStorage
            storage = RawMediaCloudinaryStorage()
            pdf = ContentFile(b'%PDF-1.4\nreal-enough-pdf-body', name='notes.pdf')
            storage.save('attachments/notes.pdf', pdf)

        self.assertTrue(mock_upload.called)
        _, kwargs = mock_upload.call_args
        self.assertEqual(kwargs.get('resource_type'), 'raw')

    @patch('cloudinary.uploader.upload')
    def test_gpx_attachment_uploads_via_raw_resource_type(self, mock_upload):
        mock_upload.return_value = {'public_id': 'attachments/trail', 'resource_type': 'raw'}
        with self._cloudinary_env():
            from cloudinary_storage.storage import RawMediaCloudinaryStorage
            storage = RawMediaCloudinaryStorage()
            gpx = ContentFile(b'<?xml version="1.0"?><gpx></gpx>', name='trail.gpx')
            storage.save('attachments/trail.gpx', gpx)

        self.assertTrue(mock_upload.called)
        _, kwargs = mock_upload.call_args
        self.assertEqual(kwargs.get('resource_type'), 'raw')


class GpxAttachmentStorageIndependenceTestCase(TestCase):
    """The GPX-drawing bonus (_maybe_parse_attachment_as_gpx) reads the
    attachment straight out of request.FILES — the raw multipart upload —
    and parses it in-memory before post.save() ever calls the storage
    backend. So which storage backend is configured cannot affect whether
    the route gets drawn; combined with CloudinaryUploadPipelineTestCase
    above (which proves attachments upload correctly via Cloudinary's raw
    resource type), this shows the whole pipeline holds together."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='gpx-storage-user', password='gpxpass123')
        self.client.force_login(self.user)

    def test_attach_gpx_draws_route_before_any_storage_save(self):
        gpx_content = (
            b'<?xml version="1.0"?><gpx><trk><trkseg>'
            b'<trkpt lat="53.35" lon="-6.26"></trkpt>'
            b'<trkpt lat="53.36" lon="-6.27"></trkpt>'
            b'</trkseg></trk></gpx>'
        )
        gpx_file = SimpleUploadedFile('trail.gpx', gpx_content, content_type='application/gpx+xml')

        response = self.client.post(reverse('home'), {'body': 'Ride with attached GPX', 'attachment': gpx_file})

        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(body='Ride with attached GPX')
        self.assertIsNotNone(post.route)
        self.assertTrue(post.has_location)
        self.assertTrue(post.attachment)