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

