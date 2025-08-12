from django.core.management.base import BaseCommand
from django.db.models import Q
from stores.models import Store
from stores.utils_google import crawl_popular_times_weekly_by_name_address
import time

class Command(BaseCommand):
    help = "구글 지도 '인기 시간대' 빠른 크롤링(월요일 선택→오른쪽 화살표). 인기 섹션 없으면 즉시 스킵"

    def add_arguments(self, parser):
        parser.add_argument(
            "--only-with-kakao",
            action="store_true",
            help="kakao_url 있는 가게만 대상",
        )
        parser.add_argument(
            "--no-headless",
            action="store_true",
            help="브라우저 창 띄워서 실행(디버깅용)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="처리할 최대 가게 수(디버깅용)",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.3,
            help="가게 간 대기(초)",
        )

    def handle(self, *args, **opts):
        only_with_kakao = opts.get("only_with_kakao", False)
        headless = not opts.get("no_headless", False)
        limit = opts.get("limit")
        sleep_sec = float(opts.get("sleep", 0.3))

        # 모든 가게
        # qs = Store.objects.all()

        # google_hourly 가 NULL 인 가게만(재시도시 이걸로 qs 변경 후 커맨드 실행)
        qs = Store.objects.filter(google_hourly__isnull=True)

        if only_with_kakao:
            qs = qs.filter(~Q(kakao_url=""), ~Q(kakao_url=None))
        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(f"대상 가게 수: {total}")

        for idx, store in enumerate(qs.iterator(), start=1):
            try:
                weekly, place_url = crawl_popular_times_weekly_by_name_address(
                    name=store.name,
                    address=store.address,
                    headless=headless,
                )
                if not weekly:
                    self.stdout.write(self.style.WARNING(f"[SKIP] {store.name} 인기 섹션 없음/파싱 실패"))
                    time.sleep(sleep_sec)
                    continue

                store.google_hourly = weekly
                if place_url:
                    store.google_url = place_url
                store.save(update_fields=["google_hourly", "google_url"])
                self.stdout.write(self.style.SUCCESS(f"[OK] {store.name} 저장 완료 ({idx}/{total})"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[ERROR] {store.name}: {e}"))

            time.sleep(sleep_sec)
