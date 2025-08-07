import requests
from django.conf import settings

# 카카오 로컬 api 사용
KAKAO_API_KEY = settings.KAKAO_REST_API_KEY

# 동덕여대 위경도
lat = 37.606372
lng = 127.041772

def get_places(category_code, query='', radius=1000, lat=lat, lng=lng):
    url = 'https://dapi.kakao.com/v2/local/search/category.json'
    headers = {'Authorization': f'KakaoAK {KAKAO_API_KEY}'}
    params = {
        'category_group_code': category_code,
        'x': lng,   # 경도
        'y': lat,   # 위도
        'radius': radius,   # 2km = 도보 30분
        'size': 15, # 한 페이지 최대 15개(카카오 제한)
        'page': 1,
        'sort': 'distance'
    }

    places = []
    while True:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()
        places += data['documents']

        # 마지막 페이지까지 반복
        if len(data['documents']) < params['size']:
            break
        params['page'] += 1
        if params['page'] > 45: # 15개*45=675개, 카카오 최대
            break

    return places

# 모델에 맞게 카테고리 분류
def map_kakao_category(category_name):
    if '카페' in category_name or '제과' in category_name:
        return 'cafe'
    
    # 음식점 > 한식 > 육류,고기 -> 고깃집이 한식으로 분류되는 것 방지
    parts = [s.strip() for s in category_name.split('>')]
    if '한식' in parts:
        # '한식 > 육류,고기'면 parts = [..., '한식', '육류,고기']
        # 하위 카테고리가 3개 미만 → bbq
        if len(parts) == 3 and '육류,고기' in parts:
            return 'bbq'
        # '한식 > 육류,고기 > 닭요리' 등 하위가 3개 이상 → korean : 닭고기, 곱창 등은 고깃집으로 분류 x
        return 'korean'
    
    if '중식' in category_name:
        return 'chinese'
    if '일식' in category_name:
        return 'japanese'
    if '패스트푸드' in category_name or '치킨' in category_name:
        return 'fastfood'
    if '분식' in category_name:
        return 'bunsik'
    if '건강식' in category_name or '샐러드' in category_name:
        return 'healthy'
    if '양식' in category_name:
        return 'western'
    if '고기' in category_name or '갈비' in category_name or '겹살' in category_name:
        return 'bbq'
    if '술집' in category_name:
        return 'bar'
    return None
