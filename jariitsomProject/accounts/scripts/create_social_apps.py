import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# manage.py가 있는 루트 디렉토리를 sys.path에 추가
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

# settings 모듈 경로 설정
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jariitsomProject.settings')

import django
django.setup()

# 이하 동일
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site

load_dotenv()

client_id = os.getenv('KAKAO_REST_API_KEY')
domain = os.getenv('SITE_DOMAIN', 'localhost:8000')

site, _ = Site.objects.get_or_create(id=1)
site.domain = domain
site.name = domain
site.save()

app, _ = SocialApp.objects.get_or_create(
    provider='kakao',
    defaults={
        'name': '카카오소셜로그인',
        'client_id': client_id,
        'secret': '',
        'key': '',
    }
)

app.sites.add(site)
print('Kakao SocialApp 설정 완료')
