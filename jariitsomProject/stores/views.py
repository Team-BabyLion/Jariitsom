from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Store, Bookmark, VisitLog
from .serializers import VisitLogSerializer, BookmarkSerializer
from .serializers import StoreSerializer, StoreCongestionSerializer
from rest_framework.viewsets import ModelViewSet
from django.db.models import F, Case, When, Value
from rest_framework import filters

# api view를 통해 혼잡도 입력부분 구현
### 현재 손님 수만 입력하면 알아서 혼잡도의 정도를 정해서 db에 해당 내용 저장
@api_view(['POST'])
def update_store_congestion(request, store_id):
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return Response({'error': '가게를 찾을 수 없습니다.'}, status=status.HTTP_404_NOT_FOUND)
    
    # 현재 손님 수를 필수 입력 필드로 지정 -> 입력 안하면 err 생성
    current_customers = request.data.get('current_customers')
    
    # 값이 비었거나 None이면 에러
    if current_customers is None or str(current_customers).strip() == '':
        return Response({'error': 'current_customers 값이 필요합니다.'}, status=status.HTTP_400_BAD_REQUEST)

    # 정수로 변환 시도
    try:
        current_customers = int(current_customers)
    except ValueError:
        return Response({'error': 'current_customers는 정수여야 합니다.'}, status=status.HTTP_400_BAD_REQUEST)

    # 음수 값은 허용하지 않음
    if current_customers < 0:
        return Response({'error': 'current_customers는 0 이상의 정수여야 합니다.'}, status=status.HTTP_400_BAD_REQUEST)

    # 최대 손님 수가 입력 안되어있다면 에러 생성
        # 근데 이건 우리가 직접 db에 입력하는거라면 굳이 싶긴한데 그래도 넣는게 안전할 듯
    max_customers = store.max_customers
    if max_customers <= 0:
        return Response({'error': 'max_customers 값이 설정되어 있지 않거나 0입니다.'}, status=status.HTTP_400_BAD_REQUEST)

    # 현재 인원수가 최대 수용 인원보다 크다면 에러 생성
    if current_customers > max_customers:
        return Response({'error': 'current_customers가 max_customers보다 클 수 없습니다.'}, status=status.HTTP_400_BAD_REQUEST)


    # 혼잡도 계산
    ratio = current_customers / store.max_customers
    if ratio < 0.25:
        congestion = 'low'
    elif ratio < 0.75:
        congestion = 'medium'
    else:
        congestion = 'high'

    # serializer 입력용의 데이터 딕셔너리 구성
    data = {
        'current_customers': current_customers,
        'congestion': congestion
    }

    serializer = StoreCongestionSerializer(store, data=data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# 가게 혼잡도 정보 조회
@api_view(['GET'])
def get_store_congestion(request, store_id):
    try:
        store = Store.objects.get(id=store_id)
    except Store.DoesNotExist:
        return Response({'error': '가게를 찾을 수 없습니다.'}, status=404)

    serializer = StoreSerializer(store, context={'request': request})
    return Response(serializer.data, status=status.HTTP_200_OK)

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
        subcategory = self.request.query_params.get('subcategory')
        bookmarked = self.request.query_params.get('bookmarked')

        if category is not None:
            queryset = queryset.filter(category=category)
            # 왼쪽 카테고리는 필드 이름(인자명), 오른쪽 카테고리는 쿼리스트링에서 받아온 값(변수)
            # 변수명 헷갈리면 바꾸기
        if subcategory is not None:
            queryset = queryset.filter(subcategory=subcategory)
            # 조건이 대체 되는 게 아닌 누적 되는 식으로 작동함

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
    
    # 필터(filters.~ 따로 선언하면 덮어씌워짐)
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['rating', 'population_ratio']
    
# 클릭할 때마다 즐겨찾기 추가, 삭제
@api_view(['POST'])
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
def list_bookmarks(request):
    user = request.user
    bookmarks = Bookmark.objects.filter(user=user).select_related('store')
    # 해당 사용자가 북마크한 가게 목록을 가져옴과 동시에 store 정보까지 가져옴
    serializer = BookmarkSerializer(bookmarks, many=True, context={'request':request})
    return Response(serializer.data)

# 손님 방문 기록 작성하기
@api_view(['POST'])
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