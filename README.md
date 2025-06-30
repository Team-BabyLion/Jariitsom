# 자리있솜 프로젝트
---
## 설치 방법(초기 세팅)
- git 관련은 노션 참고
1. python -m venv myvenv
2. source myvenv/Scripts/activate
3. cd jariitsom
4. pip install -r requirements.txt
5. python manage.py makemigrations
6. python manage.py migrate
7. python manage.py createsuperuser

+) python manage.py loaddata stores/fixtures/stores_data.json

---
## git 협업 방법
- 개발은 팀 레포의 develop 브랜치에서 진행(PR 여기로)
- 제출 전 main으로 merge

#### 로컬에서 작업하기 전
1. git pull origin(팀장)/upstream(팀원) develop
#### 로컬에서 작업한 후
- Store 데이터가 변경 된 경우
  - python manage.py dumpdata stores.Store --indent 2 > stores/fixtures/stores_data.json
- 설치 패키지가 추가된 경우
  - pip freeze > requirements.txt(프로젝트 폴더 내에서)
2. git status(변경사항 확인, 필수 x)
3. git add .
4. git commit -m "커밋 메시지"
5. git push origin "브랜치명"
#### 깃허브 사이트에서
6. develop으로 PR 보내기
7. 팀장 확인 후 merge
---
## 가게 데이터 유지 관련

#### 설치 후 가게 데이터 받기
- 만약 pull 해온 Store 데이터와 내 Store 데이터가 다르다면 미리 삭제 작업(충돌 방지)
1. python manage.py shell
- 이 밑은 shell에서 작성
2. from stores.models import Store
3. Store.objects.all().delete()
4. exit()

- pull 해온 Store 데이터와 충돌이 나지 않을 데이터가 존재하거나, Store 데이터가 없다면
5. python manage.py loaddata stores/fixtures/stores_data.json

#### 만약 가게 데이터를 변경/추가 했을 경우
- python export_stores.py

#### 초기 데이터 구성
- python manage.py dumpdata stores.Store --indent 2 > stores/fixtures/stores_data.json
- 만약 stores 앱에 fixtures 디렉토리가 없다면 추가해야 함
