# export_stores.py

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jariitsomProject.settings')
django.setup()

from django.core.serializers import serialize
from stores.models import Store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_PATH = os.path.join(BASE_DIR, 'stores', 'fixtures')
os.makedirs(FIXTURES_PATH, exist_ok=True)

file_path = os.path.join(FIXTURES_PATH, 'stores_data.json')

# JSON 문자열로 직렬화 (datetime 포함)
json_data = serialize('json', Store.objects.all(), indent=2)

# UTF-8로 저장 (ensure_ascii=False는 serialize('json')에서 이미 적용됨)
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(json_data)
