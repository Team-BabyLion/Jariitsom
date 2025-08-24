import json
from typing import List
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from math import cos, radians
from rest_framework.decorators import api_view, action
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, filters, permissions
from .serializers import VisitLogSerializer, BookmarkSerializer
from .serializers import StoreSerializer
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from .utils import haversine, read_coords_from_request, read_radius_topk
from .apis import get_gemini_conditions, get_gemini_chat_reply
from .apis import extract_conditions, missing_slots, follow_up_question

from .models import Store, Bookmark, VisitLog
from .forecast import forecast_congestion, ensure_ai_congestion_now

from collections import defaultdict
from datetime import datetime, timedelta, time
from django.utils import timezone

from .kakao_ai_crawl import crawl_kakao_ai_by_place_id, extract_place_id
from .mood_extractor import pick_mood_tags

# 거리 문자열 도움주는 함수
def _meters_to_text(m):
    if m is None:
        return None
    m_rounded = int(round(m / 50.0) * 50)
    return f"{m_rounded}m" if m_rounded < 1000 else f"{m_rounded/1000:.1f}km"

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']

def _parse_range(s: str):
    if not s or "~" not in s:
        return None, None
    try:
        a, b = [p.strip() for p in s.split("~", 1)]
        ha, ma = map(int, a.split(":"))
        hb, mb = map(int, b.split(":"))
        return time(ha, ma), time(hb, mb)
    except Exception:
        return None, None

def _aware_today(t: time, base_dt):
    naive = datetime.combine(base_dt.date(), t)
    return timezone.make_aware(naive, base_dt.tzinfo)

# 영업종료일 경우만 true
def _is_closed_now(store, now):
    bh = getattr(store, "business_hours", None) or {}
    today = bh.get(WEEKDAYS[now.weekday()], {}) or {}

    open_t, close_t = _parse_range((today.get("open_close") or "").strip())
    if not (open_t and close_t):
        return False

    start_dt = _aware_today(open_t, now)
    end_dt   = _aware_today(close_t, now)
    if end_dt <= start_dt:
        end_dt += timedelta(days=1)

    return not (start_dt <= now < end_dt)

class StoreViewSet(ModelViewSet):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'menu_names']
    ordering_fields = ['rating']

    # 시리얼라이저에 추가 컨텍스트 전달
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        context['user_lat'] = self.request.query_params.get('user_lat')
        context['user_lng'] = self.request.query_params.get('user_lng')
        return context

    def get_queryset(self):
        queryset = Store.objects.all() # 여기에 한 번 더 선언 해줘야 됨
        category = self.request.query_params.get('category')
        bookmarked = self.request.query_params.get('bookmarked')

        if category is not None:
            queryset = queryset.filter(category=category)
            # 왼쪽 카테고리는 필드 이름(인자명), 오른쪽 카테고리는 쿼리스트링에서 받아온 값(변수)
            # 조건이 대체 되는 게 아닌 누적 되는 식으로 작동함

        if bookmarked == 'true':
            queryset = queryset.filter(bookmarked_by__user=self.request.user)
            # 이 store를 즐겨찾기한 사용자 중 현재 로그인한 사용자가 있는지 역참조

        return queryset
    
    # 정렬 커스터마이징
    def list(self, request, *args, **kwargs):
        from .forecast import ensure_ai_congestion_now
        qs = self.filter_queryset(self.get_queryset())

        # distance, relaxed, rating 등 정렬 모드 읽기
        ordering = request.query_params.get('ordering')
        user_lat = request.query_params.get('user_lat')
        user_lng = request.query_params.get('user_lng')

        # 커스텀 정렬을 위해 쿼리셋을 리스트로 변환
        items = list(qs)

        # 정렬과 무관하게 좌표가 오면 거리 계산
        if user_lat and user_lng:
            ulat, ulng = float(user_lat), float(user_lng)
            for s in items:
                s._user_distance = haversine(ulat, ulng, s.latitude, s.longitude)

        LEVEL_RANK = {'low': 0, 'medium': 1, 'high': 2}

        # 현재 혼잡도 부여
        for s in items:
            ai_level = ensure_ai_congestion_now(s)
            s._ai_level = ai_level
            s._ai_rank = LEVEL_RANK.get(ai_level, 1)

        # 영업종료인 가게는 리스트에서 조회 불가능
        now = timezone.localtime()
        items = [s for s in items if not _is_closed_now(s, now)]

        if ordering == 'distance': # 거리순 정렬
            # 거리가 없다면 무한대로 취급 -> 가장 뒤로 감
            items.sort(key=lambda s: getattr(s, '_user_distance', float('inf')))
        elif ordering == 'relaxed': # 여유로운순 정렬
            items.sort(key=lambda s: (s._ai_rank, s.id))
        elif ordering == 'rating': # 별점높은순 정렬
            items.sort(key=lambda s: (-s.rating, s.id))
        else: # 기본 정렬(id순)
            items.sort(key=lambda s: s.id)

        # 무한 스크롤을 위한 서버 슬라이싱
        limit = int(request.query_params.get('limit', 50))
        offset = int(request.query_params.get('offset', 0))
        sliced = items[offset:offset + limit]

        # 슬라이싱 한 것들을 시리얼라이즈
        serializer = self.get_serializer(sliced, many=True)
        return Response(serializer.data)
    
    # ========= 지도 가게 위치 표시 ===========
    @method_decorator(cache_page(10))  # 쿼리스트링 포함 경로 단위로 10초 캐시
    @action(detail=False, methods=["GET"], url_path="markers")
    def markers(self, request):
        """
        지도 마커용 경량 데이터.
        필터:
          - BBox: sw_lat, sw_lng, ne_lat, ne_lng  (권장: 지도 뷰포트 갱신용)
          - Circle: lat, lng, radius(미터)
        옵션:
          - category=cafe|korean|... 
          - limit, offset
          - cluster=true|false   (기본 false)
          - cell_m=80            (클러스터 격자 크기, meters)
        응답:
          - cluster=false: [{id, name, category, latitude, longitude, kakao_url, congestion}, ...]
          - cluster=true : [{lat, lng, count, ids:[...]}]  # 대표 좌표 + 그룹 개수
        """
        from .serializers import StoreMarkerSerializer  # 지연 임포트(순환참조 방지)

        qs = Store.objects.all()
        category = request.query_params.get("category")
        exclude_category = request.query_params.get("exclude_category")

        # 특정 카테고리 포함
        if category:
            qs = qs.filter(category=category)

        # 특정 카테고리 제외
        if exclude_category:
            qs = qs.exclude(category=exclude_category)

        # 1) BBox 파라미터
        sw_lat = request.query_params.get("sw_lat")
        sw_lng = request.query_params.get("sw_lng")
        ne_lat = request.query_params.get("ne_lat")
        ne_lng = request.query_params.get("ne_lng")

        # 2) Circle 파라미터
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        radius = request.query_params.get("radius")  # meters

        cluster = (request.query_params.get("cluster", "false").lower() == "true")
        try:
            cell_m = float(request.query_params.get("cell_m", 80.0))  # 기본 80m 셀
        except ValueError:
            cell_m = 80.0

        # BBox가 오면 우선 적용
        if all([sw_lat, sw_lng, ne_lat, ne_lng]):
            try:
                sw_lat, sw_lng = float(sw_lat), float(sw_lng)
                ne_lat, ne_lng = float(ne_lat), float(ne_lng)
            except ValueError:
                return Response({"detail": "bbox 파라미터가 잘못되었습니다."}, status=400)

            # 남서-북동 정상화(뒤집혀 들어온 케이스 방지)
            if ne_lat < sw_lat:
                sw_lat, ne_lat = ne_lat, sw_lat
            if ne_lng < sw_lng:
                sw_lng, ne_lng = ne_lng, sw_lng

            qs = qs.filter(
                latitude__gte=sw_lat, latitude__lte=ne_lat,
                longitude__gte=sw_lng, longitude__lte=ne_lng
            )

        # BBox가 없고 Circle이 오면 반경 필터
        elif all([lat, lng, radius]):
            try:
                lat, lng, radius = float(lat), float(lng), float(radius)
            except ValueError:
                return Response({"detail": "lat/lng/radius 파라미터가 잘못되었습니다."}, status=400)

            # 성능 위해 대략 bbox로 1차 축소
            ddeg = max(0.01, radius / 100000.0)  # 아주 대략, 위경도 0.01도 ≈ ~1km
            rough = qs.filter(
                latitude__gte=lat - ddeg, latitude__lte=lat + ddeg,
                longitude__gte=lng - ddeg, longitude__lte=lng + ddeg
            ).only("id", "name", "category", "latitude", "longitude", "kakao_url", "congestion")

            # 정확한 반경은 하버사인으로 2차 필터
            filtered = []
            for s in rough:
                try:
                    d = haversine(lat, lng, s.latitude, s.longitude)
                    if d <= radius:
                        filtered.append(s)
                except Exception:
                    continue
            qs = filtered  # 리스트로 교체
        
        else:
            # 필터 없이 호출되면 과도 응답 방지
            return Response({"detail": "bbox 또는 lat/lng/radius 중 하나는 반드시 필요합니다."}, status=400)

        # --- 클러스터링 옵션 ---
        if cluster:
            # meters → degrees 변환(경도는 위도에 따라 달라서 중심 위도 기준)
            if isinstance(qs, list) and qs:
                center_lat = sum(s.latitude for s in qs) / len(qs)
            else:
                # BBox의 중앙 위도 추정
                if all([sw_lat, ne_lat]):
                    center_lat = (float(sw_lat) + float(ne_lat)) / 2.0
                else:
                    center_lat = float(lat) if lat else 37.5

            lat_deg_per_m = 1.0 / 111320.0
            lon_deg_per_m = 1.0 / (111320.0 * max(0.1, cos(radians(center_lat))))  # 극지방 안정화

            lat_step = cell_m * lat_deg_per_m
            lon_step = cell_m * lon_deg_per_m

            buckets = {}  # (gi, gj) -> {"lat":..., "lng":..., "count":..., "ids":[...]}
            iterable = qs if isinstance(qs, list) else qs.iterator()
            for s in iterable:
                if s.latitude is None or s.longitude is None:
                    continue
                gi = round(s.latitude / lat_step)
                gj = round(s.longitude / lon_step)
                key = (gi, gj)
                slot = buckets.get(key)
                if not slot:
                    buckets[key] = {
                        "lat": s.latitude,
                        "lng": s.longitude,
                        "count": 1,
                        "ids": [s.id],
                    }
                else:
                    # 간단 평균으로 대표 좌표 갱신
                    c = slot["count"] + 1
                    slot["lat"] = (slot["lat"] * slot["count"] + s.latitude) / c
                    slot["lng"] = (slot["lng"] * slot["count"] + s.longitude) / c
                    slot["count"] = c
                    slot["ids"].append(s.id)

            # 슬라이싱(무한스크롤/성능 보호)
            limit = int(request.query_params.get("limit", 300))
            offset = int(request.query_params.get("offset", 0))
            groups = list(buckets.values())
            sliced = groups[offset:offset + limit]
            # 클러스터 응답
            return Response(sliced)
    
        # --- 일반(비클러스터) 모드 ---
        limit = int(request.query_params.get("limit", 300))
        offset = int(request.query_params.get("offset", 0))
        
        if isinstance(qs, list):
            sliced = qs[offset:offset + limit]
            ser = StoreMarkerSerializer(sliced, many=True)
            return Response(ser.data)

        qs = qs[offset:offset + limit]
        ser = StoreMarkerSerializer(qs, many=True)
        return Response(ser.data)

    
# 클릭할 때마다 즐겨찾기 추가, 삭제
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_bookmark(request, store_id):
    user = request.user
    store = Store.objects.get(id=store_id)
    bookmark, created = Bookmark.objects.get_or_create(user=user, store=store)
    #즐겨찾기가 이미 되어 있으면 -> created == False
    
    if not created: 
        bookmark.delete() # 즐겨찾기에서 삭제
        return Response(status=200) 
    return Response(status=201) 

# 로그인한 사용자의 즐겨찾기 리스트 가져오기
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_bookmarks(request):
    user = request.user
    bookmarks = Bookmark.objects.filter(user=user).select_related('store')
    # 해당 사용자가 북마크한 가게 목록을 가져옴과 동시에 store 정보까지 가져옴
    serializer = BookmarkSerializer(bookmarks, many=True, context={'request':request})
    return Response(serializer.data)

# 손님 방문 기록 작성
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_visit_log(request, store_id):
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return Response({'error': '가게 정보를 찾을 수 없습니다.'}, status=404)

    serializer = VisitLogSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(user=request.user, store=store)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

# 손님 방문 기록 조회: GET ~/visitlogs/list/?expand=true&days=7&limit_per_day=50
@api_view(['GET'])
def get_visit_logs(request, store_id):
    expand = request.GET.get('expand', 'false').lower() == 'true' # true면 오늘+과거 n일까지(더보기 클릭)
    days = int(request.GET.get('days', 7)) # 과거 며칠 포함(기본 7)
    limit_per_day = int(request.GET.get('limit_per_day', 50)) # 하루 섹션당 최대 개수

    now = timezone.localtime()
    today = now.date()
    start_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    start_tomorrow = start_today + timedelta(days=1)

    # expand 범위만큼 잘라서 가져오기
    start_range = start_today if not expand else (start_today - timedelta(days=days))
    qs = (VisitLog.objects
          .filter(store_id=store_id, created_at__gte=start_range, created_at__lt=start_tomorrow)
          .order_by('-created_at'))

    # 날짜별 딕셔너리(키: 날짜, 값: 로그 리스트)
    buckets = defaultdict(list)
    for log in qs:
        d = timezone.localtime(log.created_at).date()
        buckets[d].append(log)

    # 섹션 순서: 오늘 -> 어제 -> ... 날짜 내림차순
    ordered_days = [today] if not expand else [today] + [today - timedelta(days=i) for i in range(1, days+1)]

    groups = [] # 섹션 리스트, 각각{label, items}
    for day in ordered_days:
        items = buckets.get(day, [])
        if not items:
            continue
        ser = VisitLogSerializer(items[:limit_per_day], many=True)
        # 섹션 라벨은 각 아이템의 day_label을 그대로 사용 (모두 동일)
        label = ser.data[0]['day_label'] if ser.data else '오늘'
        groups.append({'label': label, 'items': ser.data})

    return Response({'expanded': expand, 'groups': groups})


# 가게 리뷰(카카오 AI 요약/불릿/블로그 요약) 크롤링 → 무드 태그 저장
@api_view(['POST'])
def update_mood_tags(request, store_id):
    store = get_object_or_404(Store, pk=store_id)

    if not store.kakao_url:
        return Response({'error': '카카오맵 링크가 없습니다.'}, status=400)

    # http/https 모두 대응해서 place_id 추출
    place_id = extract_place_id(store.kakao_url)
    if not place_id:
        return Response({'error': 'place_id 추출 실패'}, status=400)

    data = crawl_kakao_ai_by_place_id(place_id)
    # 세 가지 중 하나라도 있으면 성공으로 간주
    if not data or (
        not data.get("store_summary") and
        not data.get("ai_bullets") and
        not data.get("blog_keywords")
    ):
        store.mood_tags = ["요약 없음"]
        store.save(update_fields=["mood_tags"])
        return Response({'message': '요약 없음 태그 저장', 'mood_tags': store.mood_tags}, status=200)

    # 텍스트 합쳐서 의미기반 무드 추출
    combined_text = " ".join(filter(None, [
        data.get("store_summary", ""),
        " ".join(data.get("ai_bullets", [])),
        " ".join(data.get("blog_keywords", [])),
    ]))

    tags = pick_mood_tags(combined_text, getattr(store, "category", None), top_k=5, mode="adj")
    store.mood_tags = tags if tags else ["무드정보부족"]

    # (선택) 모델에 store_summary 필드 있다면 같이 저장
    if hasattr(store, "store_summary"):
        store.store_summary = data.get("store_summary", "")
    
    store.save()
    return Response({
        'message': '무드 태그가 업데이트되었습니다.',
        'mood_tags': store.mood_tags,
        'store_summary': getattr(store, "store_summary", None),
        'ai_bullets': data.get("ai_bullets", []),
        'blog_keywords': data.get("blog_keywords", []),
    }, status=200)


# 챗봇 가게 추천 코드
def _parse_gemini_json(text: str):
    """Gemini가 JSON만 내도록 요청했지만 방어적으로 파싱."""
    try:
        start = text.rfind("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except Exception:
        return None

def _normalize_congestion(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"low", "medium", "high"}:
        return v
    return "medium"

def _tokenize_mood(text: str) -> List[str]:
    if not text:
        return []
    raw = text.replace(",", " ").split()
    return [t.strip() for t in raw if t.strip()]

def _mood_overlap_score(request_moods: List[str], store_moods: List[str]) -> float:
    if not request_moods or not store_moods:
        return 0.0
    # 가게 태그 정규화(공통 후행어 제거)
    CLEAN_SUFFIX = (" 분위기", " 무드", " 느낌", " 좌석", " 자리")
    sm = []
    for tag in store_moods:
        if not tag:
            continue
        x = tag.strip().lower()
        for suf in CLEAN_SUFFIX:
            if x.endswith(suf):
                x = x[: -len(suf)]
        sm.append(x)
    store_set = set(sm)

    exact = 0
    partial = 0

    for rq in request_moods:
        rq = rq.strip().lower()
        if not rq:
            continue

        # 1) 정확 일치
        if rq in store_set:
            exact += 1
            continue

        # 2) 부분 일치(요청 단어가 태그 안에 포함 / 태그가 요청 안에 포함)
        hit = False
        for tag in store_set:
            if rq in tag or tag in rq:
                partial += 1
                hit = True
                break
        if hit:
            continue

        # 3) 결합태그 헤드 일치 (예: "조용한 자리" vs "조용한")
        for tag in store_set:
            head = tag.split()[0]
            if head == rq:
                partial += 1
                break

    req_n = max(1, len(request_moods))
    # 정확 매치 1.0, 부분 매치 0.5 가중
    score = (exact + 0.5 * partial) / req_n
    # 0~1 범위 유지
    return max(0.0, min(1.0, score))

def _congestion_compat_score(request_level: str, store_level: str) -> float:
    order = {"low": 0, "medium": 1, "high": 2}
    r = order.get(request_level or "medium", 1)
    s = order.get((store_level or "medium").lower(), 1)
    # 요청보다 붐비지 않으면 가점, 한 단계 더 붐비면 감점
    diff = s - r
    if diff <= 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0

def _distance_score(meters: float, cutoff: float) -> float:
    if meters is None:
        return 0.5
    if meters >= cutoff:
        return 0.0
    return 1.0 - (meters / cutoff)

class RecommendStoreView(APIView):
    """
    POST /recommend/?lat=..&lng=..
    body: { "message": "조용하고 감성적인 카페 추천" }
    """
    def post(self, request):
        user_input = request.data.get("message", "")
        if not user_input:
            return Response({"error": "message가 필요합니다."}, status=status.HTTP_400_BAD_REQUEST)

        # 위치/반경 파라미터
        # ★ 위치/반경 파싱 (헤더/바디/기본값 폴백)
        # 반경 / 후보군 개수 고정값
        RADIUS_DEFAULT = 1200.0   # 1.2km
        TOPK_DEFAULT   = 5

        # === 현재 위치: 프론트가 쿼리 파라미터로 전달 (?lat=..&lng=..) ===
        try:
            lat = float(request.query_params.get("lat"))
            lng = float(request.query_params.get("lng"))
        except (TypeError, ValueError):
            # lat/lng가 없거나 잘못된 경우엔 기존 기본값/폴백
            lat, lng = read_coords_from_request(request)  # 동덕여대 기본 좌표 폴백
        
        radius = RADIUS_DEFAULT
        top_k = TOPK_DEFAULT

        # 1) Gemini로 의도 추출
        gemini_text = get_gemini_conditions(user_input)
        if gemini_text is None:
            return Response({"error": "Gemini API 호출 실패"}, status=500)

        # 우선 dict로 바로 떨어지는 신규 함수 사용
        parsed = extract_conditions(user_input)

        # 실패 시 기존 방식으로 폴백(문자열→수동 파싱)
        if not parsed:
            gemini_text = get_gemini_conditions(user_input)
            if gemini_text is None:
                return Response({"error": "Gemini API 호출 실패"}, status=500)
            parsed = _parse_gemini_json(gemini_text)

        # ★ 빠진 슬롯만 되묻기
        miss = missing_slots(parsed)
        if miss:
            return Response({
                "need_more": True,
                "missing": miss,
                "ask": follow_up_question(miss)
            }, status=200)

        req_mood_str = parsed.get("mood", "") or ""
        req_congestion = _normalize_congestion(parsed.get("congestion", "medium"))
        req_category = parsed.get("category")  # 예: cafe/korean/...

        req_moods = _tokenize_mood(req_mood_str)

        # 2) 1차 후보: 카테고리 우선 필터
        qs = Store.objects.all()
        if req_category:
            qs = qs.filter(category=req_category)

        # ============혼잡도 부분 변경됨============
        # # 3) 현재 혼잡도 반영 갱신(후보만)
        now = timezone.localtime()

        ai_level_map = {}  # store_id -> 'low'|'medium'|'high' (예외 시 medium)
        for s in qs.only("id", "congestion"):
            try:
                ai_level_map[s.id] = ensure_ai_congestion_now(s)  # 이 시점에 DB congestion도 최신화됨
            except Exception:
                ai_level_map[s.id] = s.congestion or "medium"

        # 4) 반경 필터 및 스코어링
        ranked = []
        for s in qs:
            # 거리
            d = None
            try:
                d = haversine(lat, lng, s.latitude, s.longitude)
            except Exception:
                d = None

            if d is not None and d > radius:
                continue  # 반경 밖 제외

            # ============혼잡도 부분 변경됨============
            # # 무드/혼잡도/거리 점수
            mood_sc = _mood_overlap_score(req_moods, s.mood_tags or [])

            # s.congestion 대신 방금 구한 AI 현재 레벨 사용
            store_level = ai_level_map.get(s.id, s.congestion or "medium")
            cong_sc = _congestion_compat_score(req_congestion, store_level)

            dist_sc = _distance_score(d, cutoff=radius)

            # 가중치(원하면 조절 가능)
            total = (mood_sc * 0.55) + (cong_sc * 0.25) + (dist_sc * 0.20)

            ranked.append((
                s,
                round(total, 6),
                {"mood": round(mood_sc, 6), "congestion": round(cong_sc, 6), "distance": round(dist_sc, 6)},
                d
            ))

        # 결과가 너무 없으면(0개) 카테고리만 맞춰 거리순 폴백
        if not ranked:
            backup = []
            for s in qs:
                d = None
                try:
                    d = haversine(lat, lng, s.latitude, s.longitude)
                except Exception:
                    d = float("inf")
                backup.append((s, 0.0, d if d is not None else float("inf")))
            backup.sort(key=lambda x: x[2])
            top = [t[0] for t in backup[:top_k]]

            # chat message (결과 없음일 때)
            chat_message = get_gemini_chat_reply(
                user_input=user_input,
                parsed=parsed,
                top1_name=top[0].name if top else None,
                top1_distance_m=(backup[0][1] if backup else None),
                top1_url=(top[0].kakao_url if top else None),
            ) or '조건에 맞는 결과가 적어 반경을 넓혀보겠솜! 가까운 순으로 보여줬솜!'

            
            if top:
                d0 = backup[0][1]
                dist_text = _meters_to_text(d0)
                name = top[0].name
                url = top[0].kakao_url or ""
                # 거리 말풍선
                chat_message = f'{dist_text} 정도에 "{name}"가 있솜!'
                # url이 있을 경우의 응답 메시지
                payload = {"chat_message": chat_message}
                if url:
                    payload["link_message"] = "링크로 바로 가보솜~"
                    payload["link_url"] = url
                return Response(payload)

            return Response({"chat_message": "조건에 맞는 결과가 적어 반경을 넓혀보겠솜!"})

        # 정상 매칭: 상위 정렬
        ranked.sort(key=lambda x: x[1], reverse=True)
        top1, _, _, top1_dist = ranked[0]
        if top1_dist is None:
            top1_dist = haversine(lat, lng, top1.latitude, top1.longitude)

        dist_text = _meters_to_text(top1_dist)
        name = top1.name
        url = top1.kakao_url or ""

        # 최종 메시지: 거리/가게명/URL 포함, '솜!' 톤 유지
        # 말풍선 1
        chat_message = f'{dist_text} 정도에 "{name}"가 있솜!'
        payload = {"chat_message": chat_message}
        # 말풍선 2 (URL이 있으면)
        if url:
            payload["link_message"] = "더 자세히 확인해보솜!"
            payload["link_url"] = url

        return Response(payload)

import random
### 챗봇을 시작할 때 질문하는 가이드 양식 보여주는 api
class RecommendGuideView(APIView):
    def get(self, request):
        example_messages = [
            "조용한 분위기의 감성적인 가게 추천해줘",
            "혼잡하지 않은 한식당이 좋아요",
            "데이트하기 좋은 장소 추천해줘",
            "북적이지 않는 바 조용히 술 마시고 싶어요",
            "카페인데 사람 너무 많은 건 피하고 싶어"
        ]
        random_example = random.choice(example_messages)

        return Response({
            "message": "아래 예시를 참고해서 솜봇에게 말을 걸어보세요!",
            "examples": random_example
        })
    
# 혼잡도 예측
@api_view(['GET'])
def forecast_store(request, store_id):
    store = get_object_or_404(Store, pk=store_id)

    raw = request.GET.get('minutes', '')
    if raw.strip():
        try:
            offsets = [int(x) for x in raw.split(',') if x.strip() != '']
        except ValueError:
            return Response({'error': 'minutes 파라미터는 정수 콤마 리스트만 가능'}, status=400)
    else:
        offsets = [0, 10, 20, 30, 60] # 기본값

    # data는 [{minutes_ahead, at, ai_level}, ...] 형태의 리스트
    data = forecast_congestion(store, offsets=offsets)
    return Response({
        'store_id': store.id,
        'generated_at': timezone.localtime().isoformat(),
        'items': data
    }, status=200)