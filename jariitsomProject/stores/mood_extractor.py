# stores/mood_extractor.py
import re
from collections import Counter
from konlpy.tag import Okt

OKT = Okt()

TOP_K = 5
NEG_WINDOW = 5
PROX_NEAR = 2
PROX_MID = 5

# 공통 앵커
ANCHORS_COMMON = {
    "분위기","인테리어","공간","좌석","자리","소음","음악","조명","테이블",
    "내부","감성","동선","쾌적","청결","위생","컨센트","콘센트"
}

# 카테고리별 앵커 (필요시 추가)
ANCHORS_BY_CATEGORY = {
    "cafe": ANCHORS_COMMON | {"공부","작업","좌석","콘센트","테이블","창가","채광","조용","향","베이커리"},
    "bar": ANCHORS_COMMON | {"조명","음악","시끄러움","좌석","테이블"},
    "korean": ANCHORS_COMMON | {"좌석","소음","청결","위생","테이블"},
    "japanese": ANCHORS_COMMON | {"좌석","청결","테이블"},
    "chinese": ANCHORS_COMMON | {"좌석","소음","위생"},
    "western": ANCHORS_COMMON | {"좌석","청결","인테리어"},
    "fastfood": ANCHORS_COMMON | {"좌석","소음"},
    "bunsik": ANCHORS_COMMON | {"좌석","소음"},
    "healthy": ANCHORS_COMMON | {"좌석","청결","인테리어"},
    "bbq": ANCHORS_COMMON | {"좌석","소음","환기","냄새","연기"},
}

# 간단 감성 사전
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

def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def _split_sentences(text: str):
    text = _normalize_text(text)
    return [s.strip() for s in re.split(r"(?<=[\.!\?]|요|다)\s+", text) if s.strip()]

def _adjective_pretty(adj: str) -> str:
    return adj[:-2]+"한" if adj.endswith("하다") else adj

def _anchor_set(category: str):
    base = set(ANCHORS_COMMON)
    if category and category in ANCHORS_BY_CATEGORY:
        base |= ANCHORS_BY_CATEGORY[category]
    return base

def _score_mood_words(text: str, category: str):
    anchors = _anchor_set(category)
    candidates = Counter()
    pair_candidates = Counter()

    for sent in _split_sentences(text):
        morphs = OKT.pos(sent, stem=True)
        toks = [w for w,_ in morphs]

        anchor_idx = [i for i,(w,t) in enumerate(morphs) if (t in {"Noun","Adjective"} and w in anchors)]
        intens = {i for i,(w,t) in enumerate(morphs) if t=="Adverb" and w in INTENSIFIERS}
        dimin  = {i for i,(w,t) in enumerate(morphs) if t=="Adverb" and w in DIMINISHERS}

        for i,(w,t) in enumerate(morphs):
            cand = None
            if t == "Adjective":
                cand = w
            elif t == "Noun" and w.endswith(("함","감","미")) and len(w) > 1:
                cand = w[:-1] + "하다"
            if not cand:
                continue

            cand = NORMALIZE.get(cand, cand)

            base = 1.0 if cand in POS_WORDS else (-1.0 if cand in NEG_WORDS else 0.25)

            weight = 1.0
            if (i-1) in intens or (i-2) in intens: weight *= 1.2
            if (i-1) in dimin  or (i-2) in dimin:  weight *= 0.85

            prox = 0.0
            if anchor_idx:
                d = min(abs(i-a) for a in anchor_idx)
                if d <= PROX_NEAR: prox += 1.0
                elif d <= PROX_MID: prox += 0.5

            start = max(0, i-NEG_WINDOW)
            ctx = {w for w,_ in morphs[start:i]}
            polarity = -1.0 if ctx & NEGATIONS else 1.0

            score = (base + prox) * weight * polarity
            if score >= -0.2:
                candidates[cand] += score

            if anchor_idx:
                nearest = min(anchor_idx, key=lambda a: abs(i-a))
                if abs(nearest - i) <= PROX_MID:
                    pair = f"{_adjective_pretty(cand)} {toks[nearest]}"
                    pair_candidates[pair] += max(0.1, score)

    return candidates, pair_candidates

def pick_mood_tags(text: str, category: str, top_k: int = TOP_K, mode: str = "adj"):
    """
    mode="adj"        → '조용한','깔끔한' 같은 형용사 위주
    mode="adj_anchor" → '조용한 분위기' 같은 결합 태그 우선
    """
    text = _normalize_text(text)
    if not text:
        return []

    cand_adj, cand_pairs = _score_mood_words(text, category)

    pretties = Counter({ _adjective_pretty(adj): sc for adj,sc in cand_adj.items() })
    top_adj = [w for w,_ in pretties.most_common(20)]
    top_pairs = [w for w,_ in cand_pairs.most_common(20)]
    pool = (top_pairs + top_adj) if mode=="adj_anchor" else (top_adj + top_pairs)

    seen, final = set(), []
    for w in pool:
        if len(w) < 2 or w in seen: 
            continue
        seen.add(w); final.append(w)
        if len(final) == top_k: 
            break
    return final
