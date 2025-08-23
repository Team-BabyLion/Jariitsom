from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import timedelta
import math
from django.utils import timezone
from django.db.models import QuerySet
from .models import Store, VisitLog
from sklearn.linear_model import LogisticRegression
import numpy as np
from functools import lru_cache

# 혼잡도 라벨과 정수 인덱스 양방향 매핑
_LABEL2IDX = {"low": 0, "medium": 1, "high": 2}
_IDX2LABEL = {v: k for k, v in _LABEL2IDX.items()}

# VisitLog vs 인기 시간대 크롤링 데이터 최종 합성 가중치
WEIGHT_MODEL_BASE = 0.7
# WEIGHT_GOOGLE_BASE = 0.3(w_google = 1-w_model로 대체됨)

# 샘플 수가 적을 때(모델 불안정) 가중치를 완화시킬 범위(샘플이 많을수로 MAX에 가까워짐)
WEIGHT_MODEL_MIN = 0.55
WEIGHT_MODEL_MAX = 0.9

# 현재 요일과 같은 요일일 경우 가중치에 곱해줌
WEEKDAY_MATCH_BONUS = 2.0

# 학습 샘플 최소 개수 기준(이 미만이면 불안정으로 간주함)
MIN_SAMPLES = 20

# dt를 주기적(사인/코사인) 특성으로 변환
def _time_feats(dt) -> Tuple[float, float, float, float]:
    h = dt.hour + dt.minute / 60.0  # 시간 0~24
    w = dt.weekday()                # 요일 0~6
    # 하루 주기를 기준으로 시간의 사인/코사인 인코딩->연속값
    h_sin = math.sin(2 * math.pi * h / 24.0)
    h_cos = math.cos(2 * math.pi * h / 24.0)
    # 일주일 주기를 기준으로 요일의 사인/코사인 인코딩
    w_sin = math.sin(2 * math.pi * w / 7.0)
    w_cos = math.cos(2 * math.pi * w / 7.0)
    return h_sin, h_cos, w_sin, w_cos

# 현재 시간대(dt) google_hourly 퍼센트를 가져오고 분단위로 선형보간
def _google_percent_at(store: Store, dt) -> Optional[int]:
    if not store.google_hourly:
        return None

    w = dt.weekday()
    arr_today = store.google_hourly.get(str(w))
    if not arr_today or len(arr_today) != 24:
        return None

    h = dt.hour
    m = dt.minute / 60.0  # 분 비율(0.0~1.0)
    p0 = arr_today[h] # 현재 시각(13시)

    if h < 23:
        p1 = arr_today[h + 1] # 다음 시각(14시)
    else: # 23시면 다음날 0시 값과 보간, 다음날 배열이 없거나 길이가 24가 아니면 p1=p0
        arr_next = store.google_hourly.get(str((w + 1) % 7))
        p1 = arr_next[0] if arr_next and len(arr_next) == 24 else p0

    return int(round(p0 + (p1 - p0) * m)) # 선형 보간

# 예측 결과 하나를 담는 데이터 클래스
@dataclass
class ForecastItem:
    minutes_ahead: int # 현재(0)로부터 몇 분 뒤 예측인지
    at: str # 예측 시각
    ai_level: str  # 최종 합성 결과

# 최근 방문기록으로 학습 데이터(X), 라벨(y), 샘플 가중치(w) 반환
def _collect_training_data(store: Store, days: int = 30,
    base_weekday: Optional[int] = None  # 오늘 요일을 넘겨 받음
) -> Tuple[list, list, list]:
    since = timezone.localtime() - timedelta(days=days) # 학습 데이터 시작 시점(현재로부터 days일 전)
    logs: QuerySet[VisitLog] = (
        store.visit_logs
        .filter(created_at__gte=since)
        .only("created_at", "congestion") # 둘만 가져옴(피쳐로 쓸 것)
    )

    X, y, w = [], [], []
    now = timezone.localtime()

    for lg in logs:
        dt = timezone.localtime(lg.created_at) # 로그 생성 시각을 로컬 시각으로 변환

        # 시간/요일 주기 특성
        h_sin, h_cos, w_sin, w_cos = _time_feats(dt)
        X.append([h_sin, h_cos, w_sin, w_cos])
        y.append(_LABEL2IDX.get(lg.congestion, 1)) # 혼잡도 문자열 정수 라벨로 매핑(기본 보통)

        # 최신 로그 가중치(24시간 반감기)
        age_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
        weight = 0.5 ** (age_hours / 24.0)

        # 오늘과 같은 요일이면 보너스
        if base_weekday is not None and dt.weekday() == base_weekday:
            weight *= WEEKDAY_MATCH_BONUS

        w.append(weight)

    return X, y, w

# X, y, w를 받아 로지스틱 회귀 모델을 학습해 반환
def _train_model(X: list, y: list, w: list):
    if len(X) < MIN_SAMPLES:
        return None # 샘플 수가 너무 적으면 학습 x
    try:
        model = LogisticRegression(max_iter=300, multi_class="auto",
            C=0.8  # 과적합 억제용 규제 강화
        ) # 분류 모델
        # 파이썬 리스트를 넘파이 배열로 변환(dtype 명시->안정성)
        X_arr = np.array(X, dtype=float)
        y_arr = np.array(y, dtype=int)
        w_arr = np.array(w, dtype=float)
        model.fit(X_arr, y_arr, sample_weight=w_arr) # 학습
        return model
    except Exception:
        return None # ex) 최근 y가 전부 medium일 경우(불균형)

# 모델만 사용해 예측 -> (라벨, 예측 확률) 튜플 반환
def _predict_model(store: Store, model, t) -> Tuple[str, float]:
    h_sin, h_cos, w_sin, w_cos = _time_feats(t)
    X = np.array([[h_sin, h_cos, w_sin, w_cos]], dtype=float)
    
    proba = model.predict_proba(X)[0]  # 각 클래스[low, medium, high]의 확률 반환
    idx = int(np.argmax(proba)) # 가장 확률이 높은 인덱스
    conf = float(proba[idx]) # 그 클래스의 확률을 예측 확률로 사용
    return _IDX2LABEL[idx], conf

# 구글 인기 시간대 기준으로만 예측한 결과를 라벨로 변환
def _predict_google(store: Store, t) -> str:
    p = _google_percent_at(store, t)
    return store.percent_to_level(p)

# 모델 라벨, 구글 라벨 가중치 결합 -> 최종 라벨
def _combine_with_weights(label_model: str, label_google: str,
                          w_model: float, w_google: float) -> str:
    scores = {"low": 0.0, "medium": 0.0, "high": 0.0}
    scores[label_model] += w_model
    scores[label_google] += w_google
    # 동점이면 모델 우선
    best = max(scores.items(), key=lambda kv: (kv[1], 1 if kv[0] == label_model else 0))[0]
    return best

# 한 가게의 혼잡도를 여러 시점으로 예측 -> 리스트 반환
def forecast_congestion(store: Store, offsets: List[int] = [0, 10, 20, 30, 60], now=None) -> List[Dict[str, Any]]:
    now = now or timezone.localtime()
    base_weekday = now.weekday()

    # 최근 30일의 방문기록에서 요일/시각 피쳐만 추출해 X, y, w 만들기
    X, y, w = _collect_training_data(store, days=30, base_weekday=base_weekday)
    model = _train_model(X, y, w) # 학습

    # 샘플 수에 따라 가중치 결정(모델이 없으면 구글 인기 시간대로만)
    if model is None:
        w_model, w_google = 0.0, 1.0
    else:
        n = len(X) # 학습에 쓰인 샘플 개수
        ratio = min(1.0, max(0.0, (n - MIN_SAMPLES) / (100 - MIN_SAMPLES)))
        w_model = max(WEIGHT_MODEL_MIN + (WEIGHT_MODEL_MAX - WEIGHT_MODEL_MIN) * ratio,
                      WEIGHT_MODEL_BASE)
        w_google = 1.0 - w_model

    results = []
    for m in offsets:
        t = now + timedelta(minutes=m) # 예측 시각 계산
        
        # 모델/구글 라벨 예측과 최종 결합
        label_g = _predict_google(store, t) # 구글 라벨
        if model is None:
            # 방문기록 부족 + 구글 있음: 구글 라벨 사용(구글도 None이면 medium 처리)
            final_label = label_g if label_g in {"low","medium","high"} else "medium"
        else:
            label_m, _ = _predict_model(store, model, t)
            final_label = _combine_with_weights(label_m, label_g, w_model, w_google)
        
        # 결과 리스트에 추가
        results.append(ForecastItem(minutes_ahead=m, at=t.isoformat(), ai_level=final_label))

    # 현재값을 Store.congestion에 반영
    cur = [it for it in results if it.minutes_ahead == 0]
    if cur:
        lvl = cur[0].ai_level
        if store.congestion != lvl:
            Store.objects.filter(pk=store.pk).update(congestion=lvl)

    # dataclass 인스턴스를 dict로 변환해서 직렬화하기 쉬운 형태로 반환
    return [it.__dict__ for it in results]

# 같은 스토어/5분 버킷 동안 한 번만 예측, 계산한 현재 라벨 Store.congestion에 즉시 반영됨
@lru_cache(maxsize=1024)
def _ai_now_cached_and_sync(store_id: int, slot_key: str) -> str:
    now = timezone.localtime()
    store = Store.objects.only('id', 'congestion').get(pk=store_id)
    # 지금(0)에 대한 예측만
    data = forecast_congestion(store, offsets=[0], now=now)
    level = data[0]['ai_level']
    return level

# 호출 시점 기준 AI 현재 혼잡도를 계산/저장하고 라벨 반환(외부에서 공용으로 사용)
def ensure_ai_congestion_now(store: Store) -> str:
    now = timezone.localtime()
    slot_key = f"{now.strftime('%Y%m%d%H')}_{now.minute // 5}"  # 5분 버킷
    try:
        return _ai_now_cached_and_sync(store.id, slot_key)
    except Exception:
        # 예외 시 원래 DB 값, 없으면 medium
        return store.congestion or "medium"