from django.urls import path, include
from rest_framework.routers import SimpleRouter
from .views import StoreViewSet
from .views import RecommendStoreView, RecommendGuideView
from .views import toggle_bookmark, list_bookmarks
from .views import create_visit_log, get_visit_logs
from .views import update_mood_tags
from .views import forecast_store

store_router = SimpleRouter()
store_router.register('stores', StoreViewSet)

urlpatterns = [
    path('', include(store_router.urls)),

    # 즐겨찾기
    path('bookmarks/', list_bookmarks, name='list_bookmarks'),
    path('stores/<int:store_id>/bookmark/', toggle_bookmark, name='toggle_bookmark'),
    path('stores/<int:store_id>/refresh-mood-tags/', update_mood_tags, name='update_mood_tags'),

    # 손님 방문기록
    path('stores/<int:store_id>/visitlogs/', create_visit_log, name='create_visit_log'),
    path('stores/<int:store_id>/visitlogs/list/', get_visit_logs, name='get_visit_logs'),

    # 챗봇 가게(카페, 음식점) 추천
    path('recommend/', RecommendStoreView.as_view(), name='recommend-store'),
    path('recommend/guide/', RecommendGuideView.as_view(), name='recommend-guide'),

    # 혼잡도 예측
    path('stores/<int:store_id>/forecast/', forecast_store, name='forecast-store'),
]