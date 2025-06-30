from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import StoreViewSet
from .views import get_store_congestion, update_store_congestion
from .views import toggle_bookmark, list_bookmarks
from .views import create_visit_log, get_latest_visit_log

store_router = SimpleRouter()
store_router.register('stores', StoreViewSet)

urlpatterns = [
    path('', include(store_router.urls)),

    # 혼잡도 조회
    path('stores/<int:store_id>/congestion/', get_store_congestion, name='get_store_congestion'),
    # 혼잡도 업데이트
        # api/를 붙여도되고 안붙여도 되는데 해커톤이나 빠른 개발용이면 보통 안붙임.
        # 붙이는 경우는 이후에 웹페이지용과 API용 URL이 불분명해져서 붙이는 것임.
        # 지금은 안붙이겠음!
    path('stores/<int:store_id>/update_congestion/', update_store_congestion, name='api_update_congestion'),

    # 즐겨찾기
    path('bookmarks/', list_bookmarks, name='list_bookmarks'),
    path('stores/<int:store_id>/bookmark/', toggle_bookmark, name='toggle_bookmark'),
    
    # 손님 방문기록
    path('stores/<int:store_id>/visit/', create_visit_log, name='create_visit_log'),
    path('stores/<int:store_id>/visit/latest/', get_latest_visit_log, name='get_latest_visit_log'),
]