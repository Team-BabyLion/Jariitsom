import os
import json, math, requests
import google.generativeai as genai ### gemini 사용하기 위해 import
from dotenv import load_dotenv

from stores.models import Store

CATEGORIES = [c[0] for c in Store.CATEGORY_CHOICES]
CONGESTIONS = [c[0] for c in Store.CONGESTION_CHOICES]

# ================= 환경 변수 로딩 & Gemini 초기화 ===============
load_dotenv()

# 카카오 로컬 api 사용
KAKAO_API_KEY = os.getenv("KAKAO_REST_API_KEY")

# GEMINI API 사용
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

def get_gemini_conditions(user_input):
    prompt = f"""
    사용자의 장소 추천 요청에서 다음 세 가지 정보를 추출해서 JSON으로 응답해 줘.

    1. mood: 사용자가 원하는 분위기 (예: "조용한", "감성적인", "활기찬" 등 자연어 그대로)
    2. congestion: 혼잡도. 반드시 다음 3개 중 하나로 응답해 → "low", "medium", "high"
    3. category: 장소의 카테고리. 아래 중 하나로만 응답해:
       ["cafe", "korean", "chinese", "japanese", "fastfood", "bunsik", "healthy", "western", "bbq", "bar"]
    
    JSON 외에는 아무 말도 하지 마.

    예시:
    입력: 조용하고 감성적인 분위기의 카페 추천해줘. 너무 붐비는 곳은 싫어.
    출력: {{"mood": "조용한", "congestion": "medium", "category": "cafe"}}

    입력: {user_input}
    출력:
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return None

def get_gemini_chat_reply(user_input, parsed, top1_name=None, top1_distance_m=None, top1_url=None):
    """
    귀여운 '...솜!' 말투로 한두 문장 한국어 답변 생성.
    - 문장 끝은 반드시 '솜!' 또는 '솜~'로 끝내도록 강하게 지시
    - 결과가 없을 때도 자연스럽게 안내
    """
    mood = (parsed or {}).get("mood") or ""
    congestion = (parsed or {}).get("congestion") or ""
    category = (parsed or {}).get("category") or ""

    # 숫자는 너무 구체적이면 어색할 수 있어 50m 단위로 반올림
    dist_str = None
    if isinstance(top1_distance_m, (int, float)):
        dist_str = f"{int(round(top1_distance_m / 50.0) * 50)}m"

    # 프롬프트
    prompt = f"""
다음 정보를 바탕으로 사용자에게 장소 추천을 한두 문장으로 한국어로 알려주솜!
모든 문장의 끝은 반드시 '솜!' 또는 '솜~'으로 끝내주솜!
결과를 짧고 명확하게, 60자 이내로 말하솜!
가능하면 추천 가게 이름은 큰따옴표로 감싸주솜!

[사용자 입력]
{user_input}

[추출된 조건]
- mood: {mood}
- congestion: {congestion}
- category: {category}

[추천 결과 Top1]
- name: {top1_name or ""}
- distance: {dist_str or ""}
- url: {top1_url or ""}

[말하기 예시]
원하는 장소를 찾고있솜! 현재 위치에서 "{top1_name or "가게"}"가 제일 가깝솜! 링크로 바로 이동해보솜~ {top1_url or ""}

절대로 JSON으로 답하지 말고, 순수 문장만 한두 줄로 말해주솜!
"""

    try:
        response = model.generate_content(prompt)
        return (response.text or "").strip()
    except Exception:
        return None

def _safe_json(text: str):
    """LLM 응답에서 JSON만 잘라 파싱(프리폼 응답 대비 방어 코드)."""
    if not text:
        return None
    try:
        s = text[text.rfind("{"): text.rfind("}")+1]
        return json.loads(s)
    except Exception:
        try:
            return json.loads(text)
        except Exception:
            return None

# 동덕여대 위경도(이 근방 가게만 탐색)
lat = 37.606372
lng = 127.041772

# 장소 검색 함수 정의
def get_places(category_code, query='', radius=1000, lat=lat, lng=lng):
    # 카카오맵 카테고리 검색 api 엔드포인트
    # 엔드포인트: 외부에서 접속할 수 있는 api url, 여기서 정보 받아옴
    url = 'https://dapi.kakao.com/v2/local/search/category.json'
    headers = {'Authorization': f'KakaoAK {KAKAO_API_KEY}'}
    # api 호출에 필요한 쿼리 파라미터 세팅
    params = {
        'category_group_code': category_code,
        'x': lng,   # 경도
        'y': lat,   # 위도
        'radius': radius,
        'size': 15, # 한 페이지 최대 15개(카카오 제한)
        'page': 1, # 시작 페이지
        'sort': 'distance' # 가까운 거리순 정렬
    }

    places = []
    while True:
        res = requests.get(url, headers=headers, params=params) # 카카오 api 호출
        data = res.json() # json 변환
        places += data['documents'] # 'documents'에 가게 정보 리스트 넣음

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

# (추가) 슬롯 추출/되묻기/한줄 근거/NLQ→필터
# -----------------------------
def extract_conditions(user_input: str) -> dict:
    """
    위 get_gemini_conditions와 같은 의미지만 dict로 바로 반환.
    (기존 코드와의 호환을 위해 둘 다 제공)
    """
    if not model:
        return {}
    prompt = f"""
    사용자의 장소 추천 요청에서 다음 세 가지 정보를 추출해서 JSON으로 응답해 줘.

    1. mood: 자연어 그대로 문자열
    2. congestion: 반드시 "low"|"medium"|"high"
    3. category: 반드시 {CATEGORIES} 중 하나

    JSON 외에는 아무 말도 하지 마.
    입력: {user_input}
    출력:
    """
    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text or "")
        return data or {}
    except Exception:
        return {}

def missing_slots(parsed: dict):
    missing = []
    if not parsed.get("category") or parsed["category"] not in CATEGORIES:
        missing.append("category")
    if not parsed.get("congestion") or parsed["congestion"] not in CONGESTIONS:
        missing.append("congestion")
    if not parsed.get("mood"):
        missing.append("mood")
    return missing

def follow_up_question(missing_list):
    order = {"category": "카테고리(예: 카페/한식/바 등)",
             "congestion": "원하는 혼잡도(low/medium/high)",
             "mood": "분위기(예: 조용한/감성적인 등)"}
    items = [order[m] for m in missing_list]
    if len(items) == 1:
        return f"{items[0]}를 알려줄래? 솜!"
    return f"{' · '.join(items)}를 알려줄래? 솜!"

def one_line_reason(top_place: dict, mood: str, congestion: str):
    """
    카드에 붙일 1줄 근거 생성. 실패 시 보수적 템플릿 반환.
    """

    name = top_place.get("place_name") or "이곳"
    distance = top_place.get("_distance_str", "")
    rating = top_place.get("_rating_str", "")
    prompt = f"""
    다음 정보를 한 줄 한국어로 요약해 추천 근거를 만들어줘. 30자 이내, 과장 금지.
    - 가게: "{name}"
    - 거리: {distance or "가까움"}
    - 목표 분위기: {mood or "일반"}
    - 원하는 혼잡도: {congestion or "medium"}
    - 별점: {rating or "정보없음"}

    형태 예: 리뷰에 '조용' 언급 多 + 현재 low
    """
    try:
        res = model.generate_content(prompt)
        text = (res.text or "").strip()
        return text if text else f"{distance or '가까움'} · {mood or '무드'} · {congestion or '혼잡도'}"
    except Exception:
        return f"{distance or '가까움'} · {mood or '무드'} · {congestion or '혼잡도'}"

def nlq_to_filters(nlq: str) -> dict:
    """
    자연어 → 구조화 필터(JSON) 예시:
    {"has_outlet": true, "quiet": true, "group_ok": false, "open_until": "23:00", "price_tier": "mid"}
    """
    if not model:
        return {}
    prompt = f"""
    다음 한국어 문장을 가게 검색 필터 JSON으로 변환해줘.
    허용 키:
      - has_outlet: bool (콘센트 여부)
      - quiet: bool (조용함 선호)
      - group_ok: bool (단체 가능)
      - late_open: bool (늦게까지 영업)
      - open_until: "HH:MM" (최소 영업 종료 시각)
      - price_tier: "low"|"mid"|"high" (대략적 가격대)
    존재하지 않으면 생략. JSON만 출력.

    예) "콘센트 있고 조용한 곳"
    -> {{"has_outlet": true, "quiet": true}}

    입력: {nlq}
    출력:
    """
    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text or "")
        return data or {}
    except Exception:
        return {}