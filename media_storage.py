"""Per-field storage selection for uploads that need different Cloudinary
resource-type handling than Django's DEFAULT_FILE_STORAGE default.

DEFAULT_FILE_STORAGE (see social/settings.py) is only switched to Cloudinary
when CLOUDINARY_URL is set, and defaults to MediaCloudinaryStorage's 'image'
resource type — correct as-is for pure-image fields (avatars, item photos),
which is why those fields don't need anything from this module.

Two kinds of fields need an explicit override instead:
  - post_media_storage: fields that hold EITHER an image OR a video
    (Post.post_media, Comment.media). Cloudinary needs resource_type='auto'
    for these, since forcing resource_type='image' rejects/mishandles video
    uploads.
  - attachment_storage: fields that are never images (Post.attachment,
    Comment.attachment — pdf/gpx/txt/csv) and must use Cloudinary's raw
    resource type to upload/download correctly.

Both fall back to Django's normal default_storage (local disk in dev/tests)
when CLOUDINARY_URL isn't set, so nothing changes locally. They're passed to
FileField(storage=...) as callables (supported since Django 4.2) so the
choice is re-evaluated lazily rather than baked in at import time — this is
also what lets tests flip CLOUDINARY_URL on/off via override_settings without
ever importing cloudinary_storage unless it's actually needed.
"""
from django.conf import settings
from django.core.files.storage import default_storage


def post_media_storage():
    if getattr(settings, 'CLOUDINARY_URL', ''):
        from cloudinary_storage.storage import MediaCloudinaryStorage
        return MediaCloudinaryStorage(resource_type='auto')
    return default_storage


def attachment_storage():
    if getattr(settings, 'CLOUDINARY_URL', ''):
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    return default_storage
