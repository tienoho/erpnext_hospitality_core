"""Chỉ khởi tạo cấu hình bench test trong container hospitality-v2-test."""
import json
from pathlib import Path

root=Path('/home/frappe/test-bench')
if Path.cwd()!=root or not Path('/source/hospitality_core').exists():
    raise SystemExit('Chỉ chạy trong container test riêng.')
(root/'sites/apps.txt').write_text('frappe\nerpnext\nhospitality_core\n')
(root/'sites/common_site_config.json').write_text(json.dumps(dict(
    db_host='hospitality-v2-db',db_port=3306,redis_cache='redis://hospitality-v2-redis:6379/0',
    redis_queue='redis://hospitality-v2-redis:6379/1',redis_socketio='redis://hospitality-v2-redis:6379/2',
    developer_mode=0,disable_telemetry=1)))
