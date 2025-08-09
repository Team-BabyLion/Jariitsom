# stores/kakao_ai_crawl.py
import re, time
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1")

def extract_place_id(url: str):
    if not url: 
        return None
    m = re.search(r"place\.map\.kakao\.com/(\d+)", url)
    return m.group(1) if m else None

def crawl_kakao_ai_by_place_id(place_id: str):
    url = f"https://place.map.kakao.com/{place_id}"

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=390,844")
    options.add_argument(f"user-agent={MOBILE_UA}")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(1)

        # 블로그 요약 키워드
        blog_keywords = []
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.info_review")))
            soup = BeautifulSoup(driver.page_source, "html.parser")
            info_review = soup.select("div.info_review span.option_review")
            for opt in info_review:
                kw_el = opt.select_one('span[style*="white-space"]')
                if kw_el:
                    raw = kw_el.get_text(" ", strip=True)
                    parts = [p.strip() for p in raw.replace("·", ",").split(",") if p.strip()]
                    blog_keywords.extend(parts)
        except Exception:
            pass

        # AI 요약 펼치기 + 불릿
        store_summary, ai_bullets = "", []
        try:
            trigger = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a.link_ai")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", trigger)
            time.sleep(1.2)

            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.group_summary, div.info_ai"))
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
            desc = soup.select_one("div.group_summary p.desc_summary")
            if desc:
                store_summary = desc.get_text(" ", strip=True)
            bullet_tags = soup.select("div.info_ai span.txt_option")
            ai_bullets = [b.get_text(" ", strip=True) for b in bullet_tags if b.get_text(strip=True)]
        except Exception:
            soup = BeautifulSoup(driver.page_source, "html.parser")
            bullet_tags = soup.select("div.info_ai span.txt_option")
            ai_bullets = [b.get_text(" ", strip=True) for b in bullet_tags if b.get_text(strip=True)]

        return {
            "store_summary": store_summary,
            "ai_bullets": ai_bullets,
            "blog_keywords": blog_keywords,
        }

    except Exception as e:
        print("❌ 요약 정보 크롤링 실패:", e)
        try:
            with open(f"kakao_debug_{place_id}.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
        except Exception:
            pass
        return {}
    finally:
        driver.quit()
