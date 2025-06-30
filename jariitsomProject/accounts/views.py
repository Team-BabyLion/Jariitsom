from django.shortcuts import render
from .models import User
from .serializers import UserSerializer
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

    # 회원가입과 아이디(username) 중복 체크는 모두 인증 없이 요청 가능
    def get_permissions(self):
        if self.action in ['create', 'check_username']:
            return [AllowAny()]
        return super().get_permissions()

    #아이디 중복 확인 실시간 검사에 사용
    @action(detail=False, methods=['get'], url_path='check-username')
    def check_username(self, request):
        username = request.query_params.get('username')

        is_taken = User.objects.filter(username=username).exists()
        return Response({'is_taken': is_taken})