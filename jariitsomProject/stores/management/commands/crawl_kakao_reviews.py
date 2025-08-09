# stores/management/commands/crawl_kakao_reviews.py

from django.core.management.base import BaseCommand
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from konlpy.tag import Okt
from stores.models import Store
from collections import Counter, defaultdict
import time, re

EMOJI_RE = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)

# -----------------------------
# 구성 옵션
# -----------------------------
TOP_K = 5
TAG_MODE = "adj"          # "adj" | "adj_anchor"  (adj_anchor면 '조용한 분위기' 같은 결합 태그도 가능)
NEG_WINDOW = 5            # 부정어 탐지 윈도우
PROX_NEAR = 2             # 앵커 근접 거리(강)
PROX_MID = 5              # 앵커 근접 거리(중)

OKT = Okt()

# 공통 앵커(무드와 직결되는 명사)
ANCHORS_COMMON = {
    "분위기","인테리어","공간","좌석","자리","소음","음악","조명","테이블","내부","감성","동선","쾌적","청결","위생","컨센트","콘센트"
}

# 카테고리별 앵커(필요 시 계속 확장)
ANCHORS_BY_CATEGORY = {
    "cafe": ANCHORS_COMMON | {"공부","작업","좌석","콘센트","테이블","창가","채광","조용","향","베이커리"},
    "bar": ANCHORS_COMMON | {"조명","음악","시끄러움","좌석","테이블","분위기"},
    "korean": ANCHORS_COMMON | {"좌석","소음","청결","위생","테이블"},
    "japanese": ANCHORS_COMMON | {"좌석","청결","테이블"},
    "chinese": ANCHORS_COMMON | {"좌석","소음","위생"},
    "western": ANCHORS_COMMON | {"좌석","청결","인테리어"},
    "fastfood": ANCHORS_COMMON | {"좌석","소음"},
    "bunsik": ANCHORS_COMMON | {"좌석","소음"},
    "healthy": ANCHORS_COMMON | {"좌석","청결","인테리어"},
    "bbq": ANCHORS_COMMON | {"좌석","소음","환기","냄새","연기"},
}

# 긍/부정(간단 사전) — 필요 시 확장
POS_WORDS = {
    "조용하다","차분하다","아늑하다","깔끔하다","정갈하다","쾌적하다","편하다","안락하다",
    "아름답다","예쁘다","세련되다","모던하다","따뜻하다","밝다","넓다","고즈넉하다","은은하다","시원하다"
}
NEG_WORDS = {
    "시끄럽다","답답하다","지저분하다","복잡하다","좁다","불편하다","어둡다","침침하다","냄새나다","미지근하다","텁텁하다"
}
NEGATIONS = {"안","못","별로","전혀","아니","없","노","no","No","않"}

# 동의어/표기 정규화
NORMALIZE = {
    "정갈하다":"깔끔하다",
    "모던하다":"세련되다",
    "빈티지하다":"레트로하다",
    "포근하다":"아늑하다",
    "안락하다":"아늑하다",
    "환하다":"밝다",
    "조용조용하다":"조용하다",
    "청결하다":"깔끔하다",
}

# 강조/약화 부사
INTENSIFIERS = {"아주","매우","정말","진짜","너무","굉장히","꽤","상당히","되게"}
DIMINISHERS = {"좀","약간","조금","살짝"}

# 불용어
STOPWORDS = {
    # 서술어·형태소 잔재
    "이다", "하다", "되다", "있다", "없다", "같다", "되겠다", "가능하다",
    "아니다", "않다", "어떻다", "그렇다", "이렇다", "저렇다", "되었다", "되어있다",
    "되어다", "되어서", "되어", "되서", "됐", "됐다",

    # 평가 의미 없는 일반 형용사
    "많다", "적다", "크다", "작다", "높다", "낮다", "길다", "짧다", "빠르다", "느리다",
    "가깝다", "멀다", "새롭다", "오래되다",

    # 빈도 높은 보편적 형용사 (리뷰 무드에 기여 적음)
    "좋다", "괜찮다", "별로다", "나쁘다", "최고다", "맛있다", "맛없다", "재미있다",
    "재밌다", "재미없다", "싫다", "편하다", "불편하다", "쉽다", "어렵다",

    # 접속·관계 표현
    "그리고", "하지만", "그러나", "또한", "그래서", "그러므로", "때문에", "때문",
    "아마", "혹시", "만약", "이런", "저런", "그런", "이렇게", "저렇게", "그렇게",

    # 조사·감탄사·형태 잔재
    "요", "네", "음", "아", "오", "응", "야", "흠", "우와", "와", "허", "헉", "이야"
}

def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def split_sentences(text: str):
    text = normalize_text(text)
    # 간단 문장 분리: 종결/서술(~다/~요/문장부호)
    return [s.strip() for s in re.split(r"(?<=[\.!\?]|요|다)\s+", text) if s.strip()]

def tokens_with_pos(sentence: str):
    # 원형화(stem=True): '깔끔했어요' -> '깔끔하다'
    return OKT.pos(sentence, stem=True)

def adjective_pretty(adj: str) -> str:
    # '깔끔하다' -> '깔끔한' 표기
    if adj.endswith("하다"):
        return adj[:-2] + "한"
    return adj

def build_anchor_set(category: str):
    base = set(ANCHORS_COMMON)
    if category and category in ANCHORS_BY_CATEGORY:
        base |= ANCHORS_BY_CATEGORY[category]
    return base

def score_mood_words(text: str, category: str):
    """
    문장을 돌며 형용사/묘사 명사를 후보로 삼아 점수화.
    - 앵커 근접 가중치
    - 부정어 반전
    - 강조/약화 부사 가중치
    - 동의어 정규화
    - n-gram(형용사+앵커) 후보 가산
    """
    anchors = build_anchor_set(category)
    candidates = Counter()
    pair_candidates = Counter()  # adj+anchor n-gram

    for sent in split_sentences(text):
        morphs = tokens_with_pos(sent)  # [(word, tag)]
        tokens_only = [w for w,_ in morphs]
        # 앵커 위치들
        anchor_idx = [i for i,(w,t) in enumerate(morphs) if (t in {"Noun","Adjective"} and w in anchors)]

        # 강조/약화 부사 인덱스
        intens = {i for i,(w,t) in enumerate(morphs) if t=="Adverb" and w in INTENSIFIERS}
        dimin  = {i for i,(w,t) in enumerate(morphs) if t=="Adverb" and w in DIMINISHERS}

        for i, (w, t) in enumerate(morphs):
            cand = None
            if t == "Adjective":
                cand = w
            elif t == "Noun" and w.endswith(("함","감","미")) and len(w) > 1:
                # 아늑함/정갈함/쾌적함 등 -> 아늑하다
                cand = w[:-1] + "하다"
            if not cand:
                continue

            cand = NORMALIZE.get(cand, cand)

            # base polarity
            base = 0.0
            if cand in POS_WORDS:
                base += 1.0
            elif cand in NEG_WORDS:
                base -= 1.0
            else:
                base += 0.25  # 사전 밖이면 소폭 후보 가점

            # 강조/약화 가중치
            weight = 1.0
            if (i-1) in intens or (i-2) in intens:
                weight *= 1.2
            if (i-1) in dimin or (i-2) in dimin:
                weight *= 0.85

            # 앵커 근접 가중치
            prox_bonus = 0.0
            if anchor_idx:
                dist = min(abs(i - a) for a in anchor_idx)
                if dist <= PROX_NEAR:
                    prox_bonus += 1.0
                elif dist <= PROX_MID:
                    prox_bonus += 0.5

            # 부정어 근접 반전
            start = max(0, i - NEG_WINDOW)
            ctx = {w for w,_ in morphs[start:i]}
            polarity = -1.0 if ctx & NEGATIONS else 1.0

            score = (base + prox_bonus) * weight * polarity

            # 너무 부정적이면 태그 후보에서 제외(무드에선 부정 성향 제외)
            if score >= -0.2:
                candidates[cand] += score

            # n-gram: 가까운 앵커를 하나 골라 결합 후보 가산
            if anchor_idx:
                nearest = min(anchor_idx, key=lambda a: abs(i-a))
                if abs(nearest - i) <= PROX_MID:
                    pair = f"{adjective_pretty(cand)} {tokens_only[nearest]}"
                    pair_candidates[pair] += max(0.1, score)

    return candidates, pair_candidates

def pick_tags(text: str, category: str, top_k=TOP_K, mode=TAG_MODE):
    text = normalize_text(text)
    if not text:
        return []

    cand_adj, cand_pairs = score_mood_words(text, category)

    # 형용사 표기 prettify & 동의어 정규화된 상태 유지
    pretties = Counter()
    for adj, sc in cand_adj.items():
        pretties[adjective_pretty(adj)] += sc

    # 상위 후보 뽑기
    top_adj = [w for w,_ in pretties.most_common(20)]
    top_pairs = [w for w,_ in cand_pairs.most_common(20)]

    # 최종 태그 선택
    final = []
    if mode == "adj_anchor":
        pool = top_pairs + top_adj  # 결합 태그 우선
    else:
        pool = top_adj + top_pairs  # 형용사 우선

    seen = set()
    for w in pool:
        w = w.strip()
        if len(w) < 2:
            continue
        if w in seen:
            continue
        if w in STOPWORDS:
            continue
        seen.add(w)
        final.append(w)
        if len(final) == top_k:
            break

    return final

#### AI 요약 없는 가게들 후기 크롤링
def clean_text(s: str) -> str:
    s = s or ""
    s = EMOJI_RE.sub("", s)                 # 이모지 제거
    s = s.replace("\u200b", "").strip()     # zero-width 제거
    return re.sub(r"\s+", " ", s)

def collect_review_texts(driver, max_reviews=60, max_round=6):
    """모바일 뷰에서 리뷰 본문만 수집(p.desc_review). 스크롤로 더 로드."""
    collected = []
    seen = set()
    for r in range(max_round):
        # 스크롤 조금씩 내려서 lazy-load 유도
        driver.execute_script("window.scrollBy(0, document.body.scrollHeight*0.6);")
        time.sleep(1.2)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # '더보기' 버튼 텍스트는 제거
        for btn in soup.select("p.desc_review span.btn_more"):
            btn.extract()

        for p in soup.select("p.desc_review"):
            t = clean_text(p.get_text(" ", strip=True))
            if not t or t in seen:
                continue
            seen.add(t)
            collected.append(t)
            if len(collected) >= max_reviews:
                return collected
    return collected

def extract_review_keywords(place_id):
    url = f"https://place.map.kakao.com/{place_id}"

    mobile_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1"
    )
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=390,844")  # 모바일 뷰
    options.add_argument(f"user-agent={mobile_ua}")

    driver = webdriver.Chrome(options=options)
    driver.get(url)

    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
        time.sleep(1)

        # 블로그 AI 요약 키워드
        blog_keywords = []
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.info_review"))
            )
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        info_review = soup.select("div.info_review span.option_review")
        for opt in info_review:
            kw_el = opt.select_one('span[style*="white-space"]')
            if kw_el:
                raw = kw_el.get_text(" ", strip=True)
                parts = [p.strip() for p in raw.replace("·", ",").split(",") if p.strip()]
                blog_keywords.extend(parts)

        # AI 요약 패널 열기
        store_summary = ""
        ai_bullets = []
        try:
            trigger = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.link_ai"))
            )
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

        # === 폴백: 리뷰 본문 긁기 ===
        raw_reviews = collect_review_texts(driver, max_reviews=80, max_round=8)

        return {
            "store_summary": store_summary,
            "ai_bullets": ai_bullets,
            "blog_keywords": blog_keywords,
            "raw_reviews": raw_reviews,
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

# url에서 place_id 추출 (http/https 모두 대응)
def extract_place_id(url):
    if not url:
        return None
    m = re.search(r"place\.map\.kakao\.com/(\d+)", url)
    return m.group(1) if m else None

class Command(BaseCommand):
    help = "DB에 저장된 모든 가게의 카카오 URL을 기반으로 리뷰 크롤링 및 mood_tags 업데이트(정확도 향상 버전)"

    def handle(self, *args, **options):
        stores = Store.objects.exclude(kakao_url__isnull=True).exclude(kakao_url='')

        for store in stores:
            place_id = extract_place_id(store.kakao_url)
            if not place_id:
                self.stdout.write(self.style.ERROR(f"[{store.name}] place_id 추출 실패"))
                continue

            result = extract_review_keywords(place_id)
            if not result:
                store.mood_tags = ["요약 없음"]
                store.save()
                self.stdout.write(self.style.WARNING(f"[{store.name}] 요약 없음 태그 저장"))
                continue

            # 텍스트 결합: AI요약/불릿/블로그키워드 + 리뷰본문
            combined_bits = []
            if result.get("store_summary"):
                combined_bits.append(result["store_summary"])
            if result.get("ai_bullets"):
                combined_bits.append(" ".join(result["ai_bullets"]))
            if result.get("blog_keywords"):
                combined_bits.append(" ".join(result["blog_keywords"]))
            if result.get("raw_reviews"):
                combined_bits.append(" ".join(result["raw_reviews"]))

            combined_text = " ".join(filter(None, combined_bits)).strip()

            if not combined_text:
                store.mood_tags = ["요약 없음"]
                store.save()
                self.stdout.write(self.style.WARNING(f"[{store.name}] 요약/리뷰 모두 없음"))
                continue

            tags = pick_tags(combined_text, getattr(store, "category", None), top_k=TOP_K, mode=TAG_MODE)
            store.mood_tags = tags if tags else ["무드정보부족"]
            store.save()

            src = "AI+리뷰" if result.get("store_summary") or result.get("ai_bullets") or result.get("blog_keywords") else "리뷰"
            self.stdout.write(self.style.SUCCESS(
                f"[{store.name}] ({src}) mood_tags 업데이트: {store.mood_tags}"
            ))