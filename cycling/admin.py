from django.contrib import admin
from .models import Comment, Profile, Post
from django.contrib.auth.models import User


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    readonly_fields = ('user', 'created_at')


class PostAdmin(admin.ModelAdmin):
    list_display = ('user', 'body', 'created_at', 'number_of_likes')
    inlines = [CommentInline]

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()


admin.site.register(Post, PostAdmin)
admin.site.register(Profile)

class ProfileInline(admin.StackedInline):
    model = Profile

class UserAdmin(admin.ModelAdmin):
    model = User 
    fields = ["username"]
    inlines = [ProfileInline]

