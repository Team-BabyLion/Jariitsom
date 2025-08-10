from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time, math

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
