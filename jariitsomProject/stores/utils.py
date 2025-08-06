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
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 창 띄우기 싫으면
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(kakao_url)
    time.sleep(2.5)  # JS 렌더링 대기 (네트워크 따라 2~4초로 조절)

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # 1. 별점
    rating = None
    star_tag = soup.find('span', class_='num_star')
    if star_tag:
        try:
            rating = float(star_tag.text.strip())
        except:
            rating = None

    # 2. 대표 사진
    photo_url = None
    img_tag = soup.find('img', class_='img-thumb')
    if img_tag and img_tag.has_attr('src'):
        photo_url = img_tag['src']
        if photo_url.startswith("//"):
            photo_url = "https:" + photo_url

    # 3. 요일별 영업/브레이크타임
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

    driver.quit()
    return {
        'rating': rating,
        'photo_url': photo_url,
        'business_hours': business_hours
    }
