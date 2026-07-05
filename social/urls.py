from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from core import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('cycling.urls')),
    path('items', include('item.urls')),
    path('dashboard', include('dashboard.urls')),
    path('index/',core_views.index, name='index'),
    path('contact/',core_views.contact, name='contact'),
    path('inbox/', include('conversation.urls')),


]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
