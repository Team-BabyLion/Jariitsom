from django.core.management.base import BaseCommand
from stores.models import Store
from stores.utils import crawl_kakao_full_info_selenium
import time

class Command(BaseCommand):
    def handle(self, *args, **options):
        stores = Store.objects.all()
        for store in stores:
            if not store.kakao_url:
                self.stdout.write(f"{store.name} - 카카오맵 URL 없음, 건너뜀")
                continue

            data = crawl_kakao_full_info_selenium(store.kakao_url)
            if not data:
                self.stdout.write(f"{store.name} - 크롤링 실패")
                continue

            updated = False

            if data['rating'] is not None and store.rating != data['rating']:
                store.rating = data['rating']
                updated = True
            if data['photo_url'] and (not store.photo or data['photo_url'] != store.photo):
                store.photo = data['photo_url']
                updated = True
            if data['business_hours'] and store.business_hours != data['business_hours']:
                store.business_hours = data['business_hours']
                updated = True
            if data['menus'] and store.menus != data['menus']:
                store.menus = data['menus']
                updated = True

            if updated:
                store.save()
                self.stdout.write(f"{store.name} - 업데이트 완료")
            else:
                self.stdout.write(f"{store.name} - 변경사항 없음")
            time.sleep(0.7)  # 너무 빠른 요청 방지

        self.stdout.write("모든 가게 정보 업데이트 완료.")
