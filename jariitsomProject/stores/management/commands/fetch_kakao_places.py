import os
from django.core.management.base import BaseCommand
from stores.models import Store
from stores.apis import get_places, map_kakao_category
from dotenv import load_dotenv
from stores.utils import haversine

load_dotenv()

# 가게 탐색 중심점 정의
# 675개로는 데이터가 한정적이라 중심점 늘림
LOCATION_CONFIG = {
    '정문': {'lat': 37.60563, 'lng': 127.0414, 'field': 'main_gate_distance'},
    '후문': {'lat': 37.606351, 'lng': 127.044481, 'field': 'back_gate_distance'},
    '월곡역3출': {'lat': 37.60256, 'lng': 127.0416, 'field': None},
    '상월곡역1출': {'lat': 37.60586, 'lng': 127.0471, 'field': None},
    '오거리': {'lat': 37.60412, 'lng': 127.0425, 'field': None},
}
# 카테고리별
CATEGORY_MAP = {
    'cafe': 'CE7',
    'restaurant': 'FD6',
}


# 카카오 로컬 API 가게 정보 DB에 자동 저장, 갱신하는 커맨드
class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        # 중심점 좌표마다 반복
        for loc_name, loc_info in LOCATION_CONFIG.items():
            lat, lng = loc_info['lat'], loc_info['lng']
            field = loc_info['field']

            for category, code in CATEGORY_MAP.items():
                places = get_places(
                    category_code=code,
                    lat=lat,
                    lng=lng,
                    radius=1000
                )
                print(f"{loc_name} - {category}({code}): {len(places)}개 발견")

                for p in places:
                    cat = map_kakao_category(p['category_name'])
                    # 위도, 경도 float 변환
                    place_lat = float(p['y'])
                    place_lng = float(p['x'])
                    address = p.get('road_address_name') or p.get('address_name') or ''

                    # 중복 확인: 이름 + 위도 + 경도 조합
                    store, created = Store.objects.update_or_create(
                        name=p['place_name'],
                        latitude=place_lat,
                        longitude=place_lng,
                        defaults={
                            'category': cat,
                            'address': address,
                            # http -> https로 저장
                            'kakao_url': p['place_url'].replace('http://', 'https://', 1),
                            'rating': 0.0,     # 별점 기본값 -> 크롤링으로 변경
                            'photo': None,     # 사진 기본값 -> 크롤링으로 변경
                        }
                    )
                    # LOCATION_CONFIG 기반으로 '정문', '후문' 거리 모두 계산해서 넣기!
                    main_gate_info = LOCATION_CONFIG['정문']
                    back_gate_info = LOCATION_CONFIG['후문']

                    # 해당 장소가 정문/후문에서 얼마나 떨어져 있는지 계산
                    main_dist = haversine(main_gate_info['lat'], main_gate_info['lng'], place_lat, place_lng)
                    back_dist = haversine(back_gate_info['lat'], back_gate_info['lng'], place_lat, place_lng)

                    # 기존보다 더 가까운 거리거나 새로 생성되면 DB 업데이트
                    updated = False
                    if store.main_gate_distance == 0 or main_dist < store.main_gate_distance or created:
                        store.main_gate_distance = main_dist
                        updated = True
                    if store.back_gate_distance == 0 or back_dist < store.back_gate_distance or created:
                        store.back_gate_distance = back_dist
                        updated = True

                    if updated:
                        store.save()

                    # if created:
                    #     self.stdout.write(f"  [NEW] {store.name} 저장 완료")
                    # else:
                    #     self.stdout.write(f"  [SKIP] {store.name} 이미 존재")
