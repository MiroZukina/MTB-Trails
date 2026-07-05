import json as _json
import math as _math
import os as _os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.utils.text import get_valid_filename
from media_utils import (
    get_youtube_id, is_image_url, is_video_url, youtube_nocookie_embed_url,
    attachment_icon_for, human_file_size,
)
from media_storage import post_media_storage, attachment_storage
# Create your models here.


def _attachment_upload_path(instance, filename):
    return f'attachments/{get_valid_filename(filename)}'


def _comment_attachment_upload_path(instance, filename):
    return f'comment_attachments/{get_valid_filename(filename)}'


DIFFICULTY_CHOICES = [
    ('green', 'Easy'),
    ('blue', 'Moderate'),
    ('red', 'Difficult'),
    ('black', 'Severe'),
]

DIFFICULTY_COLORS = {
    'green': '#66bb6a',
    'blue':  '#4285f4',
    'red':   '#e03030',
    'black': '#757575',
}


class Post(models.Model):
    user = models.ForeignKey(
        User, related_name="post",
        on_delete=models.DO_NOTHING
    )
    body = models.CharField(max_length=200)
    post_media = models.FileField(upload_to='post_media/', null=True, blank=True, storage=post_media_storage)
    media_url = models.URLField(blank=True, default="")
    attachment = models.FileField(upload_to=_attachment_upload_path, null=True, blank=True, storage=attachment_storage)
    created_at = models.DateTimeField(auto_now_add=True)
    likes = models.ManyToManyField(User, related_name="post_like", blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_name = models.CharField(max_length=200, blank=True, default="")
    route = models.JSONField(null=True, blank=True)
    length_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, null=True, blank=True)
    elevations = models.JSONField(null=True, blank=True)
    total_ascent_m = models.IntegerField(null=True, blank=True)

    def _compute_length_km(self):
        pts = self.route
        if not pts or len(pts) < 2:
            return None
        R = 6371.0
        total = 0.0
        for i in range(1, len(pts)):
            a, b = pts[i - 1], pts[i]
            dLat = _math.radians(b[0] - a[0])
            dLon = _math.radians(b[1] - a[1])
            s = (_math.sin(dLat / 2) ** 2 +
                 _math.cos(_math.radians(a[0])) * _math.cos(_math.radians(b[0])) *
                 _math.sin(dLon / 2) ** 2)
            total += R * 2 * _math.atan2(_math.sqrt(s), _math.sqrt(1 - s))
        from decimal import Decimal
        return Decimal(str(round(total, 2)))

    def save(self, *args, **kwargs):
        self.length_km = self._compute_length_km()
        super().save(*args, **kwargs)

    def number_of_likes(self):
        return self.likes.count()

    @property
    def is_video(self):
        if self.post_media:
            return self.post_media.name.lower().endswith(('.mp4', '.mov'))
        return False

    @property
    def youtube_embed_url(self):
        video_id = get_youtube_id(self.media_url)
        return youtube_nocookie_embed_url(video_id) if video_id else None

    @property
    def media_url_is_video(self):
        return bool(self.media_url) and is_video_url(self.media_url)

    @property
    def media_url_is_image(self):
        return bool(self.media_url) and is_image_url(self.media_url)

    @property
    def attachment_filename(self):
        return _os.path.basename(self.attachment.name) if self.attachment else ''

    @property
    def attachment_extension(self):
        return _os.path.splitext(self.attachment_filename)[1].lstrip('.').lower()

    @property
    def attachment_icon(self):
        return attachment_icon_for(self.attachment_extension)

    @property
    def attachment_size_display(self):
        if not self.attachment:
            return ''
        try:
            return human_file_size(self.attachment.size)
        except (OSError, ValueError):
            return ''

    @property
    def has_elevations(self):
        return bool(self.elevations)

    @property
    def difficulty_label(self):
        return dict(DIFFICULTY_CHOICES).get(self.difficulty, '')

    @property
    def difficulty_color(self):
        return DIFFICULTY_COLORS.get(self.difficulty, '#e03030')

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def has_route(self):
        return bool(self.route)

    @property
    def route_json(self):
        return _json.dumps(self.route) if self.route else 'null'

    def __str__(self):
        return (
            f"{self.user}"
            f"({self.created_at:%Y-%m-%d %H:%M}):"
            f"{self.body}..."
        )

class Comment(models.Model):
    user = models.ForeignKey(
        User, related_name="comments",
        on_delete=models.CASCADE
    )
    post = models.ForeignKey(
        Post, related_name="comments",
        on_delete=models.CASCADE
    )
    text = models.TextField(blank=True, default="")
    media = models.FileField(upload_to='comment_media/', null=True, blank=True, storage=post_media_storage)
    media_url = models.URLField(blank=True, default="")
    attachment = models.FileField(upload_to=_comment_attachment_upload_path, null=True, blank=True, storage=attachment_storage)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} on {self.post} at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_video(self):
        if self.media:
            return self.media.name.lower().endswith(('.mp4', '.mov', '.webm'))
        return False

    @property
    def youtube_embed_url(self):
        video_id = get_youtube_id(self.media_url)
        return youtube_nocookie_embed_url(video_id) if video_id else None

    @property
    def media_url_is_video(self):
        return bool(self.media_url) and is_video_url(self.media_url)

    @property
    def media_url_is_image(self):
        return bool(self.media_url) and is_image_url(self.media_url)

    @property
    def attachment_filename(self):
        return _os.path.basename(self.attachment.name) if self.attachment else ''

    @property
    def attachment_extension(self):
        return _os.path.splitext(self.attachment_filename)[1].lstrip('.').lower()

    @property
    def attachment_icon(self):
        return attachment_icon_for(self.attachment_extension)

    @property
    def attachment_size_display(self):
        if not self.attachment:
            return ''
        try:
            return human_file_size(self.attachment.size)
        except (OSError, ValueError):
            return ''

class Profile(models.Model):
 user = models.OneToOneField(User, on_delete=models.CASCADE)
 follows = models.ManyToManyField("self", 
        related_name="followed_by",
        symmetrical=False,
        blank=True)
 date_modified = models.DateTimeField(auto_now=True)
 profile_image = models.ImageField(upload_to='profile_images/', null=True, blank=True)
 media_url = models.URLField(blank=True, default="")
 profile_bio = models.CharField(null=True, blank=True, max_length=500)
 facebook_link = models.CharField(null=True, blank=True, max_length=100)
 homepage_link = models.CharField(null=True, blank=True, max_length=100)
 instagram_link = models.CharField(null=True, blank=True, max_length=100)
 linkedin_link = models.CharField(null=True, blank=True, max_length=100)
 
 def __str__(self):
        return self.user.username
 
 
 
 #Create Profile When New User Sings up
def create_profile(sender, instance, created, **kwargs):
    if created:
        user_profile = Profile(user=instance)
        user_profile.save()
        user_profile.follows.set([instance.profile.id])
        user_profile.save()

post_save.connect(create_profile, sender=User)