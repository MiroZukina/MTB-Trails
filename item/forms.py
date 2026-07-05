from django import forms
from .models import Item
from media_utils import validate_media_url, validate_image_file

INPUT_CLASSES = 'w-full py-4 px-6 rounded-xl border'


class _ItemMediaValidationMixin:
    def clean_image(self):
        f = self.cleaned_data.get('image')
        if f:
            validate_image_file(f)
        return f

    def clean_media_url(self):
        url = self.cleaned_data.get('media_url', '')
        validate_media_url(url, allow_youtube=False)
        return url


class NewItemForm(_ItemMediaValidationMixin, forms.ModelForm):
    media_url = forms.URLField(
        label="Image URL",
        required=False,
        widget=forms.URLInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'https://... image link'}),
    )

    class Meta:
        model = Item
        fields = ('category', 'name', 'description', 'price', 'image', 'media_url')
        widgets = {
            'category': forms.Select(attrs={
                'class': INPUT_CLASSES
            }),
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASSES
            }),
            'description': forms.Textarea(attrs={
                'class': INPUT_CLASSES
            }),
            'price': forms.TextInput(attrs={
                'class': INPUT_CLASSES
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': INPUT_CLASSES,
                'accept': 'image/*',
            }),
        }


class EditItemForm(_ItemMediaValidationMixin, forms.ModelForm):
    media_url = forms.URLField(
        label="Image URL",
        required=False,
        widget=forms.URLInput(attrs={'class': INPUT_CLASSES, 'placeholder': 'https://... image link'}),
    )

    class Meta:
        model = Item
        fields = ('name', 'description', 'price', 'image', 'media_url', 'is_sold')
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASSES
            }),
            'description': forms.Textarea(attrs={
                'class': INPUT_CLASSES
            }),
            'price': forms.TextInput(attrs={
                'class': INPUT_CLASSES
            }),
            'image': forms.ClearableFileInput(attrs={
                'class': INPUT_CLASSES,
                'accept': 'image/*',
            }),
        }