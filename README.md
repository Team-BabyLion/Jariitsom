# 자리있솜 프로젝트
---
## 설치 방법(초기 세팅)
0. .env.example과 같은 위치에 .env 파일 생성 후 실제 값으로 변경
1. python -m venv myvenv
2. source myvenv/Scripts/activate
3. cd jariitsomProject
4. pip install -r requirements.txt
5. python manage.py makemigrations
6. python manage.py migrate
7. python manage.py createsuperuser
8. python accounts/scripts/create_social_apps.py
9. python manage.py fetch_kakao_places
10. python manage.py update_store_info
11. python manage.py fetch_google_populartimes
12. python manage.py shell
- 셸에서 입력
        
```
from stores.models import Store

deleted_count, _ = Store.objects.filter(photo__isnull=True).delete()

print(f"{deleted_count}개의 가게가 삭제되었습니다.")
```
```
from stores.models import Store

for store in Store.objects.all():
    menus = store.menus or []
    names = ', '.join([m['name'] for m in menus if m.get('name')])
    store.menu_names = names
    store.save()
```
```
exit()
```
13. python manage.py crawl_kakao_reviews

---

## 크롤러 개발환경(셀레니움) 사용을 위해 드라이버 설치
- 본인의 크롬 브라우저 버전에 맞는 크롬 드라이버(https://chromedriver.chromium.org/downloads) 다운로드
- 다운로드한 폴더의 압축을 해제하고 chromedriver(.exe)를 프로젝트 폴더에 복사(manage.py와 같은 위치)

---

## git 협업 방법
- 개발은 팀 레포의 develop 브랜치에서 진행(PR 여기로)
- 제출 전 main으로 merge

#### 로컬에서 작업하기 전
1. git pull origin(팀장)/upstream(팀원) develop
#### 로컬에서 작업한 후
- 설치 패키지가 추가된 경우
  - pip freeze > requirements.txt(프로젝트 폴더 내에서)
- 가게 정보가 변경되었을 경우
  - python manage.py fetch_kakao_places
2. git status(변경사항 확인, 필수 x)
3. git add .
4. git commit -m "커밋 메시지"
5. git push origin "브랜치명"
#### 깃허브 사이트에서
6. develop으로 PR 보내기
7. 팀장 확인 후 merge

