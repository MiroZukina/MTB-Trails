"""Cloudinary storage for FileFields that hold either an image or a video
(Post.post_media, Comment.media) — see media_storage.post_media_storage().

Only imported when CLOUDINARY_URL is actually set: importing
cloudinary_storage.storage runs cloudinary_storage's credential check at
import time (cloudinary_storage/app_settings.py), which raises
ImproperlyConfigured if no Cloudinary credentials are configured. That's
fine here because this module is only reached from inside
media_storage.post_media_storage()'s `if CLOUDINARY_URL:` branch, never at
Django startup.

Two Cloudinary quirks this class has to bridge:

1. Upload vs delivery resource type. Cloudinary's upload API accepts
   resource_type='auto' and detects image vs video per file, which is why
   plain MediaCloudinaryStorage(resource_type='auto') is used for this
   field today. But there is no 'auto' resource type for *delivery* URLs —
   they must be built with the file's real type ('image' or 'video'), so
   the current storage's .url() produces /auto/upload/... and 404s.

2. The real type can't be read back off Cloudinary's own public_id.
   Per Cloudinary's upload API docs, the public_id for image/video assets
   never includes the file extension (only 'raw' assets keep it), so the
   extension normally used to tell image from video is gone by the time
   Django calls .url()/.delete() with the stored FieldFile name. To keep
   that information around, _save() reattaches the original extension to
   whatever public_id Cloudinary returns, and delete() strips it back off
   before talking to the Cloudinary SDK directly (Cloudinary's destroy API
   rejects a public_id that includes an extension). Reads don't need that
   treatment: Cloudinary's own URL parsing already treats a trailing
   extension as a format suffix rather than part of the public_id, so
   MediaCloudinaryStorage's inherited _get_url() works unchanged once
   _get_resource_type() can see the extension.
"""
import os

import cloudinary.uploader
from cloudinary_storage.storage import MediaCloudinaryStorage
from django.core.files.uploadedfile import UploadedFile

from media_utils import POST_VIDEO_EXTENSIONS


class PostMediaCloudinaryStorage(MediaCloudinaryStorage):
    RESOURCE_TYPE = 'auto'

    def _get_resource_type(self, name):
        ext = os.path.splitext(name)[1].lower()
        return 'video' if ext in POST_VIDEO_EXTENSIONS else 'image'

    def _upload(self, name, content):
        # Always request 'auto' here (not self._get_resource_type(name),
        # which is for delivery/delete), so both images and videos upload
        # correctly through this one field.
        options = {'use_filename': True, 'resource_type': 'auto', 'tags': self.TAG}
        folder = os.path.dirname(name)
        if folder:
            options['folder'] = folder
        return cloudinary.uploader.upload(content, **options)

    def _save(self, name, content):
        ext = os.path.splitext(name)[1]
        name = self._normalise_name(name)
        name = self._prepend_prefix(name)
        content = UploadedFile(content, name)
        response = self._upload(name, content)
        public_id = response['public_id']
        if ext and not public_id.lower().endswith(ext.lower()):
            public_id += ext
        return public_id

    def delete(self, name):
        public_id = os.path.splitext(name)[0]
        response = cloudinary.uploader.destroy(
            public_id, invalidate=True, resource_type=self._get_resource_type(name))
        return response['result'] == 'ok'
