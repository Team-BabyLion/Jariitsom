from rest_framework import serializers
from django.utils import timezone
from .models import Store, Bookmark, VisitLog
from .forecast import ensure_ai_congestion_now

# 거리에 따른 도보 시간 계산 함수
def walk_minutes(distance):
    if distance is not None:
        return int(distance / 67) + 1 # 직선 거리임을 고려 -> 1분 추가
    return None

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']

class StoreSerializer(serializers.ModelSerializer): 
    # SerializerMethodField(): 읽기 전용 필드, 직렬화 시에 동적으로 계산된 값을 넣고 싶을 때 사용
    is_bookmarked = serializers.SerializerMethodField()

    user_distance = serializers.SerializerMethodField()
    user_walk_minutes = serializers.SerializerMethodField()
    main_gate_walk_minutes = serializers.SerializerMethodField()
    back_gate_walk_minutes = serializers.SerializerMethodField()

    ai_congestion_now = serializers.SerializerMethodField()

    # 필드 선언하면 직렬화 할 때 이 메소드를 자동으로 호출
    # 이름 규칙: get_필드명
    def get_is_bookmarked(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            return Bookmark.objects.filter(user=user, store=obj).exists()
        return False
    
    # 거리, 도보 시간
    def get_user_distance(self, obj):
        # views.py get_queryset에서 계산해서 붙여줌
        return getattr(obj, '_user_distance', None)

    def get_user_walk_minutes(self, obj):
        distance = self.get_user_distance(obj)
        return walk_minutes(distance)

    def get_main_gate_walk_minutes(self, obj):
        distance = obj.main_gate_distance
        return walk_minutes(distance)

    def get_back_gate_walk_minutes(self, obj):
        distance = obj.back_gate_distance
        return walk_minutes(distance)
    
    # 이 호출 시점에 db의 congestion도 최신 예측 값으로 동기화됨
    def get_ai_congestion_now(self, obj: Store) -> str:
        return ensure_ai_congestion_now(obj)

    class Meta:
        model = Store
        fields = [ 'id', 'category', 'photo', 'name', 'rating', 'address', 
                  'latitude', 'longitude', 'main_gate_distance', 'back_gate_distance',
                  'user_distance', 'user_walk_minutes',
                  'main_gate_distance', 'main_gate_walk_minutes',
                  'back_gate_distance', 'back_gate_walk_minutes',
                  'ai_congestion_now', 'congestion',
                  'business_hours', 'is_bookmarked', 'kakao_url', 'google_url', 'menus',
                  'mood_tags' ]
        # is_~들은 모델에는 필요 없는 필드지만, 프론트에는 보내줘야 함
        # 프론트에도 mood_tag 전달 가능

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
    when = serializers.SerializerMethodField() # 5분 전, 1시간 전, 14:01 ...
    day_label = serializers.SerializerMethodField() # 오늘, 어제, 20xx.xx.xx(요일)

    def get_when(self, obj):
        dt = timezone.localtime(obj.created_at)
        today = timezone.localdate()
        # 오늘 방문 기록일 경우
        if dt.date() == today:
            delta = timezone.localtime() - dt
            mins = int(delta.total_seconds() // 60)
            if mins < 1:
                return '방금 전'
            if mins < 60:
                return f'{mins}분 전'
            hours = mins // 60
            return f'{hours}시간 전'
        # 오늘이 아니면 시각으로
        return dt.strftime('%H:%M')

    # 방문 후기 날짜별 라벨링
    def get_day_label(self, obj):
        dt = timezone.localtime(obj.created_at).date()
        today = timezone.localdate()
        diff = (today - dt).days
        if diff == 0:
            return '오늘'
        if diff == 1:
            return '어제'
        return f"{dt.strftime('%Y.%m.%d')}({WEEKDAYS[dt.weekday()]})"

    class Meta:
        model = VisitLog
        fields = ['id', 'visit_count', 'wait_time', 'congestion',
                  'created_at', 'when', 'day_label']

# 지도에서 가게별 위치 표시할 때 필요한 경량 마커        
class StoreMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ["id", "name", "category", "latitude", "longitude", "kakao_url", "congestion"]