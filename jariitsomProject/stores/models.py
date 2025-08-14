from django.db import models
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from typing import Optional

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
    # 요일별(0~6)*시간별(0~23)로 저장
    google_hourly = models.JSONField(verbose_name="구글 인기시간대 퍼센트", blank=True, null=True)

    # 해당 요일과 시간에 해당하는 퍼센트를 꺼내옴
    def get_google_percent(self, weekday: int, hour: int):
        if not self.google_hourly: # 크롤링 데이터가 없음
            return None
        arr = self.google_hourly.get(str(weekday))
        if not arr or hour >= len(arr): # 비정상 케이스
            return None
        return arr[hour] # 퍼센트는 정수값

    # 여유/보통/혼잡으로 분류
    def percent_to_level(self, p: Optional[int]) -> str:
        if p is None:   return 'medium' # null이면 보통
        if p < 30:   return 'low'
        if p < 60:   return 'medium'
        return 'high'

    # 현재 혼잡도 계산
    def current_level_from_google(self, now=None) -> str:
        now = now or timezone.localtime()
        p = self.get_google_percent(now.weekday(), now.hour)
        return self.percent_to_level(p)

    #영업 시간, 브레이크 타임
    business_hours = models.JSONField(verbose_name="요일별 영업/브레이크 타임", blank=True, null=True)

    #가게 링크
    kakao_url = models.URLField(verbose_name="카카오맵 링크", blank=True, null=True)
    google_url = models.URLField(verbose_name="구글맵 링크", blank=True, null=True)

    #대표 메뉴 리스트
    menus = models.JSONField(verbose_name="대표 메뉴", blank=True, null=True)
    menu_names = models.TextField(verbose_name="메뉴 이름", blank=True, null=True)
    
    #### 각 가게마다 갖고 있는 무드 확인 가능 한 태그
    mood_tags = models.JSONField(verbose_name="분위기 태그", blank=True, null=True)
    
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

# 손님 방문기록 관련 모델
class VisitLog(models.Model):
    # 방문 인원 선택
    VISIT_COUNT_CHOICES = [
        (1, '1명'),
        (2, '2명'),
        (3, '3명'),
        (4, '4명'),
        (5, '5명'),
        (6, '6명 이상'),
    ]
    # 대기 시간 선택
    WAIT_TIME_CHOICES = [
        ('바로 입장', '바로 입장'),
        ('10분 이내', '10분 이내'),
        ('20분 이내', '20분 이내'),
        ('30분 이내', '30분 이내'),
        ('1시간 이내', '1시간 이내'),
        ('1시간 이상', '1시간 이상'),
    ]
    # 혼잡도 선택
    CONGESTION_CHOICES = [
        ('low', '여유'),
        ('medium', '보통'),
        ('high', '혼잡'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)  # 방문자
    store = models.ForeignKey('Store', on_delete=models.CASCADE, related_name='visit_logs')  # 어떤 가게
    
    visit_count = models.PositiveIntegerField(choices=VISIT_COUNT_CHOICES)  # 몇 명 방문
    wait_time = models.CharField(max_length=20, choices=WAIT_TIME_CHOICES)  # 대기 시간
    congestion = models.CharField(max_length=10, choices=CONGESTION_CHOICES)  # 혼잡도
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']  # 최신순 기본
        indexes = [ # 후기 최신순 리스트를 빠르게 가져오기 위함
            models.Index(fields=['store', '-created_at']),
        ]

    def __str__(self):
        return f'{self.store.name} 방문기록 - {self.user.username}'