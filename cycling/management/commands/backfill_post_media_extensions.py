"""One-off backfill for Post.post_media / Comment.media rows saved before
PostMediaCloudinaryStorage started reattaching the file extension to the
stored name (see cloudinary_media_storage.py).

Why this is needed: Cloudinary's public_id for image/video assets never
includes the file extension, so any row saved by the old
MediaCloudinaryStorage(resource_type='auto') has a name with no extension
at all (e.g. "post_media/shot_ajd8x2"), and there is nothing left in the
database to tell whether that file is an image or a video. The new
.url() logic defaults to 'image' when it can't find a recognized
extension, so:
  - legacy IMAGE rows already resolve correctly, no action needed.
  - legacy VIDEO rows are still broken (URL now hits /image/upload/... for
    a resource Cloudinary only has under /video/upload/...) until their
    stored name is corrected.

This command finds legacy (extension-less) rows, asks Cloudinary's Search
API for the asset's real resource_type/format (Search doesn't require
knowing the resource_type up front, unlike most other Admin API calls), and
rewrites the stored name to include the right extension. It never touches
the Cloudinary asset itself -- only the DB column.

Defaults to a dry run. Pass --apply to actually write changes.
"""
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from cycling.models import Post, Comment
from media_utils import POST_VIDEO_EXTENSIONS

ALL_KNOWN_EXTENSIONS = POST_VIDEO_EXTENSIONS + ('.jpg', '.jpeg', '.png', '.webp', '.gif')


class Command(BaseCommand):
    help = (
        'Find Post.post_media / Comment.media rows saved without a file '
        'extension (from before the /auto/upload/ 404 fix) and backfill the '
        'extension from Cloudinary so video rows resolve correctly. '
        'Dry-run by default; pass --apply to write changes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Actually write the fix instead of just reporting it.')

    def handle(self, *args, **options):
        if not getattr(settings, 'CLOUDINARY_URL', ''):
            raise CommandError('CLOUDINARY_URL is not set in this environment -- run this where Cloudinary is configured (e.g. production).')

        import cloudinary.search

        apply_changes = options['apply']
        fields = [(Post, 'post_media'), (Comment, 'media')]

        already_fine = fixed = not_found = errors = 0

        for model, field_name in fields:
            qs = model.objects.exclude(**{field_name: ''}).exclude(**{f'{field_name}__isnull': True})
            for obj in qs:
                name = getattr(obj, field_name).name
                if not name:
                    continue
                if name.lower().endswith(ALL_KNOWN_EXTENSIONS):
                    already_fine += 1
                    continue

                self.stdout.write(f'{model.__name__}({obj.pk}).{field_name} = {name!r} -- no recognized extension, querying Cloudinary...')
                try:
                    result = cloudinary.search.Search().expression(f'public_id="{name}"').execute()
                except Exception as exc:
                    self.stderr.write(f'  ERROR querying Cloudinary: {exc}')
                    errors += 1
                    continue

                resources = result.get('resources', [])
                if not resources:
                    self.stderr.write('  NOT FOUND on Cloudinary -- needs manual review (broken upload? deleted asset?)')
                    not_found += 1
                    continue

                resource = resources[0]
                fmt = resource.get('format')
                resource_type = resource.get('resource_type')
                if not fmt:
                    self.stderr.write(f'  Cloudinary returned no format for resource_type={resource_type!r} -- needs manual review')
                    not_found += 1
                    continue

                new_name = f'{name}.{fmt}'
                self.stdout.write(f'  resource_type={resource_type}, format={fmt} -> {new_name!r}')
                if apply_changes:
                    model.objects.filter(pk=obj.pk).update(**{field_name: new_name})
                fixed += 1

        self.stdout.write(self.style.SUCCESS(
            f'Done. already_fine={already_fine} fixed={fixed} not_found={not_found} errors={errors} '
            f'({"applied" if apply_changes else "dry run, use --apply to write"})'
        ))
