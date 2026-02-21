"""
URL configuration for cookbook project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path('recipes/', include("recipes.urls")),
    path('admin/', admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("accounts/", include("accounts.urls")),
    path('', RedirectView.as_view(url='/recipes/', permanent=True)),
    path('sw.js', TemplateView.as_view(template_name="sw.js", content_type='application/javascript'), name='sw.js'),
    path('manifest.json', TemplateView.as_view(template_name="manifest.json", content_type='application/json'), name='manifest.json'),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)