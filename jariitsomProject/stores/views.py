import json
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Store, Bookmark, VisitLog
from .serializers import VisitLogSerializer, BookmarkSerializer
from .serializers import StoreSerializer
from rest_framework.viewsets import ModelViewSet
from django.db.models import F, Case, When, Value
from rest_framework import filters
from .apis import get_places
from .apis import get_gemini_conditions
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import permission_classes
from .utils import haversine

class StoreViewSet(ModelViewSet):
    queryset = Store.objects.all()
    serializer_class = StoreSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request  # context에 request를 추가함
        return context

    def get_queryset(self):
        queryset = Store.objects.all() # 여기에 한 번 더 선언 해줘야 됨
        
        category = self.request.query_params.get('category')
        user_lat = self.request.query_params.get('user_lat')
        user_lng = self.request.query_params.get('user_lng')
        bookmarked = self.request.query_params.get('bookmarked')

        if category is not None:
            queryset = queryset.filter(category=category)
            # 왼쪽 카테고리는 필드 이름(인자명), 오른쪽 카테고리는 쿼리스트링에서 받아온 값(변수)
            # 변수명 헷갈리면 바꾸기
            # 조건이 대체 되는 게 아닌 누적 되는 식으로 작동함

        # 사용자의 현재 위치 파라미터가 있을 때만 거리 계산/정렬
        if user_lat and user_lng:
            user_lat, user_lng = float(user_lat), float(user_lng)
            for store in queryset:
                store._user_distance = haversine(user_lat, user_lng, store.latitude, store.longitude)
            ordering = self.request.query_params.get('ordering')
            if ordering == 'distance':
                queryset = sorted(queryset, key=lambda s: getattr(s, '_user_distance', 1e10))

        if bookmarked == 'true':
            queryset = queryset.filter(bookmarked_by__user=self.request.user)
            # 이 store를 즐겨찾기한 사용자 중 현재 로그인한 사용자가 있는지 역참조

        # 여유로운순 정렬을 위한 인구 비율 계산
        # .annotate(): 기존 Store 객체들 각각에 새 필드(population_ratio)를 붙이는 역할
        queryset = queryset.annotate(
            # annotate 안은 Django ORM의 SQL 연산 표현식 공간 -> if문 못 씀 -> Case, When 사용
            population_ratio = Case(
                # 0 나눗셈 방지용 -> 만약 최대 수용 인원이 0일 때 혼잡도 최대(1.0)으로 둠
                When(max_customers = 0, then = Value(1.0)),
                # F(): 모델 필드를 참조하는 객체, * 1.0은 정수 나눗셈 방지용
                default = F('current_customers') * 1.0 / F('max_customers')
            )
        )

        return queryset
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['user_lat'] = self.request.query_params.get('user_lat')
        context['user_lng'] = self.request.query_params.get('user_lng')
        return context
    
    # 필터(filters.~ 따로 선언하면 덮어씌워짐)
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'menus']
    ordering_fields = ['rating', 'population_ratio']
    
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

# 손님 방문 기록 작성하기
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_visit_log(request, store_id):
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return Response({'error': '가게 정보를 찾을 수 없습니다.'}, status=404)

    data = request.data.copy()
    data['store'] = store.id
    serializer = VisitLogSerializer(data=data)
    if serializer.is_valid():
        serializer.save(user=request.user)
        return Response(serializer.data, status=201)
    return Response(serializer.errors, status=400)

# 손님 방문 기록 조회 (가장 최근 방문 정보 1건)
@api_view(['GET'])
def get_latest_visit_log(request, store_id):
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return Response({'error': '가게 정보를 찾을 수 없습니다.'}, status=404)

    latest_log = store.visit_logs.order_by('-created_at').first()
    if not latest_log:
        return Response({'message': '아직 한번도 방문하지 않은 가게입니다.'}, status=204)

    serializer = VisitLogSerializer(latest_log)
    return Response(serializer.data, status=200)

# 챗봇 가게 추천 api
class RecommendStoreView(APIView):
    def post(self, request):
        user_input = request.data.get('message', '')
        if not user_input:
            return Response({"error": "입력값이 없습니다."}, status=status.HTTP_400_BAD_REQUEST)

        gemini_response = get_gemini_conditions(user_input)
        if gemini_response is None:
            return Response({"error": "Gemini API 호출 실패"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            parsed = json.loads(gemini_response)
            mood = parsed.get("mood")
            congestion = parsed.get("congestion")
            category = parsed.get("category")
        except json.JSONDecodeError:
            return Response({"error": f"Gemini 응답 파싱 실패: {gemini_response}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 필터링된 가게 목록
        stores = Store.objects.filter(
            mood_tags__contains=[mood],
            congestion=congestion,
            category=category
        )
        serializer = StoreSerializer(stores, many=True, context={'request': request})
        return Response({"results": serializer.data}, status=status.HTTP_200_OK)

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
        return Response({
            "message": "아래 예시를 참고해서 자연스럽게 입력해 주세요.",
            "examples": example_messages
        })