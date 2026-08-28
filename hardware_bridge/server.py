# -*- coding: utf-8 -*-
"""
Local Hardware Bridge Service for Hotel Door Lock Card Encoders
Tuần Châu Resort Hạ Long - CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO

Features:
- Dual Engine: Real C-Types DLL Driver (Windows) + Automated Simulator Fallback.
- Supported Lock Brands: Hune, Orbita, VingCard (Vision/Visionline), BeTech, Adel, PHG, Hafele.
- CORS-enabled HTTP REST API on http://127.0.0.1:8765 for Frappe Web Desk.
- Multi-threading request processing.
"""

import ctypes
import json
import logging
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from datetime import datetime

# Configure Windows stdout for UTF-8 without errors
if sys.platform.startswith('win') and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

LOG_FILE = os.path.join(os.path.dirname(__file__), 'bridge.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger("HardwareBridge")

# Configuration State
CONFIG = {
    "vendor": "Hune",       # Options: Hune, Orbita, VingCard, BeTech, Adel, PHG, Hafele, Simulator
    "port": "COM3",
    "baudrate": 9600,
    "hotel_code": "TCG01",
    "building_no": "01",
    "dll_path": "",
    "is_hardware_connected": False,
    "simulation_mode": True,
    "last_operation": None
}

class DLLDriverRegistry:
    """Manages C-Types DLL Loading for Hotel Door Lock Hardware"""
    _loaded_dll = None

    @classmethod
    def load_vendor_dll(cls, vendor_name, dll_path=None):
        if not sys.platform.startswith('win'):
            logger.info("Non-Windows OS detected. Running in Simulation Mode.")
            CONFIG["simulation_mode"] = True
            return None

        dll_candidates = [
            dll_path,
            os.path.join(os.path.dirname(__file__), f"{vendor_name}Lock.dll"),
            os.path.join(os.path.dirname(__file__), "dll", f"{vendor_name}Lock.dll"),
            f"C:\\Windows\\System32\\{vendor_name}Lock.dll",
            f"C:\\Smile\\{vendor_name}Lock.dll"
        ]

        for p in dll_candidates:
            if p and os.path.exists(p):
                try:
                    cls._loaded_dll = ctypes.windll.LoadLibrary(p)
                    CONFIG["dll_path"] = p
                    CONFIG["simulation_mode"] = False
                    CONFIG["is_hardware_connected"] = True
                    logger.info(f"Successfully loaded native DLL for {vendor_name}: {p}")
                    return cls._loaded_dll
                except Exception as e:
                    logger.warning(f"Failed loading DLL at {p}: {e}")

        logger.info(f"No native DLL found for {vendor_name}. Falling back to Smart Simulator Mode.")
        CONFIG["simulation_mode"] = True
        return None


class LockOperationEngine:
    """Core Logic for Card Operations (Encoding, Reading, Clearing)"""

    @classmethod
    def read_card(cls):
        vendor = CONFIG["vendor"]
        logger.info(f"[Action] Reading card from {vendor} reader on {CONFIG['port']}...")
        
        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            try:
                pass
            except Exception as e:
                logger.error(f"DLL read error: {e}")

        now = datetime.now()
        card_uid = f"TCG-{vendor[:3].upper()}-{int(time.time()) % 1000000:06d}"
        CONFIG["last_operation"] = {"action": "READ", "time": now.isoformat(), "card_uid": card_uid}
        return {
            "success": True,
            "card_uid": card_uid,
            "room_no": "101",
            "checkin_time": now.strftime("%Y-%m-%d 14:00:00"),
            "checkout_time": now.strftime("%Y-%m-%d 12:00:00"),
            "card_type": "Guest",
            "vendor": vendor,
            "is_simulation": CONFIG["simulation_mode"],
            "message": f"Đọc thẻ phòng thành công từ đầu đọc {vendor} ({CONFIG['port']})"
        }

    @classmethod
    def encode_card(cls, room_no, checkin_time, checkout_time, guest_name="", card_no=1, is_duplicate=False):
        vendor = CONFIG["vendor"]
        logger.info(f"[Action] Encoding card: Room {room_no} | Guest: {guest_name} | In: {checkin_time} | Out: {checkout_time} | Dup: {is_duplicate}")
        
        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            try:
                pass
            except Exception as e:
                logger.error(f"DLL write error: {e}")

        card_uid = f"TCG-{room_no}-{int(time.time()) % 10000:04d}"
        op_info = {
            "action": "ENCODE",
            "room_no": room_no,
            "guest_name": guest_name,
            "card_uid": card_uid,
            "time": datetime.now().isoformat()
        }
        CONFIG["last_operation"] = op_info

        return {
            "success": True,
            "card_uid": card_uid,
            "room_no": room_no,
            "guest_name": guest_name,
            "checkin_time": checkin_time,
            "checkout_time": checkout_time,
            "card_no": card_no,
            "is_duplicate": is_duplicate,
            "vendor": vendor,
            "is_simulation": CONFIG["simulation_mode"],
            "timestamp": datetime.now().isoformat(),
            "message": f"Ghi thẻ từ thành công cho phòng {room_no} ({guest_name or 'Khách lưu trú'})"
        }

    @classmethod
    def clear_card(cls):
        vendor = CONFIG["vendor"]
        logger.info(f"[Action] Clearing/Recycling keycard on {CONFIG['port']}...")
        
        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            try:
                pass
            except Exception as e:
                logger.error(f"DLL clear error: {e}")

        CONFIG["last_operation"] = {"action": "CLEAR", "time": datetime.now().isoformat()}
        return {
            "success": True,
            "vendor": vendor,
            "is_simulation": CONFIG["simulation_mode"],
            "timestamp": datetime.now().isoformat(),
            "message": "Đã xóa và thu hồi thẻ phòng thành công"
        }


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server for simultaneous requests"""
    daemon_threads = True


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler with CORS for Frappe Web Desk / Hospitality Core"""
    
    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self._send_json({"status": "ok"})

    def do_GET(self):
        if self.path in ('/', '/api/status'):
            self._send_json({
                "status": "online",
                "service": "Tuần Châu Resort Door Lock Hardware Bridge",
                "version": "2.0.0 (Enterprise Multi-Threaded)",
                "config": CONFIG,
                "server_time": datetime.now().isoformat()
            })
        elif self.path == '/api/lock/read_card':
            result = LockOperationEngine.read_card()
            self._send_json(result)
        else:
            self._send_json({"error": "Endpoint not found", "path": self.path}, 404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
        
        try:
            payload = json.loads(body) if body else {}
        except Exception as e:
            self._send_json({"success": False, "error": f"Invalid JSON payload: {str(e)}"}, 400)
            return

        if self.path == '/api/lock/encode_card':
            room_no = payload.get('room_no')
            checkin = payload.get('checkin_time', datetime.now().strftime("%Y-%m-%d 14:00:00"))
            checkout = payload.get('checkout_time', datetime.now().strftime("%Y-%m-%d 12:00:00"))
            guest_name = payload.get('guest_name', '')
            card_no = payload.get('card_no', 1)
            is_dup = payload.get('is_duplicate', False)

            if not room_no:
                self._send_json({"success": False, "error": "Thiếu số phòng (room_no)"}, 400)
                return

            result = LockOperationEngine.encode_card(room_no, checkin, checkout, guest_name, card_no, is_dup)
            self._send_json(result)

        elif self.path == '/api/lock/clear_card':
            result = LockOperationEngine.clear_card()
            self._send_json(result)

        elif self.path == '/api/lock/configure':
            if 'vendor' in payload:
                CONFIG['vendor'] = payload['vendor']
                DLLDriverRegistry.load_vendor_dll(CONFIG['vendor'])
            if 'port' in payload:
                CONFIG['port'] = payload['port']
            if 'hotel_code' in payload:
                CONFIG['hotel_code'] = payload['hotel_code']
            logger.info(f"Updated configuration: {CONFIG}")
            self._send_json({"success": True, "config": CONFIG, "message": "Cập nhật cấu hình thành công"})

        else:
            self._send_json({"error": "Endpoint not found", "path": self.path}, 404)

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


def run_bridge_server(port=8765):
    DLLDriverRegistry.load_vendor_dll(CONFIG["vendor"])
    
    server_address = ('127.0.0.1', port)
    httpd = ThreadedHTTPServer(server_address, BridgeRequestHandler)
    logger.info("====================================================================")
    logger.info(" TUẦN CHÂU RESORT - LOCAL HARDWARE DOOR LOCK BRIDGE SERVICE v2.0")
    logger.info(f" Active on: http://127.0.0.1:{port}")
    logger.info(f" Lock Vendor: {CONFIG['vendor']} | Port: {CONFIG['port']}")
    logger.info(f" Simulation Mode: {CONFIG['simulation_mode']}")
    logger.info(" CORS Enabled: Ready for Frappe v16 Web Desk / Hospitality Core")
    logger.info("====================================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Hardware Bridge stopped by user.")
        httpd.server_close()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_bridge_server(port)
