from rest_framework import serializers
from .models import Store, Bookmark, VisitLog

class StoreSerializer(serializers.ModelSerializer): 
    # 현재 시간에 따라 값이 입력되는 is_open, is_breaktime 필드
    # SerializerMethodField(): 읽기 전용 필드, 직렬화 시에 동적으로 계산된 값을 넣고 싶을 때 사용
    is_open = serializers.SerializerMethodField()
    is_breaktime = serializers.SerializerMethodField()
    is_bookmarked = serializers.SerializerMethodField()

    # 필드 선언하면 직렬화 할 때 이 메소드를 자동으로 호출
    # 이름 규칙: get_필드명
    def get_is_open(self, obj):
        return obj.is_open_now()

    def get_is_breaktime(self, obj):
        return obj.is_breaktime_now()
    
    def get_is_bookmarked(self, obj):
        user = self.context['request'].user
        return Bookmark.objects.filter(user=user, store=obj).exists()

    class Meta:
        model = Store
        fields = [ 'id', 'category', 'subcategory', 'photo', 'name', 
                  'rating', 'address', 'latitude', 'longitude', 
                  'congestion', 'current_customers', 'max_customers', 
                  'open_time', 'close_time', 'break_start_time', 'break_end_time', 
                  'is_open', 'is_breaktime', 'is_bookmarked', 'naver_url', 'created_at' ]
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