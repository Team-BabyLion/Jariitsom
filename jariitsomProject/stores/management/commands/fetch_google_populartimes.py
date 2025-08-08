from django.core.management.base import BaseCommand
from stores.models import Store
from stores.utils_google import crawl_popular_times_weekly_by_latlng_name
import time

class Command(BaseCommand):
    help = "위경도+가게명으로 구글맵 인기시간대(요일×시간) 크롤링하여 Store.google_hourly 저장"

    def add_arguments(self, parser):
        parser.add_argument("--recrawl", action="store_true",
                            help="기존 google_hourly 있어도 재크롤링")
        parser.add_argument("--sleep", type=float, default=0.7,
                            help="가게 간 대기 시간(sec)")
        parser.add_argument("--only-with-kakao", action="store_true",
                            help="kakao_url 있는 가게만 처리(권장)")

    def handle(self, *args, **opts):
        recrawl = opts["recrawl"]
        delay = opts["sleep"]
        only_with_kakao = opts["only_with_kakao"]

        qs = Store.objects.all()
        if only_with_kakao:
            qs = qs.filter(kakao_url__isnull=False)

        self.stdout.write(self.style.MIGRATE_HEADING(f"대상 가게 수: {qs.count()}"))

        for s in qs:
            # 기존 데이터가 있고 재크롤링 옵션이 아니면 스킵
            if s.google_hourly and not recrawl:
                self.stdout.write(f"[SKIP] {s.name} 기존 google_hourly 존재")
                time.sleep(0.15)
                continue

            # 위경도 + 가게명으로 검색 → 크롤링
            weekly, place_url = crawl_popular_times_weekly_by_latlng_name(
                lat=s.latitude, lng=s.longitude, name=s.name
            )
            if not weekly:
                self.stdout.write(self.style.WARNING(f"[NO POPULAR] {s.name} 데이터 없음/파싱 실패"))
                time.sleep(delay)
                continue

            # 저장
            update_fields = []
            if place_url and not s.google_url:
                s.google_url = place_url
                update_fields.append("google_url")

            s.google_hourly = weekly
            update_fields.append("google_hourly")

            # 혼잡도(표기용) 갱신
            try:
                s.congestion = s.current_level_from_google()
                update_fields.append("congestion")
            except Exception:
                pass

            s.save(update_fields=update_fields)

            bars = sum(len(v) for v in weekly.values())
            self.stdout.write(self.style.SUCCESS(f"[OK] {s.name} 저장 ({bars} bars)"))
            time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("완료"))
