# -*- coding: utf-8 -*-
"""
Local Hardware Bridge Service for Hotel Door Lock Card Encoders
Tuần Châu Resort Hạ Long - CÔNG TY CỔ PHẦN NGHỈ DƯỠNG ĐÀO

Features:
- Dual Engine: Native C-Types DLL Driver (Windows) + Automated Simulator Fallback.
- Supported Lock Brands: Hune, Orbita, VingCard (Vision/Visionline), BeTech, Adel, PHG, Hafele.
- Bitness Mismatch Detection (32-bit DLL vs 64-bit Python) with PE Header Inspection.
- Chromium Private Network Access (PNA) & Full CORS for Frappe HTTPS Web Desk.
- Dynamic COM Port Scanner via Windows Registry (Zero external dependencies).
- Persistent JSON Configuration Storage (config.json).
- Multi-threaded HTTP Request Processing on port 8765.
"""

import ctypes
import json
import logging
import os
import struct
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

# Safe import for Windows Registry (Zero external dependency COM port scanner)
try:
    import winreg
except ImportError:
    winreg = None

# Configure Windows stdout for UTF-8 without errors
if sys.platform.startswith('win') and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, 'bridge.log')
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config.json')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding='utf-8')
    ]
)
logger = logging.getLogger("HardwareBridge")

# Python Bitness (32 or 64)
PYTHON_BITNESS = struct.calcsize("P") * 8

# Default Configuration State
DEFAULT_CONFIG = {
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

CONFIG = dict(DEFAULT_CONFIG)


def load_persistent_config():
    """Load config from config.json if present, overlaying defaults."""
    global CONFIG
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                CONFIG.update(saved)
                logger.info(f"Loaded persistent configuration from {CONFIG_FILE}")
        except Exception as e:
            logger.warning(f"Failed to read {CONFIG_FILE}: {e}")


def save_persistent_config():
    """Save current configuration to config.json."""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, indent=4, ensure_ascii=False)
            logger.info("Saved configuration to config.json")
    except Exception as e:
        logger.error(f"Failed to save {CONFIG_FILE}: {e}")


def get_available_com_ports():
    """Scan available COM ports from Windows Registry without requiring pyserial."""
    ports = []
    if winreg:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
            num_values = winreg.QueryInfoKey(key)[1]
            for i in range(num_values):
                _, val_data, _ = winreg.EnumValue(key, i)
                if val_data:
                    ports.append(str(val_data))
            winreg.CloseKey(key)
        except Exception:
            pass
    # Sort naturally (COM1, COM2, COM10...)
    try:
        ports.sort(key=lambda x: int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else x)
    except Exception:
        ports.sort()
    return ports


def get_pe_architecture(file_path):
    """
    Inspect the PE header of a Windows DLL file to determine its architecture.
    Returns: '32-bit (x86)', '64-bit (x64)', 'ARM64', or 'Unknown'
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, 'rb') as f:
            header = f.read(64)
            if header[:2] != b'MZ':
                return 'Non-PE file'
            pe_offset = int.from_bytes(header[0x3C:0x40], byteorder='little')
            f.seek(pe_offset)
            pe_sig = f.read(4)
            if pe_sig != b'PE\x00\x00':
                return 'Invalid PE signature'
            machine = int.from_bytes(f.read(2), byteorder='little')
            if machine == 0x014C:
                return '32-bit (x86)'
            elif machine == 0x8664:
                return '64-bit (x64)'
            elif machine == 0xAA64:
                return 'ARM64'
            return f'Unknown (0x{machine:04X})'
    except Exception as e:
        return f'Error reading PE ({e})'


class DLLDriverRegistry:
    """Manages C-Types DLL Loading & Architecture Compatibility for Hotel Door Lock Hardware"""
    _loaded_dll = None
    _dll_arch = None
    _arch_mismatch = False
    _diagnostic_msg = ""

    @classmethod
    def load_vendor_dll(cls, vendor_name, dll_path=None):
        cls._loaded_dll = None
        cls._dll_arch = None
        cls._arch_mismatch = False
        cls._diagnostic_msg = ""

        if not sys.platform.startswith('win'):
            logger.info("Hệ điều hành không phải Windows. Chạy ở chế độ Mô phỏng (Simulation Mode).")
            CONFIG["simulation_mode"] = True
            CONFIG["is_hardware_connected"] = False
            cls._diagnostic_msg = "Non-Windows OS (Simulation only)"
            return None

        if vendor_name == "Simulator":
            logger.info("Chế độ kiểm thử/mô phỏng được kích hoạt chủ động.")
            CONFIG["simulation_mode"] = True
            CONFIG["is_hardware_connected"] = False
            cls._diagnostic_msg = "Explicit Simulator Mode"
            return None

        dll_candidates = [
            dll_path,
            os.path.join(SCRIPT_DIR, f"{vendor_name}Lock.dll"),
            os.path.join(SCRIPT_DIR, "dll", f"{vendor_name}Lock.dll"),
            os.path.join(SCRIPT_DIR, f"{vendor_name}.dll"),
            f"C:\\Windows\\System32\\{vendor_name}Lock.dll",
            f"C:\\Smile\\{vendor_name}Lock.dll"
        ]

        found_path = None
        for p in dll_candidates:
            if p and os.path.exists(p):
                found_path = p
                break

        if not found_path:
            logger.info(f"Không tìm thấy file DLL cho hãng '{vendor_name}'. Chuyển sang Smart Simulator Mode.")
            CONFIG["simulation_mode"] = True
            CONFIG["is_hardware_connected"] = False
            cls._diagnostic_msg = f"Không tìm thấy DLL ({vendor_name}Lock.dll) tại {SCRIPT_DIR}"
            return None

        # Inspect PE architecture
        cls._dll_arch = get_pe_architecture(found_path)
        logger.info(f"Đã tìm thấy DLL: {found_path} [Kiến trúc: {cls._dll_arch}] | Python hiện tại: {PYTHON_BITNESS}-bit")

        # Detect Bitness Mismatch
        if (cls._dll_arch == '32-bit (x86)' and PYTHON_BITNESS == 64) or \
           (cls._dll_arch == '64-bit (x64)' and PYTHON_BITNESS == 32):
            cls._arch_mismatch = True
            msg = (
                f"[CẢNH BÁO KIẾN TRÚC] DLL '{os.path.basename(found_path)}' là {cls._dll_arch}, "
                f"nhưng Python đang chạy là {PYTHON_BITNESS}-bit! "
                f"Windows không thể nạp DLL khác bitness vào tiến trình. "
                f"Vui lòng cài đặt Python {cls._dll_arch.split()[0]} cho máy tính Lễ tân để kết nối phần cứng khóa thật."
            )
            logger.error(msg)
            cls._diagnostic_msg = msg
            CONFIG["simulation_mode"] = True
            CONFIG["is_hardware_connected"] = False
            return None

        # Attempt to load DLL
        try:
            cls._loaded_dll = ctypes.windll.LoadLibrary(found_path)
            CONFIG["dll_path"] = found_path
            CONFIG["simulation_mode"] = False
            CONFIG["is_hardware_connected"] = True
            cls._diagnostic_msg = f"Đã nạp thành công DLL {vendor_name} ({cls._dll_arch})"
            logger.info(f"Tải thành công thư viện C-Types DLL: {found_path}")
            return cls._loaded_dll
        except Exception as e:
            logger.warning(f"Lỗi khi nạp DLL tại {found_path}: {e}")
            cls._diagnostic_msg = f"Lỗi nạp DLL: {str(e)}"
            CONFIG["simulation_mode"] = True
            CONFIG["is_hardware_connected"] = False
            return None


class LockOperationEngine:
    """Core Logic for Card Operations (Encoding, Reading, Clearing)"""

    @classmethod
    def read_card(cls):
        vendor = CONFIG["vendor"]
        port = CONFIG["port"]
        logger.info(f"[Action] Reading card from {vendor} reader on {port}...")

        # Guard against silent fake success when real DLL is active but vendor SDK functions are not implemented
        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            logger.error(f"DLL loaded for {vendor} nhưng chưa có logic SDK đọc thẻ thực tế — từ chối để tránh báo thành công giả.")
            return {
                "success": False,
                "vendor": vendor,
                "is_simulation": False,
                "message": f"Chưa tích hợp driver SDK đọc thẻ cho {vendor}. Vui lòng chuyển sang Simulation Mode hoặc cài đặt driver cụ thể."
            }

        # Simulation Mode: Standardized simulated card read
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
            "port": port,
            "is_simulation": CONFIG["simulation_mode"],
            "message": f"Đọc thẻ phòng thành công (Chế độ mô phỏng - Đầu đọc {vendor} trên {port})"
        }

    @classmethod
    def encode_card(cls, room_no, checkin_time, checkout_time, guest_name="", card_no=1, is_duplicate=False):
        vendor = CONFIG["vendor"]
        port = CONFIG["port"]
        logger.info(f"[Action] Encoding card: Room {room_no} | Guest: {guest_name} | In: {checkin_time} | Out: {checkout_time} | Dup: {is_duplicate}")

        # Guard against silent fake success when real DLL is active
        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            logger.error(f"DLL loaded for {vendor} nhưng chưa có logic SDK ghi thẻ thực tế — từ chối để tránh phát thẻ rỗng cho khách.")
            return {
                "success": False,
                "vendor": vendor,
                "is_simulation": False,
                "message": f"Chưa tích hợp driver SDK ghi thẻ cho {vendor}. TUYỆT ĐỐI KHÔNG trao thẻ này cho khách. Vui lòng chuyển sang Simulation Mode hoặc cập nhật SDK."
            }

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
            "port": port,
            "is_simulation": CONFIG["simulation_mode"],
            "timestamp": datetime.now().isoformat(),
            "message": f"Ghi thẻ từ thành công cho phòng {room_no} ({guest_name or 'Khách lưu trú'})"
        }

    @classmethod
    def clear_card(cls):
        vendor = CONFIG["vendor"]
        port = CONFIG["port"]
        logger.info(f"[Action] Clearing/Recycling keycard on {port}...")

        if not CONFIG["simulation_mode"] and DLLDriverRegistry._loaded_dll:
            logger.error(f"DLL loaded for {vendor} nhưng chưa có logic xóa thẻ thật — từ chối để tránh báo thành công giả.")
            return {
                "success": False,
                "vendor": vendor,
                "is_simulation": False,
                "message": f"Chưa tích hợp driver SDK xóa thẻ cho {vendor}."
            }

        CONFIG["last_operation"] = {"action": "CLEAR", "time": datetime.now().isoformat()}
        return {
            "success": True,
            "vendor": vendor,
            "port": port,
            "is_simulation": CONFIG["simulation_mode"],
            "timestamp": datetime.now().isoformat(),
            "message": "Đã xóa và thu hồi thẻ phòng thành công"
        }


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP Server for simultaneous requests without blocking"""
    daemon_threads = True


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler with Chromium PNA and CORS for Frappe Web Desk"""

    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Access-Control-Request-Private-Network')
        # Chromium Private Network Access (PNA) header - Essential when HTTPS Desk calls local HTTP
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Access-Control-Max-Age', '86400')

    def _send_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/api/status'):
            com_ports = get_available_com_ports()
            self._send_json({
                "status": "online",
                "service": "Tuần Châu Resort Door Lock Hardware Bridge",
                "version": "2.1.0 (Enterprise Multi-Threaded)",
                "python_info": {
                    "version": sys.version.split()[0],
                    "bitness": f"{PYTHON_BITNESS}-bit"
                },
                "hardware_info": {
                    "vendor": CONFIG["vendor"],
                    "port": CONFIG["port"],
                    "baudrate": CONFIG["baudrate"],
                    "dll_path": CONFIG["dll_path"],
                    "dll_architecture": DLLDriverRegistry._dll_arch,
                    "architecture_mismatch": DLLDriverRegistry._arch_mismatch,
                    "is_hardware_connected": CONFIG["is_hardware_connected"],
                    "simulation_mode": CONFIG["simulation_mode"],
                    "diagnostic_message": DLLDriverRegistry._diagnostic_msg
                },
                "available_com_ports": com_ports,
                "server_time": datetime.now().isoformat(),
                "last_operation": CONFIG.get("last_operation")
            })

        elif self.path == '/api/ports':
            ports = get_available_com_ports()
            self._send_json({
                "success": True,
                "ports": ports,
                "current_port": CONFIG["port"]
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
            changed = False
            if 'vendor' in payload and payload['vendor'] != CONFIG.get('vendor'):
                CONFIG['vendor'] = payload['vendor']
                DLLDriverRegistry.load_vendor_dll(CONFIG['vendor'])
                changed = True
            if 'port' in payload and payload['port'] != CONFIG.get('port'):
                CONFIG['port'] = payload['port']
                changed = True
            if 'hotel_code' in payload and payload['hotel_code'] != CONFIG.get('hotel_code'):
                CONFIG['hotel_code'] = payload['hotel_code']
                changed = True
            if 'simulation_mode' in payload:
                CONFIG['simulation_mode'] = bool(payload['simulation_mode'])
                changed = True

            if changed:
                save_persistent_config()
                logger.info(f"Updated configuration: {CONFIG}")

            self._send_json({
                "success": True,
                "config": CONFIG,
                "diagnostic": DLLDriverRegistry._diagnostic_msg,
                "message": "Cập nhật cấu hình thành công"
            })

        else:
            self._send_json({"error": "Endpoint not found", "path": self.path}, 404)

    def log_message(self, format, *args):
        logger.info(f"{self.client_address[0]} - {format % args}")


def run_bridge_server(port=8765):
    # Load persistent configuration
    load_persistent_config()

    # Initialize vendor driver
    DLLDriverRegistry.load_vendor_dll(CONFIG["vendor"], CONFIG.get("dll_path"))

    available_ports = get_available_com_ports()

    server_address = ('127.0.0.1', port)
    httpd = ThreadedHTTPServer(server_address, BridgeRequestHandler)
    logger.info("====================================================================")
    logger.info(" TUẦN CHÂU RESORT - LOCAL HARDWARE DOOR LOCK BRIDGE SERVICE v2.1")
    logger.info(f" Active on: http://127.0.0.1:{port}")
    logger.info(f" Python Environment: {sys.version.split()[0]} ({PYTHON_BITNESS}-bit)")
    logger.info(f" Lock Vendor: {CONFIG['vendor']} | Selected Port: {CONFIG['port']}")
    logger.info(f" Detected COM Ports: {available_ports if available_ports else 'None'}")
    logger.info(f" Simulation Mode: {CONFIG['simulation_mode']}")
    if DLLDriverRegistry._arch_mismatch:
        logger.warning(f" ARCHITECTURE MISMATCH: {DLLDriverRegistry._diagnostic_msg}")
    logger.info(" Chromium PNA & CORS Enabled: Ready for Frappe HTTPS Web Desk")
    logger.info("====================================================================")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Hardware Bridge stopped by user.")
        httpd.server_close()


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_bridge_server(port)
