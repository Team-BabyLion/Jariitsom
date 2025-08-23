from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time, math

# 위치/반경 파싱 유틸 (추가)
# ─────────────────────────────────────────────────────────────────
DEFAULT_LAT = 37.606372     # 동덕여대
DEFAULT_LNG = 127.041772

def safe_float(v, default=None):
    try:
        return float(v)
    except Exception:
        return default

def in_korea_bounds(lat: float, lng: float) -> bool:
    # 필요 시 조정 가능
    return (30.0 <= lat <= 45.0) and (120.0 <= lng <= 135.0)

def read_coords_from_request(request):
    """
    우선순위:
      1) 헤더 X-User-Lat / X-User-Lng
      2) JSON 바디 lat / lng
      3) 기본값 (동덕여대)
    """
    # 1) 헤더
    hdr_lat = safe_float(request.headers.get("X-User-Lat"), None)
    hdr_lng = safe_float(request.headers.get("X-User-Lng"), None)

    # 2) 바디(JSON)
    data = getattr(request, "data", {}) or {}
    body_lat = safe_float(data.get("lat"), None)
    body_lng = safe_float(data.get("lng"), None)

    lat = hdr_lat if hdr_lat is not None else (body_lat if body_lat is not None else DEFAULT_LAT)
    lng = hdr_lng if hdr_lng is not None else (body_lng if body_lng is not None else DEFAULT_LNG)

    # 좌표 검증 실패 시 기본값
    if (lat is None) or (lng is None) or (not in_korea_bounds(lat, lng)):
        lat, lng = DEFAULT_LAT, DEFAULT_LNG

    return lat, lng

def read_radius_topk(request, default_radius=1200.0, default_topk=5):
    data = getattr(request, "data", {}) or {}
    radius = safe_float(data.get("radius"), default_radius)
    try:
        top_k = int(data.get("top_k", default_topk))
    except Exception:
        top_k = default_topk
    return radius, top_k

# 하버사인: 두 지점의 거리 계산
def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return int(R * c)

WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']
def crawl_kakao_full_info_selenium(kakao_url):
    # 크롬 드라이버로 카카오맵 페이지 접속
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 창 안 띄움으로 실행
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(kakao_url)
    time.sleep(2.0)  # JS 렌더링 대기(2~4초 내에서 조절)

    # 현재 웹페이지를 BeautifulSoup로 파싱
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # 별점 추출
    rating = None
    star_tag = soup.find('span', class_='num_star')
    if star_tag:
        text = star_tag.text.strip() # strip: 공백, 개행 문자 등 모두 삭제
        rating = float(text) if text else None

    # 대표 사진 url 추출
    photo_url = None
    img_tag = soup.find('img', class_='img-thumb')
    if img_tag and img_tag.has_attr('src'):
        photo_url = img_tag['src']
        # //로 시작하면 https: 붙여서 절대 경로로 변환
        if photo_url.startswith("//"):
            photo_url = "https:" + photo_url

    # 요일별 영업/브레이크타임 추출 -> 딕셔너리로 저장
    business_hours = {}
    for line in soup.select('div.line_fold'):
        day_tag = line.find('span', class_='tit_fold')
        if not day_tag:
            continue
        day_text = day_tag.text.strip()
        day = day_text[0] if day_text[0] in WEEKDAYS else None
        if not day:
            continue
        time_tags = line.select('div.detail_fold > span.txt_detail')
        open_close, breaktime = None, None
        for t in time_tags:
            txt = t.text.strip()
            if '브레이크' in txt:
                breaktime = txt.replace('브레이크타임', '').strip()
            elif '휴무' in txt or '휴무일' in txt:
                open_close = '휴무'
            else:
                open_close = txt
        business_hours[day] = {
            'open_close': open_close,
            'breaktime': breaktime
        }
    # 월화수목금토일 순서로 재정렬
    business_hours = {day: business_hours.get(day, None) for day in WEEKDAYS}

    # 상위 5개 메뉴 이름, 가격 추출 -> 리스트로 저장
    menus = []
    menu_items = soup.select('ul.list_goods > li')
    for li in menu_items[:5]:  # 상위 5개만
        name_tag = li.find('strong', class_='tit_item')
        price_tag = li.find('p', class_='desc_item')
        name = name_tag.text.strip() if name_tag else None
        price = price_tag.text.strip() if price_tag else None
        if name and price:
            menus.append({'name': name, 'price': price})

    driver.quit() # 드라이버 종료
    # 딕셔너리 형태로 반환
    return {
        'rating': rating,
        'photo_url': photo_url,
        'business_hours': business_hours,
        'menus': menus
    }
