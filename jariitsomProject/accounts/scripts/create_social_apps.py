import os
import sys
from pathlib import Path


# manage.py가 있는 루트 디렉토리를 sys.path에 추가
# -> 스크립트 실행 시에도 프로젝트 내부 모듈 import 가능하게 해줌
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

# 장고 세팅 불러오기(장고 기능 사용하기 위해 필수)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jariitsomProject.settings')

# 장고 앱 초기화(settings, 모델 접근 위해)
import django
django.setup()

# settings에서 값 읽기
from django.conf import settings
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

client_id = settings.KAKAO_REST_API_KEY
domain = settings.SITE_DOMAIN

# id=1번 사이트가 있으면 가져오고 없으면 새로 만듦
site, _ = Site.objects.get_or_create(id=1)
site.domain = domain
site.name = domain
site.save()

# 카카오 로그인용 SocialApp 객체가 없으면 생성, 있으면 기존 것 사용
app, _ = SocialApp.objects.get_or_create(
    provider='kakao',
    defaults={
        'name': '카카오소셜로그인',
        'client_id': client_id,
        'secret': '',
        'key': '',
    }
)

# 만든 SocialApp을 위에서 만든 Site와 연결
app.sites.add(site)
print('Kakao SocialApp 설정 완료')
