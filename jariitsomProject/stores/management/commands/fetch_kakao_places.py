import os
from django.core.management.base import BaseCommand
from stores.models import Store
from stores.apis import get_places, map_kakao_category
from dotenv import load_dotenv

load_dotenv()

# 카카오 로컬 API 가게 정보 DB에 자동 저장, 갱신하는 커맨드
class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        # 675개로는 데이터가 한정적이라 중심점 늘림
        locations = [
            {'name': '정문', 'lat': 37.60563, 'lng': 127.0414},
            {'name': '후문', 'lat': 37.606351, 'lng': 127.044481},
            {'name': '월곡역3출', 'lat': 37.60256, 'lng': 127.0416},
            {'name': '상월곡역1출', 'lat': 37.60586, 'lng': 127.0471},
            {'name': '오거리', 'lat': 37.60412, 'lng': 127.0425},
        ]
        # 카테고리별
        category_map = {
            'cafe': 'CE7',
            'restaurant': 'FD6',
        }

        for location in locations:
            for category, code in category_map.items():
                places = get_places(
                    category_code=code,
                    lat=location['lat'],
                    lng=location['lng'],
                    radius=800
                )
                print(f"{location['name']} - {category}({code}): {len(places)}개 발견")

                for p in places:
                    category = map_kakao_category(p['category_name'])
                    # 위도, 경도 float 변환
                    lat = float(p['y'])
                    lng = float(p['x'])

                    # 중복 확인: 이름 + 위도 + 경도 조합
                    store, created = Store.objects.update_or_create(
                        name=p['place_name'],
                        latitude=lat,
                        longitude=lng,
                        defaults={
                            'category': category,
                            'latitude': float(p['y']),
                            'longitude': float(p['x']),
                            'kakao_url': p['place_url'],
                            'rating': 0.0,     # 추후 크롤링으로 변경
                            'photo': None,     # 추후 크롤링으로 추가
                        }
                    )
                    if created:
                        self.stdout.write(f"  [NEW] {store.name} 저장 완료")
                    else:
                        self.stdout.write(f"  [SKIP] {store.name} 이미 존재")
