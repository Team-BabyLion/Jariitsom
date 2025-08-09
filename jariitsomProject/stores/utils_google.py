from typing import Optional, Tuple, Dict, List
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, re, urllib.parse

GOOGLE_MAPS_BASE = "https://www.google.com/maps"

# 크롬 드라이버 생성 함수
def _make_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,3600") # 인기 시간대가 기본 뷰에 들어오도록
    opts.add_argument("--lang=ko-KR") # 한국어로 강제(혹시 몰라서 추가)
    # (백업용) 브라우저 내부 배율
    opts.add_argument("--force-device-scale-factor=0.33")

    driver = webdriver.Chrome(options=opts)

    # 스크롤 없이 인기 섹션이 보이도록 CDP로 페이지 스케일과 뷰포트를 강제
    try:
        driver.execute_cdp_cmd("Emulation.setPageScaleFactor", {
            "pageScaleFactor": 0.33
        })
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": 1920,
            "height": 3600,
            "deviceScaleFactor": 1,
            "mobile": False
        })
    except Exception:
        pass

    return driver

# 구글맵에서 가게명+주소로 검색 후 열기
def _search_place_by_name_and_address(driver, name: str, address: str):
    # 검색 쿼리 구성 (가게명 + 주소)
    query = f"{name} {address}"
    search_url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}"
    
    # 검색 페이지 접속
    driver.get(search_url)
    time.sleep(1.2)

    # 1) 바로 상세로 랜딩되는 경우(url에 /maps/place/ 포함)
    try:
        WebDriverWait(driver, 3).until(EC.url_contains("/maps/place/"))
        return driver.current_url
    except Exception:
        pass

    # 2) 결과 목록이 뜨는 경우 -> 맨 위 결과 클릭해서 상세로 진입
    # 다양한  변형에 대비해 여러 셀렉터를 순차 시도
    selectors = [
        # 가장 안정적: 왼쪽 피드(목록) 안 첫 번째 place 링크
        (By.XPATH, "(//div[@role='feed']//a[contains(@href, '/maps/place/')])[1]"),
        # 피드가 없을 때: 모든 링크 중 첫 번째 place 링크
        (By.XPATH, "(//a[contains(@href, '/maps/place/')])[1]"),
        # 드물게 버튼 역할로 잡히는 카드
        (By.XPATH, "(//div[@role='article']//a[contains(@href, '/maps/place/')])[1]"),
    ]

    for by, sel in selectors:
        try:
            first_result = WebDriverWait(driver, 6).until(
                EC.element_to_be_clickable((by, sel))
            )
            # 클릭 씹힘 방지: JS 클릭
            driver.execute_script("arguments[0].click();", first_result)
            # URL이 상세로 바뀔 때까지 대기
            WebDriverWait(driver, 8).until(EC.url_contains("/maps/place/"))
            time.sleep(0.8)  # 패널/섹션 로딩 여유
            return driver.current_url
        except Exception:
            continue

    # 결과를 못 찾은 경우
    return None

# 인기 시간대 영역
# 인기 시간대 부분 찾기
def _find_popular_region(driver) -> Optional[object]:
    # 인기 시간대 h2를 찾기
    try:
        h2 = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, "//h2[normalize-space()='인기 시간대']"))
        )
    except Exception:
        return None

    # h2의 조상 중 role="region"인 컨테이너(그래프 포함) 찾기
    region = h2
    for _ in range(4): # 최대 4단계까지 올라가며 탐색
        try:
            region = region.find_element(By.XPATH, "./..")
        except Exception:
            break
        if region.get_attribute("role") == "region":
            return region
    return None 

# 요일 선택 드롭다운 열기
def _open_dropdown(region) -> bool:
    # btns: 리스트, region 영역 안쪽에서만 찾음, .//: 요소(region)의 모든 하위에서 찾음
    btns = region.find_elements(By.XPATH, ".//button[@aria-haspopup='menu' or contains(@class,'e2moi')]")
    if not btns:
        return False
    # region._parent: 웹드라이버, 드라이버에게 버튼 클릭 명령 -> js로 클릭(씹힘 방지)
    region._parent.execute_script("arguments[0].click();", btns[0])
    time.sleep(0.15)
    return True # 드롭다운 열기 성공

# 원하는 요일 클릭
def _select_weekday_in_open_menu(driver, label_ko: str) -> bool:
    try:
        item = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//div[@role='menu']//*[normalize-space()='{label_ko}']")
            )
        ) # 최대 5초 동안 메뉴 안에서 "월요일"(label_ko) 같은 요소가 나타나길 기다림
        driver.execute_script("arguments[0].click();", item)
        time.sleep(0.2)
        return True
    except Exception:
        return False

# 요일 변경 후 인기 시간대 그래프 뜰 때까지 대기
def _wait_visible_day_block(region) -> None:
    try:
        WebDriverWait(region._parent, 6).until(
            EC.presence_of_all_elements_located(
                (By.XPATH, ".//div[contains(@class,'g2BVhd') and not(@aria-hidden='true')]")
            )
        )
    except Exception:
        pass # 다음 단계에 안전장치가 하나 더 있음 -> 패스
    time.sleep(0.1)

# aria-label="오전/오후 n시에 붐비는 정도 n%"에서 시를 숫자로 변환
def _parse_hour_from_label(label: str) -> Optional[int]:
    match = re.search(r"(오전|오후)\s*(\d+)\s*시", label)
    if match:
        ap = match.group(1) # 오전 or 오후
        hh = int(match.group(2)) # 1~12시
        if ap == "오전": # 24시 형태로 변환, 오전 12시면 0시
            return 0 if hh == 12 else hh % 24
        return 12 if hh == 12 else (hh + 12) % 24
    return None

# 선택된 요일의 그래프를 읽어 24칸 배열로 반환
def _extract_current_day_24(region) -> List[int]:
    # 현재 보이는 요일 블록 찾기
    blocks = region.find_elements(
        By.XPATH,
        ".//div[contains(@class,'g2BVhd') and not(@aria-hidden='true')]"
    )
    if not blocks:
        return [0] * 24
    block = blocks[-1]  # 보이는 블록 하나 선택

    bars = block.find_elements(By.XPATH, ".//div[@role='img' and contains(@class,'dpoVLd')]")
    if not bars:
        return [0] * 24 # 막대 없으면 0으로 설정

    result = [0] * 24 # 배열 초기화
    # 각 막대에서 시간+퍼센트 추출
    for b in bars:
        label = b.get_attribute("aria-label") or ""
        m_pct = re.search(r"(\d+)\s*%", label)
        pct = int(m_pct.group(1)) if m_pct else 0
        hour = _parse_hour_from_label(label)
        if hour is not None:
            result[hour] = pct

    return result

# 다음 요일로 이동 클릭
def _go_next_day(region) -> bool:
    btns = region.find_elements(By.XPATH, ".//button[@aria-label='다음 날짜로 이동' or @aria-label='Next day']")
    if not btns:
        return False
    region._parent.execute_script("arguments[0].click();", btns[0])
    _wait_visible_day_block(region)
    return True

# 일주일 데이터 수집: 월요일 선택 후 화살표로 화~일 -> 딕셔너리 반환
def _collect_weekly_monday_then_next(driver, region) -> Dict[str, List[int]]:
    # 월요일을 기준점으로 선택
    if not _open_dropdown(region):
        return {}
    if not _select_weekday_in_open_menu(driver, "월요일"):
        return {}
    _wait_visible_day_block(region)

    weekly: Dict[str, List[int]] = {}
    # 월요일(0)
    weekly["0"] = _extract_current_day_24(region)
    # 오른쪽으로 6번 반복 -> 화(1)~일(6)
    for i in range(1, 7):
        if not _go_next_day(region):
            weekly[str(i)] = [0] * 24
            continue
        weekly[str(i)] = _extract_current_day_24(region)
    return weekly

# 전체 크롤링 함수
def crawl_popular_times_weekly_by_name_address(
    name: str, address: str, headless: bool = True
) -> Tuple[Optional[Dict[str, List[int]]], Optional[str]]:
    driver = _make_driver(headless=headless)
    place_url = None
    try:
        # 구글 지도 검색 후 url 생성, 접속(zoom: 적당히 근처가 보이게 설정)
        place_url = _search_place_by_name_and_address(driver, name, address)
        if not place_url:
            return None, None

        region = _find_popular_region(driver)
        if not region:
            return None, place_url

        weekly = _collect_weekly_monday_then_next(driver, region)
        if not weekly:
            return None, place_url

        # 혹시 누락될 경우 0으로 채움
        for i in range(7):
            weekly.setdefault(str(i), [0] * 24)
        return weekly, place_url # 일주일 데이터와 url 반환
    finally:
        driver.quit()
