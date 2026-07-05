import math
from decimal import Decimal
from django.db import migrations


def _haversine_sum(pts):
    if not pts or len(pts) < 2:
        return None
    R = 6371.0
    total = 0.0
    for i in range(1, len(pts)):
        a, b = pts[i - 1], pts[i]
        dLat = math.radians(b[0] - a[0])
        dLon = math.radians(b[1] - a[1])
        s = (math.sin(dLat / 2) ** 2 +
             math.cos(math.radians(a[0])) * math.cos(math.radians(b[0])) *
             math.sin(dLon / 2) ** 2)
        total += R * 2 * math.atan2(math.sqrt(s), math.sqrt(1 - s))
    return Decimal(str(round(total, 2)))


def backfill(apps, schema_editor):
    Post = apps.get_model('cycling', 'Post')
    for post in Post.objects.filter(route__isnull=False):
        try:
            km = _haversine_sum(post.route)
            if km is not None:
                post.length_km = km
                post.save(update_fields=['length_km'])
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('cycling', '0014_add_length_km_to_post'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
