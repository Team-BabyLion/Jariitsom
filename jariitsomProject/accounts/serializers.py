from .models import User
from rest_framework.serializers import ModelSerializer
from rest_framework import serializers

class UserSerializer(ModelSerializer):
    def create(self, validated_data): 
        user = User.objects.create_user(
            username = validated_data['username'],
            password = validated_data['password'],
            first_name = validated_data['first_name'],
            phone = validated_data['phone'],
        )
        return user
    
    #자동 호출되는 함수
    def validate_password(self, value):
        if len(value) < 8:
            raise serializers.ValidationError("비밀번호는 8자 이상이어야 합니다.")
            #raise: 이 데이터는 유효하지 않다는 걸 DRF에게 알려주는 방식, 오류를 일부러 발생시킴
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise serializers.ValidationError("영문과 숫자를 조합해서 입력하세요.")
        return value

    class Meta:
        model = User
        fields = [ 'username', 'password', 'first_name', 'phone' ]
        extra_kwargs = { 'password': { 'write_only': True } }