from django.db import models
from django.utils import timezone
from django.conf import settings

class Store(models.Model) : 
    #리스트[] & 튜플(), choices는 튜플 또는 튜플 리스트만 허용
    CATEGORY_CHOICES = [
        #'DB에 저장될 값', '사용자에게 보여줄 이름'
        ('cafe', '카페,디저트'),
        ('korean', '한식'),
        ('chinese', '중식'),
        ('japanese', '일식'),
        ('fastfood', '패스트푸드'),
        ('bunsik', '분식'),
        ('healthy', '건강식'),
        ('western', '양식'),
        ('bbq', '고깃집'),
        ('bar', '주점'),
    ]

    CONGESTION_CHOICES = [
        ('low', '여유'),
        ('medium', '보통'),
        ('high', '혼잡'),
    ]

    #필터링을 위한 카테고리
    category = models.CharField(verbose_name="카테고리", max_length=20, choices=CATEGORY_CHOICES, blank=True, null=True)
    
    photo = models.URLField(verbose_name="가게 이미지", blank=True, null=True)
    name = models.CharField(verbose_name="가게 이름", max_length=100)
    rating = models.FloatField(verbose_name="별점", default=0.0)
    
    #위치, 거리
    address = models.CharField(verbose_name="주소", max_length=200)
    latitude = models.FloatField(verbose_name="위도")
    longitude = models.FloatField(verbose_name="경도")

    main_gate_distance = models.IntegerField(default=0)  # 정문까지 거리(m)
    back_gate_distance = models.IntegerField(default=0)  # 후문까지 거리(m)
    
    #혼잡도
    congestion = models.CharField(verbose_name="혼잡도", max_length=10, choices=CONGESTION_CHOICES, default='low')
    current_customers = models.IntegerField(verbose_name="현재 손님 수", default=0)
    max_customers = models.IntegerField(verbose_name="최대 수용 인원", default=0)

    #영업 시간, 브레이크 타임
    business_hours = models.JSONField(verbose_name="요일별 영업/브레이크 타임", blank=True, null=True)

    #가게 링크
    kakao_url = models.URLField(verbose_name="카카오맵 링크", blank=True, null=True)

    #대표 메뉴 리스트
    menus = models.JSONField(verbose_name="대표 메뉴", blank=True, null=True)
    
    def __str__(self):
        return self.name

# 즐겨찾기 모델(사용자와 즐겨찾기 가게 관계 저장)
class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookmarks')
                            # 만들어둔 accounts.User 참조, 사용자가 삭제되면 같이 삭제됨
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='bookmarked_by')
                            # 즐겨찾기 대상인 가게, 가게가 삭제되면 같이 삭제됨
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'store')  # 중복 즐겨찾기 방지

    def __str__(self):
        return f"{self.user} bookmarks {self.store}"

# 손님 방문기록 관련 모델 추가
class VisitLog(models.Model):

    VISIT_COUNT_CHOICES = [
        (1, '1명'),
        (2, '2명'),
        (3, '3명'),
        (4, '4명'),
        (5, '5명'),
        (6, '6명 이상'),
    ]

    WAIT_TIME_CHOICES = [
        ('바로 입장', '바로 입장'),
        ('10분 이내', '10분 이내'),
        ('20분 이내', '20분 이내'),
        ('30분 이내', '30분 이내'),
        ('1시간 이내', '1시간 이내'),
        ('2시간 이상', '2시간 이상'),
    ]

    CONGESTION_CHOICES = [
        ('여유', '여유'),
        ('보통', '보통'),
        ('혼잡', '혼잡'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # 방문자
    store = models.ForeignKey('Store', on_delete=models.CASCADE, related_name='visit_logs')  # 어떤 가게
    visit_count = models.PositiveIntegerField(choices=VISIT_COUNT_CHOICES)  # 몇 명 방문
    wait_time = models.CharField(max_length=20, choices=WAIT_TIME_CHOICES)  # 대기 시간 (예: '바로 입장', '10분 이내' 등)
    congestion = models.CharField(max_length=10, choices=CONGESTION_CHOICES)  # 혼잡도 정보 (예: '여유', '보통', '혼잡')
    created_at = models.DateTimeField(auto_now_add=True)  # 언제 입력했는지

    def __str__(self):
        return f'{self.store.name} 방문기록 - {self.user.username}'