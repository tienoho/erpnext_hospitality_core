# -*- coding: utf-8 -*-
"""
Automated Integration Tests for Hardware Bridge Service
Tuần Châu Resort Hạ Long
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse

if sys.platform.startswith('win') and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

PORT = 8769  # Use a dedicated port for testing to avoid collisions
BASE_URL = f"http://127.0.0.1:{PORT}"

def run_tests():
    print(f"=== KHỞI ĐỘNG KIỂM THỬ TỰ ĐỘNG HARDWARE BRIDGE TRÊN PORT {PORT} ===")
    
    server_script = os.path.join(os.path.dirname(__file__), "server.py")
    proc = subprocess.Popen([sys.executable, server_script, str(PORT)])
    
    time.sleep(1.5)  # Wait for server startup
    
    tests_passed = 0
    total_tests = 6

    try:
        # Test 1: OPTIONS Preflight (Chromium PNA & CORS)
        print("\n[Test 1] OPTIONS Preflight (Chromium PNA & CORS)...")
        req = urllib.request.Request(f"{BASE_URL}/api/lock/encode_card", method="OPTIONS")
        req.add_header("Origin", "https://erp.tuanchaugroup.com")
        req.add_header("Access-Control-Request-Method", "POST")
        req.add_header("Access-Control-Request-Private-Network", "true")
        with urllib.request.urlopen(req, timeout=5) as resp:
            headers = dict(resp.headers)
            assert headers.get("Access-Control-Allow-Private-Network") == "true", "Thiếu header Access-Control-Allow-Private-Network"
            assert headers.get("Access-Control-Allow-Origin") == "*", "Thiếu header Access-Control-Allow-Origin"
            print("✔ Passed: Preflight PNA & CORS hợp lệ.")
            tests_passed += 1

        # Test 2: GET /api/status
        print("\n[Test 2] GET /api/status...")
        with urllib.request.urlopen(f"{BASE_URL}/api/status", timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            assert data["status"] == "online"
            assert "python_info" in data
            assert "available_com_ports" in data
            print(f"✔ Passed: Trạng thái Online | Python: {data['python_info']['bitness']} | COM: {data['available_com_ports']}")
            tests_passed += 1

        # Test 3: GET /api/ports
        print("\n[Test 3] GET /api/ports (COM Port Scanning)...")
        with urllib.request.urlopen(f"{BASE_URL}/api/ports", timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            assert data["success"] is True
            assert isinstance(data["ports"], list)
            print(f"✔ Passed: Quét cổng COM thành công: {data['ports']}")
            tests_passed += 1

        # Test 4: GET /api/lock/read_card
        print("\n[Test 4] GET /api/lock/read_card (Đọc thẻ)...")
        with urllib.request.urlopen(f"{BASE_URL}/api/lock/read_card", timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            assert data["success"] is True
            assert "card_uid" in data
            print(f"✔ Passed: Đọc thẻ thành công, UID: {data['card_uid']}")
            tests_passed += 1

        # Test 5: POST /api/lock/encode_card
        print("\n[Test 5] POST /api/lock/encode_card (Ghi thẻ phòng)...")
        payload = json.dumps({
            "room_no": "VIP-302",
            "guest_name": "NGUYEN VAN TEST",
            "checkin_time": "2026-09-10 14:00:00",
            "checkout_time": "2026-09-12 12:00:00",
            "is_duplicate": False
        }).encode('utf-8')
        req = urllib.request.Request(f"{BASE_URL}/api/lock/encode_card", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            assert data["success"] is True
            assert data["room_no"] == "VIP-302"
            print(f"✔ Passed: Ghi thẻ thành công cho phòng {data['room_no']}, UID: {data['card_uid']}")
            tests_passed += 1

        # Test 6: POST /api/lock/configure & Persistence
        print("\n[Test 6] POST /api/lock/configure (Cấu hình & Lưu persistent)...")
        cfg_payload = json.dumps({
            "vendor": "Simulator",
            "port": "COM4",
            "hotel_code": "TUANCHAU_VILLAS"
        }).encode('utf-8')
        req = urllib.request.Request(f"{BASE_URL}/api/lock/configure", data=cfg_payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            assert data["success"] is True
            assert data["config"]["port"] == "COM4"
            print(f"✔ Passed: Cấu hình cập nhật thành công: Vendor={data['config']['vendor']}, Port={data['config']['port']}")
            tests_passed += 1

    finally:
        proc.terminate()
        proc.wait()
        print("\nĐã tắt tiến trình server test.")

    print(f"\n====================================================================")
    print(f" KẾT QUẢ KIỂM THỬ: {tests_passed}/{total_tests} BÀI TEST THÀNH CÔNG (100%)")
    print(f"====================================================================")
    return tests_passed == total_tests

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
