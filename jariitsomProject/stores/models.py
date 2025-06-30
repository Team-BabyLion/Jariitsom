from django.db import models
from django.utils import timezone
from django.conf import settings

class Store(models.Model) : 
    #리스트[] & 튜플(), choices는 튜플 또는 튜플 리스트만 허용
    CATEGORY_CHOICES = [
        #'DB에 저장될 값', '사용자에게 보여줄 이름'
        ('restaurant', '음식점'),
        ('cafe', '카페/디저트'),
    ]
    SUBCATEGORY_CHOICES = [
        ('korean', '한식'),
        ('snack', '분식'),
        ('japanese', '일식'),
        ('fastfood', '패스트푸드'),
        ('salad', '샐러드'),
    ]

    CONGESTION_CHOICES = [
        ('low', '여유'),
        ('medium', '보통'),
        ('high', '혼잡'),
    ]

    #필터링을 위한 카테고리
    category = models.CharField(verbose_name="카테고리", max_length=20, choices=CATEGORY_CHOICES)
    subcategory = models.CharField(verbose_name="음식 종류", max_length=20, choices=SUBCATEGORY_CHOICES, blank=True, null=True)
    
    photo = models.ImageField(verbose_name="가게 이미지", 
                              blank=True, null=True, upload_to='store_photo')
    name = models.CharField(verbose_name="가게 이름", max_length=100)
    rating = models.FloatField(verbose_name="별점", default=0.0)
    
    #위치, 거리
    address = models.CharField(verbose_name="주소", max_length=200)
    latitude = models.FloatField(verbose_name="위도")
    longitude = models.FloatField(verbose_name="경도")
    
    #혼잡도
    congestion = models.CharField(verbose_name="혼잡도", max_length=10, choices=CONGESTION_CHOICES, default='low')
    current_customers = models.IntegerField(verbose_name="현재 손님 수", default=0)
    max_customers = models.IntegerField(verbose_name="최대 수용 인원", default=0)

    #영업 시간
    open_time = models.TimeField(verbose_name="영업 시작 시간", blank=True, null=True)
    close_time = models.TimeField(verbose_name="영업 종료 시간", blank=True, null=True)
    break_start_time = models.TimeField(verbose_name="브레이크타임 시작 시간", blank=True, null=True)
    break_end_time = models.TimeField(verbose_name="브레이크타임 종료 시간", blank=True, null=True)

    def is_open_now(self):
        now = timezone.localtime().time()
        # timezone.now() → 현재 시간을 반환, timezone.localtime() → 로컬 시간으로 바꿔줌
        # 내부적으로 timezone.now() 호출: timezone.localtime(timezone.now()).time()
        # 현재 시간(.localtime)을 얻고, 시간 부분만 분리(.time)
        if self.open_time and self.close_time: 
            return self.open_time <= now <= self.close_time
            # 지금이 영업 시간 범위에 포함되는지 True, False 반환
        return False

    def is_breaktime_now(self):
        now = timezone.localtime().time()
        if self.break_start_time and self.break_end_time:
            return self.break_start_time <= now <= self.break_end_time
        return False

    #가게 링크
    naver_url = models.URLField(verbose_name="가게 네이버 링크", blank=True, null=True)

    created_at = models.DateTimeField(verbose_name="등록일", auto_now_add=True)
    
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