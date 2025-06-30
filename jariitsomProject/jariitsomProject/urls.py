"""
URL configuration for jariitsomProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

#HttpResponse: home 화면 없어서 임시로 만든거, home 화면 생기면 지울거임
from django.http import HttpResponse

urlpatterns = [
    path('admin/', admin.site.urls),

    #home 화면 없어서 임시로 만든거
    path('', lambda request: HttpResponse("임시 홈")),

    path('', include('accounts.urls')),
    path('authaccounts/', include('allauth.urls')), #소셜 로그인
    path('', include('stores.urls')), # 혼잡도 구현을 위해서는 해당 줄 삭제 절대 금물
]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
