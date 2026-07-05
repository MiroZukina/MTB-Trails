import json
from django import forms
from django.forms import ModelForm, TextInput, fields, widgets
from .models import Post, Profile, Comment
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from media_utils import (
    validate_media_url, validate_image_file, validate_post_media_file, validate_attachment_file,
)


class PostForm(forms.ModelForm):
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Enter Your Post",
                "class": "form-control",
                "rows": 3,
            }
        ),
        label="",
    )
    post_media = forms.FileField(
        label="Photo / Video",
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*,video/*'}),
    )
    media_url = forms.URLField(
        label="Media URL",
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... image, video or YouTube link'}),
    )
    attachment = forms.FileField(
        label="Attach file (PDF / GPX / TXT / CSV)",
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.gpx,.txt,.csv'}),
    )
    latitude = forms.DecimalField(required=False, widget=forms.HiddenInput())
    longitude = forms.DecimalField(required=False, widget=forms.HiddenInput())
    location_name = forms.CharField(required=False, widget=forms.HiddenInput())
    route = forms.CharField(required=False, widget=forms.HiddenInput())
    difficulty = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Post
        fields = ("body", "post_media", "media_url", "attachment",
                   "latitude", "longitude", "location_name", "route", "difficulty")

    def clean_post_media(self):
        f = self.cleaned_data.get('post_media')
        if f:
            validate_post_media_file(f)
        return f

    def clean_media_url(self):
        url = self.cleaned_data.get('media_url', '')
        validate_media_url(url, allow_youtube=True)
        return url

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        if f:
            validate_attachment_file(f)
        return f

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Serialize existing route list → JSON string so the hidden input renders correctly
        if self.instance and self.instance.pk and self.instance.route:
            self.initial['route'] = json.dumps(self.instance.route)

    def clean_route(self):
        value = self.cleaned_data.get('route', '')
        if not value:
            return None
        try:
            data = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            raise forms.ValidationError("Invalid route data.")
        if not isinstance(data, list):
            raise forms.ValidationError("Route must be a list of points.")
        if len(data) > 500:
            raise forms.ValidationError("Route may not exceed 500 points.")
        for pt in data:
            if not (isinstance(pt, list) and len(pt) == 2
                    and all(isinstance(c, (int, float)) for c in pt)):
                raise forms.ValidationError("Each route point must be [lat, lng] numbers.")
        return data or None

    def clean_difficulty(self):
        value = self.cleaned_data.get('difficulty', '')
        valid = {'green', 'blue', 'red', 'black'}
        if value and value not in valid:
            raise forms.ValidationError("Invalid difficulty value.")
        return value or None

class CommentForm(forms.ModelForm):
    text = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "placeholder": "Enter Your Comment",
                "class": "form-control",
                "rows": 2,
            }
        ),
        label="",
    )
    media = forms.FileField(
        label="Photo / Video",
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*,video/*', 'class': 'comment-media-input', 'hidden': True}),
    )
    media_url = forms.URLField(
        label="Media URL",
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'https://... image, video or YouTube link'}),
    )
    attachment = forms.FileField(
        label="Attach file",
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,.gpx,.txt,.csv', 'class': 'comment-attachment-input', 'hidden': True}),
    )

    class Meta:
        model = Comment
        fields = ("text", "media", "media_url", "attachment")

    def clean_media(self):
        f = self.cleaned_data.get('media')
        if f:
            validate_post_media_file(f)
        return f

    def clean_media_url(self):
        url = self.cleaned_data.get('media_url', '')
        validate_media_url(url, allow_youtube=True)
        return url

    def clean_attachment(self):
        f = self.cleaned_data.get('attachment')
        if f:
            validate_attachment_file(f)
        return f

    def clean(self):
        cleaned_data = super().clean()
        text = (cleaned_data.get('text') or '').strip()
        if not (text or cleaned_data.get('media') or cleaned_data.get('media_url') or cleaned_data.get('attachment')):
            raise forms.ValidationError("Add some text, a photo/video, a link, or an attachment.")
        return cleaned_data


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label="", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}))
    first_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}))
    last_name = forms.CharField(label="", max_length=100, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}))

    class Meta:
        model = User 
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
    
    def clean_username(self):
        # Override clean_username to exclude the unique check during updates
        return self.cleaned_data['username']

    def __init__(self, *args, **kwargs):
        super(SignUpForm, self).__init__(*args, **kwargs) 

        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['username'].widget.attrs['placeholder'] = 'User Name'
        self.fields['username'].label = ''
        self.fields['username'].help_text = '<span class="form-text text-muted"><small>Required. 150 characters or fewer. Letters, digits, and @/./+/-/_ only</small></span>'

        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password1'].widget.attrs['placeholder'] = 'Password'
        self.fields['password1'].label = ''
        self.fields['password1'].help_text = '<ul class="form-text text-muted"><small><li>Your password can\'t be similar to your other personal information</li><li>Your password must contain at least 8 characters.</li><li>Your password can\'t be a commonly used password</li><li>Your password can’t be entirely numeric</li></ul>'

        self.fields['password2'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['placeholder'] = 'Confirm Password'
        self.fields['password2'].label = ''
        self.fields['password2'].help_text = '<span class="form-text text-muted"><small>Enter the same password as before, for verification.</small></span>'

class ProfilePicForm(forms.ModelForm):
    profile_image = forms.ImageField(
        label="Profile Photo",
        required=False,
        widget=forms.ClearableFileInput(attrs={'accept': 'image/*'}),
    )
    media_url = forms.URLField(
        label="Profile Photo URL",
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... image link'}),
    )
    profile_bio = forms.CharField(label="Profile Bio", widget=forms.Textarea(attrs={'class': 'form-control', 'placeholder': 'Profile Bio' }))
    homepage_link = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Website Link'}))
    facebook_link = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Facebook Link'}))
    instagram_link = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Instagram Link'}))
    linkedin_link = forms.CharField(label="", required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Linkedin Link'}))

    class Meta:
        model = Profile
        fields = ('profile_image', 'media_url', 'homepage_link', 'profile_bio', 'facebook_link', 'instagram_link', 'linkedin_link')

    def clean_profile_image(self):
        f = self.cleaned_data.get('profile_image')
        if f:
            validate_image_file(f)
        return f

    def clean_media_url(self):
        url = self.cleaned_data.get('media_url', '')
        validate_media_url(url, allow_youtube=False)
        return url