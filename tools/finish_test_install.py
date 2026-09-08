"""Tiếp tục cài site test sau lần đồng bộ bị ngắt; không dùng trên site thật."""
from pathlib import Path
import frappe

if not Path('/home/frappe/test-bench/sites/hospitality-v2.test').exists():
    raise SystemExit('Thiếu site test riêng.')
frappe.init(site='hospitality-v2.test',sites_path='/home/frappe/test-bench/sites')
frappe.connect()
frappe.set_user('Administrator')
frappe.conf.admin_password='integration-only'
try:
    from frappe.utils.install import after_install
    frappe.flags.in_install='frappe'
    after_install()
    frappe.db.commit()
    from frappe.installer import install_app
    install_app('erpnext',force=True)
    install_app('hospitality_core',force=True)
    frappe.flags.in_install=False
    from hospitality_core.migrations.property_v2 import execute
    execute()
    frappe.db.commit()
    print('HOSPITALITY_TEST_INSTALL_OK')
finally:
    frappe.destroy()
