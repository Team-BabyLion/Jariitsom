#client_id(민감정보)가 git에 올라가지 않도록 함->팀원이 카카오 로그인 사용 불가능
#팀원이 git pull + migrate만 하면 SocialApp 자동 생성되도록 파일 만들었음(배운 부분이 아니라 지피티 코드 씀)

from django.db import migrations

def create_kakao_social_app(apps, schema_editor):
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')

    site, _ = Site.objects.get_or_create(
        id=1,
        defaults={'domain': '127.0.0.1:8000', 'name': '127.0.0.1:8000'}
    )

    kakao_app, created = SocialApp.objects.get_or_create(
        provider='kakao',
        name='카카오소셜로그인',
        client_id='513115a371aaf22fcb4f017518332791',
        secret='', #kakao는 시크릿,
        key=''     #key 잘 안 씀 -> 비워둠
    )
    
    kakao_app.sites.add(site)

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('sites', '0001_initial'),
        ('socialaccount', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_kakao_social_app),
    ]
