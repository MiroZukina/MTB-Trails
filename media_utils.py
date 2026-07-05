"""Shared helpers for validating and rendering user-supplied media (uploaded
files or external URLs) across the cycling, item and profile forms."""
from urllib.parse import urlparse, parse_qs

from django.core.exceptions import ValidationError

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
POST_VIDEO_EXTENSIONS = ('.mp4', '.webm', '.mov')

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_POST_VIDEO_BYTES = 100 * 1024 * 1024

YOUTUBE_HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'www.youtu.be'}


def get_youtube_id(url):
    """Return the video id if `url` is a youtu.be or youtube.com/watch link, else None."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = parsed.netloc.lower()
    if host not in YOUTUBE_HOSTS:
        return None
    if host in ('youtu.be', 'www.youtu.be'):
        return parsed.path.lstrip('/').split('/')[0] or None
    if parsed.path == '/watch':
        return parse_qs(parsed.query).get('v', [None])[0]
    return None


def is_image_url(url):
    return urlparse(url).path.lower().endswith(IMAGE_EXTENSIONS)


def is_video_url(url):
    return urlparse(url).path.lower().endswith(POST_VIDEO_EXTENSIONS)


def validate_media_url(url, allow_youtube=False):
    """Raise ValidationError unless `url` is a plain http(s) link to an image/video
    (or, when allow_youtube, a YouTube link). Rejects javascript:/data: schemes."""
    if not url:
        return
    parsed = urlparse(url)
    if (parsed.scheme or '').lower() not in ('http', 'https'):
        raise ValidationError('URL must start with http:// or https://.')
    if allow_youtube and get_youtube_id(url):
        return
    if is_image_url(url) or is_video_url(url):
        return
    if allow_youtube:
        raise ValidationError('URL must link directly to an image/video file, or be a YouTube video.')
    raise ValidationError('URL must link directly to an image file.')


def validate_file(f, extensions, max_bytes, kind):
    name = getattr(f, 'name', '') or ''
    if not name.lower().endswith(extensions):
        raise ValidationError(f'Unsupported {kind} file type. Allowed: {", ".join(extensions)}.')
    size = getattr(f, 'size', None)
    if size is not None and size > max_bytes:
        raise ValidationError(f'{kind.capitalize()} file is too large. Max {max_bytes // (1024 * 1024)}MB.')


def validate_image_file(f, max_bytes=MAX_IMAGE_BYTES):
    validate_file(f, IMAGE_EXTENSIONS, max_bytes, 'image')


def validate_post_media_file(f):
    name = (getattr(f, 'name', '') or '').lower()
    if name.endswith(POST_VIDEO_EXTENSIONS):
        validate_file(f, POST_VIDEO_EXTENSIONS, MAX_POST_VIDEO_BYTES, 'video')
    else:
        validate_file(f, IMAGE_EXTENSIONS, MAX_IMAGE_BYTES, 'image')


def youtube_nocookie_embed_url(video_id):
    return f'https://www.youtube-nocookie.com/embed/{video_id}'


ATTACHMENT_EXTENSIONS = ('.pdf', '.gpx', '.txt', '.csv')
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

ATTACHMENT_ICONS = {'pdf': '\U0001F4C4', 'gpx': '\U0001F5FA'}
DEFAULT_ATTACHMENT_ICON = '\U0001F4C3'

# Content markers that mean "this isn't really a document", regardless of extension.
_DISALLOWED_CONTENT_MARKERS = (b'<!doctype html', b'<html', b'<script', b'<svg')


def validate_attachment_file(f):
    """Validate an uploaded post attachment by extension, size, and a light
    content sniff so a renamed .html/.svg/.exe can't slip through as a document."""
    name = getattr(f, 'name', '') or ''
    lower = name.lower()
    if not lower.endswith(ATTACHMENT_EXTENSIONS):
        raise ValidationError(
            f'Unsupported attachment type. Allowed: {", ".join(ATTACHMENT_EXTENSIONS)}.'
        )

    size = getattr(f, 'size', None)
    if size is not None and size > MAX_ATTACHMENT_BYTES:
        raise ValidationError(
            f'Attachment is too large. Max {MAX_ATTACHMENT_BYTES // (1024 * 1024)}MB.'
        )

    try:
        f.seek(0)
        head = f.read(4096)
        f.seek(0)
    except Exception:
        head = b''
    head_lower = head.lower()

    if head[:2] == b'MZ' or head[:4] == b'\x7fELF':
        raise ValidationError('Executable files are not allowed as attachments.')
    if any(marker in head_lower for marker in _DISALLOWED_CONTENT_MARKERS):
        raise ValidationError('Attachment content is not allowed (looks like HTML/script/SVG).')
    if lower.endswith('.pdf') and not head.startswith(b'%PDF-'):
        raise ValidationError('File does not look like a valid PDF.')
    if lower.endswith('.gpx') and b'<gpx' not in head_lower and b'<?xml' not in head_lower:
        raise ValidationError('File does not look like a valid GPX file.')


def attachment_icon_for(extension):
    return ATTACHMENT_ICONS.get(extension.lower().lstrip('.'), DEFAULT_ATTACHMENT_ICON)


def human_file_size(num_bytes):
    if num_bytes is None:
        return ''
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f'{size:.0f} {unit}' if unit == 'B' else f'{size:.1f} {unit}'
        size /= 1024
