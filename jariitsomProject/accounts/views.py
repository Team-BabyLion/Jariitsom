from django.contrib.auth import get_user_model
from .serializers import UserSerializer
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import permissions, status
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.hashers import check_password

User = get_user_model()

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.none() # 보안을 위해 리스트/조회 막음 -> 빈 리스트로 응답
    serializer_class = UserSerializer

    #아이디 중복 확인 실시간 검사에 사용
    @action(detail=False, methods=['get'], url_path='check-username')
    def check_username(self, request):
        username = request.query_params.get('username')
        is_taken = User.objects.filter(username=username).exists()
        return Response({'is_taken': is_taken})

# 마이페이지(조회/수정/탈퇴)
class MyAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated] # 마이페이지는 인증 필요

    # 마이페이지 최초 진입시 현재 사용자 정보 반환
    def get(self, request):
        u = request.user
        # 카카오 유저인지 확인
        is_kakao = SocialAccount.objects.filter(user=u, provider='kakao').exists()
        
        return Response({
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name,
            "phone": getattr(u, "phone", ""), # 전화번호 없으면 빈 문자열
            "is_kakao": is_kakao, # 아이디/비번 변경 숨김 처리 위해서
        }, status=200)

    # 닉네임/아이디 변경
    def patch(self, request):
        u = request.user
        is_kakao = SocialAccount.objects.filter(user=u, provider='kakao').exists()
        will_update = {}

        # 카카오면 아이디 변경 불가(혹시 몰라 추가)
        if is_kakao and "username" in request.data:
            return Response({"detail": "카카오 사용자는 아이디 변경이 허용되지 않습니다."}, status=403)

        # 닉네임(first_name)
        if "first_name" in request.data:
            first_name = (request.data.get("first_name") or "").strip()
            will_update["first_name"] = first_name

        # 아이디(username)
        if "username" in request.data:
            username = (request.data.get("username") or "").strip()
            if not username:
                return Response({"username": ["아이디를 입력하세요."]}, status=400)
            if User.objects.exclude(pk=u.pk).filter(username=username).exists(): # 본인 제외 중복 검사
                return Response({"username": ["이미 사용 중인 아이디입니다."]}, status=400)
            will_update["username"] = username

        if not will_update:
            return Response({"detail": "변경할 필드가 없습니다."}, status=400)

        for f, v in will_update.items():
            setattr(u, f, v)
        u.save(update_fields=list(will_update.keys()))
        return Response(will_update, status=200)

    # 탈퇴
    def delete(self, request):
        confirm = request.data.get("confirm")
        if confirm != "탈퇴":
            return Response({"confirm": ["'탈퇴'를 정확히 입력해 주세요."]}, status=400)
        request.user.delete()
        return Response(status=204)
    
# 비밀번호 변경
class AccountPasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user

        # 카카오면 비번 변경 불가(혹시 몰라 추가)
        if SocialAccount.objects.filter(user=user, provider='kakao').exists():
            return Response(
                {"detail": "카카오 사용자는 비밀번호 변경이 허용되지 않습니다."},
                status=403
            )
        
        current = (request.data.get("current_password") or "").strip()
        new = (request.data.get("new_password") or "").strip()
        confirm = (request.data.get("new_password_confirm") or "").strip()

        if not current:
            return Response({"current_password": ["현재 비밀번호를 입력하세요."]}, status=400)
        if new != confirm:
            return Response({"new_password_confirm": ["새 비밀번호가 일치하지 않습니다."]}, status=400)
        if not check_password(current, user.password):
            return Response({"current_password": ["현재 비밀번호가 올바르지 않습니다."]}, status=400)

        # 새 비밀번호 규칙 검증
        if len(new) < 8 or not(any(c.isalpha() for c in new) and any(c.isdigit() for c in new)):
            return Response({"new_password": ["영문+숫자 조합 8자 이상이어야 합니다."]}, status=400)

        user.set_password(new)
        user.save(update_fields=["password"])

        return Response({"detail": "비밀번호가 변경되었습니다."}, status=200)