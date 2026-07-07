from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from item.forms import NewItemForm
from item.models import Category


def _tiny_jpeg_bytes():
    buf = BytesIO()
    Image.new('RGB', (2, 2), (50, 100, 150)).save(buf, format='JPEG')
    return buf.getvalue()


def _tiny_heic_bytes():
    import pillow_heif
    buf = BytesIO()
    pillow_heif.from_pillow(Image.new('RGB', (4, 4), (30, 20, 10))).save(buf, quality=90)
    return buf.getvalue()


class MarketplaceImageValidationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='seller', password='sellerpass123')
        self.category = Category.objects.create(name='Bikes')

    def _base_data(self):
        return {'category': self.category.id, 'name': 'Trail bike', 'description': '', 'price': '100'}

    def test_real_jpeg_item_image_accepted(self):
        image = SimpleUploadedFile('bike.jpg', _tiny_jpeg_bytes(), content_type='image/jpeg')
        form = NewItemForm(data=self._base_data(), files={'image': image})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['image'].name, 'bike.jpg')

    def test_heic_item_image_accepted_and_converted_to_jpeg(self):
        heic = SimpleUploadedFile('bike.heic', _tiny_heic_bytes(), content_type='image/heic')
        form = NewItemForm(data=self._base_data(), files={'image': heic})
        self.assertTrue(form.is_valid(), form.errors)
        converted = form.cleaned_data['image']
        self.assertTrue(converted.name.endswith('.jpg'))
        converted.seek(0)
        self.assertEqual(Image.open(converted).format, 'JPEG')

    def test_corrupt_item_image_rejected_cleanly(self):
        junk = SimpleUploadedFile('bike.jpg', b'\xff\xd8\xffnotreallyajpeg', content_type='image/jpeg')
        form = NewItemForm(data=self._base_data(), files={'image': junk})
        self.assertFalse(form.is_valid())
        self.assertIn('image', form.errors)
