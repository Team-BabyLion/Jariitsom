from typing import Optional, Tuple, Dict
import re, time
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

KOREAN_WEEKDAYS = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]

def _make_driver():
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--lang=ko-KR')
    return webdriver.Chrome(options=opts)

def build_maps_search_url(lat: float, lng: float, name: str) -> str:
    q = quote_plus(name.strip())
    return f"https://www.google.com/maps/search/{q}/@{lat},{lng},17z"

def _extract_hourly_percents(driver):
    # 막대: role="img" + aria-label에 "%"
    bars = driver.find_elements(By.CSS_SELECTOR, 'div[role="img"].dpoVLd')
    out = []
    for el in bars:
        label = el.get_attribute("aria-label") or ""
        m = re.search(r'(\d+)\s*%', label)
        if m:
            out.append(int(m.group(1)))
    return out[:24]

def _find_side_panel(driver):
    panels = driver.find_elements(By.CSS_SELECTOR, 'div.m6QErb.DxyBCb')
    if panels:
        return panels[0]
    panels = driver.find_elements(By.CSS_SELECTOR, 'div[role="region"]')
    return panels[0] if panels else None

def _scroll_until_populartimes(driver, panel, timeout=12):
    end = time.time() + timeout
    while time.time() < end:
        # 인기시간대 막대 존재?
        if driver.find_elements(By.CSS_SELECTOR, 'div[role="img"].dpoVLd'):
            return True
        # 없으면 패널/윈도우 스크롤
        if panel:
            driver.execute_script("arguments[0].scrollBy(0, 500);", panel)
        else:
            driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(0.25)
    return False

def _open_weekday_dropdown(driver) -> bool:
    # '인기 시간대' 섹션 근처의 드롭다운 버튼을 찾음
    # 버튼 텍스트가 요일(금요일 등)로 표시되는 케이스가 대부분
    try:
        # 섹션 스코프 내 첫 번째 버튼 시도
        btns = driver.find_elements(
            By.XPATH,
            "//div[contains(., '인기 시간대')]//following::button[1] | //button[contains(@aria-label,'요일')]"
        )
        for b in btns:
            if b.is_displayed():
                driver.execute_script("arguments[0].click();", b)
                time.sleep(0.2)
                return True
    except Exception:
        pass
    return False

def _select_weekday(driver, label_text: str) -> bool:
    # 펼쳐진 목록에서 텍스트가 '월요일' 같은 항목 클릭
    try:
        item = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//div[@role='menu' or @role='listbox']//div[normalize-space()='{label_text}'] | //li[normalize-space()='{label_text}']")
            )
        )
        driver.execute_script("arguments[0].click();", item)
        time.sleep(0.25)
        return True
    except Exception:
        return False

def crawl_popular_times_weekly_by_latlng_name(
    lat: float, lng: float, name: str
) -> Tuple[Optional[Dict], Optional[str]]:
    driver = _make_driver()
    place_url = None
    try:
        # 검색 결과 → 첫 카드 클릭
        driver.get(build_maps_search_url(lat, lng, name))
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a.hfpxzc, a[data-result-id]'))
        )
        time.sleep(0.4)
        cards = driver.find_elements(By.CSS_SELECTOR, 'a.hfpxzc') or driver.find_elements(By.CSS_SELECTOR, 'a[data-result-id]')
        if not cards:
            return None, None
        driver.execute_script("arguments[0].click();", cards[0])

        # 상세 패널 로딩
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'h1.DUwDvf'))
        )
        time.sleep(0.3)
        place_url = driver.current_url

        # 인기시간대 섹션 보일 때까지 스크롤
        panel = _find_side_panel(driver)
        if not _scroll_until_populartimes(driver, panel, timeout=12):
            return None, place_url

        # 드롭다운 열고 요일별 수집
        weekly: Dict[str, list] = {}
        if not _open_weekday_dropdown(driver):
            # 드롭다운이 없는 레이아웃이면, 현재 보이는 요일만이라도 수집
            arr = _extract_hourly_percents(driver)
            if arr:
                import datetime
                weekly[str(datetime.datetime.today().weekday())] = arr
            return (weekly if weekly else None), place_url

        for idx, day in enumerate(KOREAN_WEEKDAYS):
            if not _select_weekday(driver, day):
                continue
            # 요일 선택 후 막대 렌더 대기
            WebDriverWait(driver, 6).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[role="img"].dpoVLd'))
            )
            time.sleep(0.2)
            arr = _extract_hourly_percents(driver)
            if arr:
                weekly[str(idx)] = arr

            # 다음 요일을 위해 다시 드롭다운 열기(닫히는 레이아웃이 많음)
            _open_weekday_dropdown(driver)

        return (weekly if weekly else None), place_url
    except Exception:
        return None, place_url
    finally:
        driver.quit()
