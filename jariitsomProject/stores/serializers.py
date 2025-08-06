from rest_framework import serializers
from .models import Store, Bookmark, VisitLog

def walk_minutes(distance):
    if distance is not None:
        return int(distance / 67) + 1
    return None

class StoreSerializer(serializers.ModelSerializer): 
    # SerializerMethodField(): 읽기 전용 필드, 직렬화 시에 동적으로 계산된 값을 넣고 싶을 때 사용
    is_bookmarked = serializers.SerializerMethodField()

    user_distance = serializers.SerializerMethodField()
    user_walk_minutes = serializers.SerializerMethodField()
    main_gate_walk_minutes = serializers.SerializerMethodField()
    back_gate_walk_minutes = serializers.SerializerMethodField()

    # 필드 선언하면 직렬화 할 때 이 메소드를 자동으로 호출
    # 이름 규칙: get_필드명
    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return Bookmark.objects.filter(user=user, store=obj).exists()
        return False
    
    def get_user_distance(self, obj):
        # views.py get_queryset에서 계산해서 붙여줌
        return getattr(obj, '_user_distance', None)

    def get_user_walk_minutes(self, obj):
        distance = self.get_user_distance(obj)
        return walk_minutes(distance)

    def get_main_gate_walk_minutes(self, obj):
        return int(obj.main_gate_distance / 80) + 1 if obj.main_gate_distance else None

    def get_back_gate_walk_minutes(self, obj):
        return int(obj.back_gate_distance / 80) + 1 if obj.back_gate_distance else None

    class Meta:
        model = Store
        fields = [ 'id', 'category', 'photo', 'name', 'rating', 'address', 
                  'latitude', 'longitude', 'main_gate_distance', 'back_gate_distance',
                  'user_distance', 'user_walk_minutes',
                  'main_gate_distance', 'main_gate_walk_minutes',
                  'back_gate_distance', 'back_gate_walk_minutes',
                  'congestion', 'current_customers', 'max_customers', 
                  'business_hours', 'is_bookmarked', 'kakao_url', 'menus' ]
        # is_~들은 모델에는 필요 없는 필드지만, 프론트에는 보내줘야 함

# 혼잡도 구현을 위한 혼잡도 관련 필드만 처리하는 serializer
class StoreCongestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ['id', 'name', 'current_customers', 'max_customers', 'congestion']
        # 변경 불가능하게끔 그냥 읽기만 되는 필드 지정
        read_only_fields = ['id', 'name', 'max_customers']

# 즐겨찾기 객체 직렬화
class BookmarkSerializer(serializers.ModelSerializer):
    store = StoreSerializer(read_only=True)  # 즐겨찾기한 가게 전체 정보 포함 응답에 사용
    store_id = serializers.PrimaryKeyRelatedField(
        queryset=Store.objects.all(), 
        source='store', # Bookmark(store=Store.objects.get(pk=store_id)) 형태로 저장됨
        write_only=True
        ) # 클라이언트가 store_id를 보내면 drf가 Bookmark.store에 연결해줌

    class Meta:
        model = Bookmark
        fields = ['id', 'store', 'store_id', 'created_at']
        # 북마크 아이디, 가게 전체 정보, 가게 아이디, 북마크한 시각

# 손님 방문 기록 직렬화
class VisitLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitLog
        # visit_count => 방문객 명수, created_at => 해당 기록이 작성된 시간
        fields = ['id', 'store', 'visit_count', 'wait_time', 'congestion', 'created_at']
        read_only_fields = ['id', 'created_at']