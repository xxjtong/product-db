"""
Import Milesight products into v2 schema with dictionary + mapping tables.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import json
import time
import requests as http_requests
from datetime import datetime

API_BASE = "http://localhost:8000/api"

# Category tree: (name, slug, level, parent_slug, spec_definitions)
CATEGORY_TREE = [
    # Level 1: Top-level
    ("网关", "gateway", 1, None, []),
    ("传感器", "sensor", 1, None, []),
    ("控制器/采集器", "controller", 1, None, []),
    ("节点/执行器", "node", 1, None, []),
    ("蜂窝设备", "cellular", 1, None, []),
    ("安防", "security", 1, None, []),
    ("工具", "tool", 1, None, []),
    # Level 2: Sub-categories
    ("LoRaWAN网关", "lorawan-gateway", 2, "gateway", [
        {"spec_key": "processor", "display_name": "处理器", "spec_type": "string", "display_group": "硬件", "sort_order": 1},
        {"spec_key": "memory", "display_name": "内存", "spec_type": "string", "display_group": "硬件", "sort_order": 2},
        {"spec_key": "flash_storage", "display_name": "存储", "spec_type": "string", "display_group": "硬件", "sort_order": 3},
        {"spec_key": "lora_chipset", "display_name": "LoRa芯片", "spec_type": "string", "display_group": "LoRa", "sort_order": 5},
        {"spec_key": "lora_channels", "display_name": "通道数", "spec_type": "number", "display_group": "LoRa", "sort_order": 6},
        {"spec_key": "frequency_band", "display_name": "频段", "spec_type": "string", "display_group": "LoRa", "sort_order": 7},
        {"spec_key": "tx_power", "display_name": "发射功率", "spec_type": "string", "display_group": "LoRa", "sort_order": 8},
        {"spec_key": "rx_sensitivity", "display_name": "接收灵敏度", "spec_type": "string", "display_group": "LoRa", "sort_order": 9},
        {"spec_key": "lora_class", "display_name": "LoRaWAN Class", "spec_type": "string", "display_group": "LoRa", "sort_order": 10},
        {"spec_key": "max_endpoints", "display_name": "终端容量", "spec_type": "number", "display_group": "LoRa", "sort_order": 11},
        {"spec_key": "built_in_ns", "display_name": "内置NS", "spec_type": "boolean", "display_group": "软件", "sort_order": 20},
        {"spec_key": "docker", "display_name": "Docker支持", "spec_type": "boolean", "display_group": "软件", "sort_order": 21},
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65", "IP67"], "sort_order": 30},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 31},
        {"spec_key": "weight", "display_name": "重量", "spec_type": "string", "display_group": "物理特性", "sort_order": 32},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 40},
        {"spec_key": "avg_power", "display_name": "平均功耗", "spec_type": "string", "display_group": "供电", "sort_order": 50},
        {"spec_key": "peak_power", "display_name": "峰值功耗", "spec_type": "string", "display_group": "供电", "sort_order": 51},
        {"spec_key": "mounting", "display_name": "安装方式", "spec_type": "string", "display_group": "物理特性", "sort_order": 33},
    ]),
    ("LoRaWAN传感器", "lorawan-sensor", 2, "sensor", [
        {"spec_key": "nfc_config", "display_name": "NFC配置", "spec_type": "boolean", "display_group": "软件", "sort_order": 1},
        {"spec_key": "data_storage", "display_name": "数据存储(条)", "spec_type": "number", "display_group": "软件", "sort_order": 2},
        {"spec_key": "screen", "display_name": "显示屏", "spec_type": "string", "display_group": "硬件", "sort_order": 3},
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65", "IP67"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "weight", "display_name": "重量", "spec_type": "string", "display_group": "物理特性", "sort_order": 12},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("NB-IoT传感器", "nbiot-sensor", 2, "sensor", [
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65", "IP67"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("LoRaWAN控制器", "lorawan-controller", 2, "controller", [
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("LoRaWAN节点/执行器", "lorawan-node", 2, "node", [
        {"spec_key": "function", "display_name": "功能", "spec_type": "string", "display_group": "功能", "sort_order": 1},
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("4G/5G路由器", "cellular-router", 2, "cellular", [
        {"spec_key": "processor", "display_name": "处理器", "spec_type": "string", "display_group": "硬件", "sort_order": 1},
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("5G CPE/Dongle", "cellular-cpe", 2, "cellular", [
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP30", "IP54", "IP65"], "sort_order": 10},
        {"spec_key": "dimensions", "display_name": "尺寸", "spec_type": "string", "display_group": "物理特性", "sort_order": 11},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("部署/配置工具", "tool", 2, "tool", [
        {"spec_key": "function", "display_name": "功能", "spec_type": "string", "display_group": "功能", "sort_order": 1},
    ]),
    ("感知相机", "sensing-camera", 2, "security", [
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP54", "IP65", "IP67"], "sort_order": 10},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
    ("网络摄像机/NVR", "nvr", 2, "security", [
        {"spec_key": "ip_rating", "display_name": "防护等级", "spec_type": "enum", "display_group": "物理特性",
         "options": ["IP54", "IP65", "IP67"], "sort_order": 10},
        {"spec_key": "operating_temp", "display_name": "工作温度", "spec_type": "string", "display_group": "环境", "sort_order": 20},
    ]),
]

# Dict ID maps (will be populated from API)
COMM_METHOD_MAP = {}  # name -> id
PROTOCOL_MAP = {}
POWER_MAP = {}
MANUFACTURER_MAP = {}


def api_call(path, method="GET", data=None):
    url = f"{API_BASE}{path}"
    kwargs = {}
    if data is not None:
        kwargs["json"] = data
    resp = http_requests.request(method, url, **kwargs, timeout=10)
    if resp.status_code >= 400:
        print(f"  API ERROR {resp.status_code}: {resp.text[:200]}")
        return None
    return resp.json()


def load_dict_maps():
    """Load dict ID maps from API."""
    global COMM_METHOD_MAP, PROTOCOL_MAP, POWER_MAP, MANUFACTURER_MAP

    resp = api_call("/dicts/comm-methods")
    for m in resp.get("comm_methods", []):
        COMM_METHOD_MAP[m["name"]] = m["id"]

    resp = api_call("/dicts/comm-protocols")
    for p in resp.get("comm_protocols", []):
        PROTOCOL_MAP[p["name"]] = p["id"]

    resp = api_call("/dicts/power-supplies")
    for p in resp.get("power_supplies", []):
        POWER_MAP[p["name"]] = p["id"]

    resp = api_call("/dicts/manufacturers")
    for m in resp.get("manufacturers", []):
        MANUFACTURER_MAP[m["name"]] = m["id"]


def setup_categories():
    """Create category tree and spec definitions."""
    cat_map = {}  # slug -> id

    for name, slug, level, parent_slug, spec_defs in CATEGORY_TREE:
        parent_id = cat_map.get(parent_slug) if parent_slug else None
        data = {
            "name": name,
            "slug": slug,
            "level": level,
            "parent_id": parent_id,
        }
        res = api_call("/categories", "POST", data)
        if res:
            cat_id = res["category"]["id"]
            cat_map[slug] = cat_id
            print(f"  Created category: {name} (id={cat_id}, level={level})")
        else:
            # Try to find existing
            cats = api_call("/categories")
            for c in cats.get("categories", []):
                if c["slug"] == slug:
                    cat_map[slug] = c["id"]
                    print(f"  Category exists: {name} (id={c['id']})")
                    break

        # Create spec definitions
        if spec_defs and cat_map.get(slug):
            existing = api_call(f"/categories/{cat_map[slug]}/spec-definitions")
            existing_keys = {s["spec_key"] for s in existing.get("spec_definitions", [])}
            for sd in spec_defs:
                if sd["spec_key"] not in existing_keys:
                    api_call(f"/categories/{cat_map[slug]}/spec-definitions", "POST", sd)

    return cat_map


# Product catalog: (model, name, category_slug, image_url, data_dict)
PRODUCTS = [
    # === Gateways ===
    ("UG67", "UG67 室外型基站网关", "lorawan-gateway", "https://www.milesight.cn/wp-content/uploads/2025/01/ug67-product-1.png", {
        "comm_methods": [
            {"method_id": "Ethernet", "details": "1× 10/100/1000Mbps (PoE)"},
            {"method_id": "LoRaWAN", "details": "8通道, CN470"},
            {"method_id": "4G", "details": "LTE CAT4, nano SIM"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "BACnet/IP"}, {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "9-24V DC"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "Modbus RTU/ASC"},
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试"},
        ],
        "specs": {
            "processor": "4核 1.5GHz ARM Cortex-A53", "memory": "2GB DDR4", "flash_storage": "16GB eMMC",
            "lora_chipset": "Semtech SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "27 dBm", "rx_sensitivity": "-140 dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP67", "dimensions": "258×228×83mm", "weight": "1.8kg",
            "operating_temp": "-40°C~70°C", "avg_power": "4.5W", "peak_power": "12W",
            "mounting": "壁挂/抱杆",
        },
    }),
    ("UG65", "UG65 室内型基站网关", "lorawan-gateway", "https://www.milesight.cn/wp-content/uploads/2021/08/ug65-product-1.png", {
        "comm_methods": [
            {"method_id": "Ethernet", "details": "1× 10/100/1000Mbps (PoE)"},
            {"method_id": "LoRaWAN", "details": "8通道, CN470"},
            {"method_id": "4G", "details": "LTE, 2FF SIM"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "BACnet/IP"}, {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "9-24V DC"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
        ],
        "hardware_interfaces": [
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试串口"},
        ],
        "specs": {
            "processor": "4核 1.5GHz ARM Cortex-A53", "memory": "512MB DDR4", "flash_storage": "8GB eMMC",
            "lora_chipset": "Semtech SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "20 dBm", "rx_sensitivity": "-140 dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP65", "dimensions": "180×110×55.5mm", "weight": "548g",
            "operating_temp": "-40°C~70°C", "avg_power": "2.9W", "peak_power": "4.2W",
            "mounting": "桌面/壁挂/抱杆",
        },
    }),
    ("EG71", "EG71 楼宇物联网网关", "lorawan-gateway", "https://www.milesight.cn/wp-content/uploads/2026/01/product-lorawan-node-eg71-banner-1.png", {
        "comm_methods": [
            {"method_id": "Ethernet", "details": "2× RJ45 (WAN/LAN可切换), ETH1支持PoE"},
            {"method_id": "LoRaWAN", "details": "8通道半双工, CN470"},
            {"method_id": "4G", "details": "LTE CAT1, nano SIM"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
            {"method_id": "RS485", "details": "2× RS485, 1200~115200bps"},
            {"method_id": "KNX", "details": "1× KNX/TP1"},
            {"method_id": "M-BUS", "details": "1× M-BUS (开发中)"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT", "direction": "forwarding"},
            {"protocol_id": "HTTPS", "direction": "forwarding"},
            {"protocol_id": "HTTP", "direction": "forwarding"},
            {"protocol_id": "ModbusRTU", "direction": "acquisition"},
            {"protocol_id": "ModbusTCP", "direction": "forwarding"},
            {"protocol_id": "BACnet/IP", "direction": "forwarding"},
            {"protocol_id": "BACnet/MS-TP", "direction": "acquisition"},
            {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "24V DC/AC (端子排)"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
            {"power_id": "USB-C", "voltage_range": "5V/3A"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 2, "description": "1200~115200bps, 每总线128设备, 1×120Ω终端电阻"},
            {"interface_name": "KNX/TP1", "quantity": 1, "description": "21-30V DC (总线供电), 最多63设备"},
            {"interface_name": "M-BUS", "quantity": 1, "description": "24-42V, 最多20设备 (开发中)"},
            {"interface_name": "通用输入(UI)", "quantity": 8, "description": "DI/AI(0-10V,4-20mA)/RTD(PT1000)/NTC/电阻, 软件切换"},
            {"interface_name": "数字输入(DI)", "quantity": 4, "description": "干接点, 支持脉冲计数≥1000Hz"},
            {"interface_name": "数字输出(DO)", "quantity": 3, "description": "继电器输出, 3A@30VDC/3A@110VAC"},
            {"interface_name": "模拟输出(AO)", "quantity": 4, "description": "4-20mA或0-10V(软件切换), 12位, ±1%FS"},
            {"interface_name": "USB", "quantity": 1, "description": "Type-C (供电+调试)"},
            {"interface_name": "NFC", "quantity": 1, "description": "13.56MHz, 支持设备配对"},
            {"interface_name": "OLED", "quantity": 1, "description": "1.3寸 128×64"},
            {"interface_name": "Micro SD", "quantity": 1, "description": "扩展存储"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "processor": "4核 1.5GHz ARM Cortex-A53", "memory": "2GB DDR4", "flash_storage": "32GB eMMC",
            "lora_chipset": "Semtech SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "27 dBm", "rx_sensitivity": "-140 dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP30", "dimensions": "123×90×36mm", "weight": "375.6g",
            "operating_temp": "-40°C~60°C", "avg_power": "8.2W", "peak_power": "11.24W",
            "mounting": "壁挂/DIN导轨",
        },
    }),
    ("UG63", "UG63 轻量级室内网关", "lorawan-gateway", "https://www.milesight.cn/wp-content/uploads/2023/12/ug63-v2-front.png", {
        "comm_methods": [
            {"method_id": "Ethernet", "details": "1× 10/100Mbps (PoE)"},
            {"method_id": "LoRaWAN", "details": "8通道, CN470"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "9-24V DC"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
        ],
        "specs": {
            "processor": "1核 ARM Cortex-A7", "memory": "256MB DDR2", "flash_storage": "256MB NAND",
            "lora_chipset": "Semtech SX1308", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "20 dBm", "rx_sensitivity": "-139 dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 500, "built_in_ns": True, "docker": False,
            "ip_rating": "IP30", "dimensions": "135×115×42mm", "weight": "350g",
            "operating_temp": "-20°C~55°C", "avg_power": "2.5W", "peak_power": "3.5W",
            "mounting": "桌面/壁挂",
        },
    }),
    ("AM307", "AM307 多合一室内环境监测传感器", "lorawan-sensor", "https://www.milesight.cn/wp-content/uploads/2023/09/am300-1.png", {
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "4×ER14505 2700mAh", "battery_life": "3年(10min上报)"},
            {"power_id": "USB-C", "voltage_range": "5V/1A"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-20°C~60°C", "accuracy": "±0.2°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2%RH", "resolution": "0.5%RH"},
            {"metric_id": "CO2", "measure_range": "400~5000ppm", "accuracy": "±(30ppm+3%)", "resolution": "1ppm"},
            {"metric_id": "TVOC", "measure_range": "1.00~5.00 IAQ", "accuracy": "±1 IAQ", "resolution": "0.01"},
            {"metric_id": "气压", "measure_range": "260~1260hPa", "accuracy": "±0.5hPa", "resolution": "0.1hPa"},
        ],
        "specs": {
            "nfc_config": True, "data_storage": 18000, "screen": "4.2寸电子墨水屏",
            "ip_rating": "IP30", "dimensions": "100.8×114×22mm", "weight": "182.5g",
            "operating_temp": "-20°C~60°C",
        },
    }),
    ("EM300-TH", "EM300-TH 温湿度传感器", "lorawan-sensor", "https://www.milesight.cn/wp-content/uploads/2021/08/em300-th-product-1.png", {
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×CR2450", "battery_life": "10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2%RH", "resolution": "0.5%RH"},
        ],
        "specs": {
            "nfc_config": True, "ip_rating": "IP30", "dimensions": "46.5×45×18.5mm",
            "weight": "37g(不含电池)", "operating_temp": "-20°C~55°C",
        },
    }),
    ("UR75", "UR75 5G工业路由器", "cellular-router", "https://www.milesight.cn/wp-content/uploads/2022/10/ur75-5g-front.png", {
        "comm_methods": [
            {"method_id": "5G", "details": "NR Sub-6GHz, 双nano SIM"},
            {"method_id": "WiFi", "details": "WiFi 6, 2.4/5GHz"},
            {"method_id": "Ethernet", "details": "1× WAN + 4× LAN 千兆 (PoE)"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "BACnet/IP"}, {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "9-36V DC"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "Modbus RTU/ASC"},
            {"interface_name": "RS232", "quantity": 1, "description": "Console调试"},
        ],
        "specs": {
            "processor": "ARM Cortex-A53 四核", "ip_rating": "IP30",
            "dimensions": "220×180×44mm", "operating_temp": "-40°C~70°C",
        },
    }),
    ("UC50x", "UC50x 多功能数据采集器", "lorawan-controller", "https://www.milesight.cn/wp-content/uploads/2025/03/uc50x-1.png", {
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "ModbusRTU"}],
        "power_supplies": [{"power_id": "DC", "voltage_range": "9-27V DC"}],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "Modbus RTU, 最多128设备"},
            {"interface_name": "通用输入(UI)", "quantity": 4, "description": "0-10V/4-20mA/PT100/脉冲"},
            {"interface_name": "数字输入(DI)", "quantity": 4, "description": "干接点/脉冲计数"},
            {"interface_name": "数字输出(DO)", "quantity": 2, "description": "继电器"},
        ],
        "specs": {
            "ip_rating": "IP30", "dimensions": "90×87×28mm", "operating_temp": "-20°C~55°C",
        },
    }),
    ("VS121", "VS121 空间人数传感器", "lorawan-sensor", "https://www.milesight.cn/wp-content/uploads/2023/05/vs121-right.png", {
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [{"power_id": "USB-C", "voltage_range": "5V/1A"}],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "7m直径", "accuracy": "95%+", "resolution": ""},
        ],
        "specs": {
            "nfc_config": True, "ip_rating": "IP30", "dimensions": "109×80×18mm",
            "weight": "86g", "operating_temp": "-20°C~55°C",
        },
    }),
]


def resolve_ids(product_data):
    """Replace string IDs with actual dict IDs."""
    data = product_data.copy()

    # Resolve comm_methods
    resolved_methods = []
    for cm in data.get("comm_methods", []):
        method_id = COMM_METHOD_MAP.get(cm.get("method_id", ""))
        if method_id:
            resolved_methods.append({"method_id": method_id, "details": cm.get("details", "")})
    data["comm_methods"] = resolved_methods

    # Resolve comm_protocols
    resolved_protocols = []
    for cp in data.get("comm_protocols", []):
        protocol_id = PROTOCOL_MAP.get(cp.get("protocol_id", ""))
        if protocol_id:
            resolved_protocols.append({"protocol_id": protocol_id, "direction": cp.get("direction", "both")})
    data["comm_protocols"] = resolved_protocols

    # Resolve power_supplies
    resolved_power = []
    for ps in data.get("power_supplies", []):
        power_id = POWER_MAP.get(ps.get("power_id", ""))
        if power_id:
            resolved_power.append({
                "power_id": power_id,
                "voltage_range": ps.get("voltage_range", ""),
                "battery_life": ps.get("battery_life", ""),
            })
    data["power_supplies"] = resolved_power

    # Resolve sensor_capabilities
    resolved_caps = []
    for sc in data.get("sensor_capabilities", []):
        metric_name = sc.get("metric_id", "")
        metric_id = None
        # Find metric by name
        resp = api_call("/dicts/sensor-metrics")
        for m in resp.get("sensor_metrics", []):
            if m["name"] == metric_name:
                metric_id = m["id"]
                break
        if metric_id:
            resolved_caps.append({
                "metric_id": metric_id,
                "measure_range": sc.get("measure_range", ""),
                "accuracy": sc.get("accuracy", ""),
                "resolution": sc.get("resolution", ""),
            })
    data["sensor_capabilities"] = resolved_caps

    return data


def download_image(url):
    """Download image and save to local storage via API."""
    try:
        resp = api_call("/products/download-image", "POST", {"url": url})
        if resp and "url" in resp:
            return resp["url"]
    except Exception as e:
        print(f"    Image download failed: {e}")
    return ""


def import_product(model, name, cat_id, image_url, data):
    """Create a product via API."""
    resolved = resolve_ids(data)

    # Download product image
    images = []
    if image_url:
        print(f"    Downloading image...")
        local_url = download_image(image_url)
        if local_url:
            images = [{"url": local_url, "is_primary": True, "sort_order": 0}]

    payload = {
        "model": model,
        "name": name,
        "category_id": cat_id,
        "manufacturer_id": MANUFACTURER_MAP.get("Milesight"),
        "status": "active",
        "image_url": images[0]["url"] if images else "",
        "product_url": f"https://www.milesight.cn/",
        **resolved,
    }

    res = api_call("/products", "POST", payload)
    if res:
        pid = res["product"]["id"]
        print(f"    Created: {name} (id={pid})")
        return pid
    else:
        print(f"    FAILED: {name}")
        return None


def main():
    print("=" * 60)
    print("Milesight v2 Product Import")
    print("=" * 60)

    # Check API
    try:
        http_requests.get(f"{API_BASE}/health", timeout=5)
    except Exception as e:
        print(f"ERROR: Cannot reach API. {e}")
        sys.exit(1)

    print("\n[1/3] Loading dict maps...")
    load_dict_maps()
    print(f"  Comm methods: {len(COMM_METHOD_MAP)}")
    print(f"  Protocols: {len(PROTOCOL_MAP)}")
    print(f"  Power: {len(POWER_MAP)}")
    print(f"  Manufacturers: {len(MANUFACTURER_MAP)}")

    print("\n[2/3] Creating categories...")
    cat_map = setup_categories()

    print("\n[3/3] Importing products...")
    created = 0
    for model, name, cat_slug, image_url, data in PRODUCTS:
        cat_id = cat_map.get(cat_slug)
        if not cat_id:
            print(f"  SKIP {model}: category '{cat_slug}' not found")
            continue
        print(f"  {model} - {name}")
        pid = import_product(model, name, cat_id, image_url, data)
        if pid:
            created += 1
        time.sleep(0.5)

    print(f"\nDone! Created {created} products")


if __name__ == "__main__":
    main()
