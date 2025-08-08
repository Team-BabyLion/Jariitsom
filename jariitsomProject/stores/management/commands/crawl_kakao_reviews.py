from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from konlpy.tag import Okt
from stores.models import Store
from collections import Counter
import time

def extract_review_keywords(place_id, max_reviews=10):
    # 1. URL 세팅
    url = f"https://place.map.kakao.com/{place_id}"

    # 2. 셀레니움 드라이버 설정
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.get(url)
    
   # 4. 리뷰 섹션 대기 및 파싱
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "p.desc_review"))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # ✔ 리뷰 텍스트만 추출 (desc_review 태그 기준)
        review_tags = soup.select('p.desc_review')
        review_texts = [tag.get_text(strip=True) for tag in review_tags]

        if not review_texts:
            print("❌ 리뷰 텍스트가 없습니다.")
            driver.quit()
            return []

        # 5. 텍스트 합치기
        combined_text = ' '.join(review_texts)

        # 6. 자연어 분석 (명사, 형용사)
        okt = Okt()
        nouns = okt.nouns(combined_text)
        adjectives = [word for word, pos in okt.pos(combined_text) if pos == 'Adjective']

        driver.quit()
        return {
            "nouns": nouns,
            "adjectives": adjectives
        }

    except Exception as e:
        print("❌ 리뷰 섹션 처리 중 오류:", e)
        driver.quit()
        return []

# url에서 place_id 추출
def extract_place_id(url):
    if url and url.startswith("http://place.map.kakao.com/"):
        return url.split("/")[-1]
    return None

class Command(BaseCommand):
    help = "DB에 저장된 모든 가게의 카카오 URL을 기반으로 리뷰 크롤링 및 mood_tags 업데이트"

    def handle(self, *args, **options):
        stores = Store.objects.exclude(kakao_url__isnull=True).exclude(kakao_url='')

        for store in stores:
            place_id = extract_place_id(store.kakao_url)
            if not place_id:
                self.stdout.write(self.style.ERROR(f"[{store.name}] place_id 추출 실패"))
                continue

            result = extract_review_keywords(place_id)
            # 1. 기존 크롤링 결과 받아오기
            result = extract_review_keywords(place_id)

            # 2. 리뷰 없을 경우 처리
            if not result or not result.get("adjectives"):
                store.mood_tags = ["리뷰 없음"]
                store.save()
                self.stdout.write(self.style.WARNING(f"[{store.name}] 리뷰 없음 태그 저장"))
                continue

            # 3. 불용어 및 짧은 형용사 필터링
            stopwords = ['좋다', '괜찮다', '별로다', '같다', '있다', '없다', '이다', '정도']  # 필요시 더 추가
            filtered_adjs = [adj for adj in result['adjectives'] if len(adj) > 1 and adj not in stopwords]

            # 4. 등장 횟수 기준으로 정렬
            from collections import Counter
            top_adjs = [word for word, _ in Counter(filtered_adjs).most_common(5)]

            # 5. 저장
            store.mood_tags = top_adjs if top_adjs else ["리뷰 없음"]
            store.save()
            self.stdout.write(self.style.SUCCESS(f"[{store.name}] mood_tags 업데이트 완료 (형용사만): {store.mood_tags}"))