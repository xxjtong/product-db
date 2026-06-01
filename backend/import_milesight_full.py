"""
Full Milesight product import script for v2 schema.
Scrapes product pages from milesight.cn, extracts specs, and imports via API.
Existing products (matched by model) are updated; new products are created.
"""
import sys, os, json, time, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Clear proxy settings for localhost API calls
for k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(k, None)
os.environ['no_proxy'] = 'localhost,127.0.0.1'

import requests as http_requests
from bs4 import BeautifulSoup

API_BASE = "http://localhost:8000/api"
HEADERS = {"Content-Type": "application/json"}

# Dict ID maps
COMM_METHOD_MAP = {}
PROTOCOL_MAP = {}
POWER_MAP = {}
SENSOR_METRIC_MAP = {}
MANUFACTURER_ID = None
CATEGORY_MAP = {}  # slug -> id

# All known product page URLs from the website product index
PRODUCT_PAGES = {
    # Gateways
    "lorawan-gateway": [
        ("UG67", "https://www.milesight.cn/lorawan/gateway/ug67/"),
        ("UG65", "https://www.milesight.cn/lorawan/gateway/ug65/"),
        ("UG63", "https://www.milesight.cn/lorawan/gateway/ug63/"),
        ("UG56", "https://www.milesight.cn/lorawan/gateway/ug56/"),
        ("EG71", "https://www.milesight.cn/lorawan/gateway/eg71/"),
    ],
    # LoRaWAN Sensors - AM series
    "lorawan-sensor": [
        ("AM307", "https://www.milesight.cn/lorawan/sensor/am300/"),  # AM300 series page has AM307/308/319
        ("EM300-TH", "https://www.milesight.cn/lorawan/sensor/em300-th/"),
        ("EM300-SLD", "https://www.milesight.cn/lorawan/sensor/em300-sldzld/"),
        ("EM300-ZLD", "https://www.milesight.cn/lorawan/sensor/em300-sldzld/"),
        ("EM300-MLD", "https://www.milesight.cn/lorawan/sensor/em300-mld/"),
        ("EM300-MCS", "https://www.milesight.cn/lorawan/sensor/em300-mcs/"),
        ("EM300-DI", "https://www.milesight.cn/lorawan/sensor/em300-di/"),
        ("EM320-TILT", "https://www.milesight.cn/lorawan/sensor/em320-tilt/"),
        ("EM320-TH", "https://www.milesight.cn/lorawan/sensor/em320-th/"),
        ("EM400-MUD", "https://www.milesight.cn/lorawan/sensor/em400-mud/"),
        ("EM400-TLD", "https://www.milesight.cn/lorawan/sensor/em400-tld/"),
        ("EM400-UDL", "https://www.milesight.cn/lorawan/sensor/em400-udl/"),
        ("EM410-RDL", "https://www.milesight.cn/lorawan/sensor/em410-rdl/"),
        ("EM500-PP", "https://www.milesight.cn/lorawan/sensor/em500-pp/"),
        ("EM500-PT100", "https://www.milesight.cn/lorawan/sensor/em500-pt100/"),
        ("EM500-LGT", "https://www.milesight.cn/lorawan/sensor/em500-lgt/"),
        ("EM500-SMTC", "https://www.milesight.cn/lorawan/sensor/em500-smtc/"),
        ("EM500-SWL", "https://www.milesight.cn/lorawan/sensor/em500-swl/"),
        ("EM500-UDL", "https://www.milesight.cn/lorawan/sensor/em500-udl/"),
        ("EM500-CO2", "https://www.milesight.cn/lorawan/sensor/em500-co2/"),
        ("VS121", "https://www.milesight.cn/lorawan/sensor/vs121/"),
        ("VS321", "https://www.milesight.cn/lorawan/sensor/vs321/"),
        ("VS125", "https://www.milesight.cn/lorawan/sensor/vs125/"),
        ("VS133", "https://www.milesight.cn/lorawan/sensor/vs133/"),
        ("VS135", "https://www.milesight.cn/lorawan/sensor/vs135/"),
        ("VS330", "https://www.milesight.cn/lorawan/sensor/vs330/"),
        ("VS340", "https://www.milesight.cn/lorawan/sensor/vs340/"),
        ("VS350", "https://www.milesight.cn/lorawan/sensor/vs350/"),
        ("VS351", "https://www.milesight.cn/lorawan/sensor/vs351/"),
        ("VS360", "https://www.milesight.cn/lorawan/sensor/vs360/"),
        ("VS361", "https://www.milesight.cn/lorawan/sensor/vs361/"),
        ("VS370", "https://www.milesight.cn/lorawan/sensor/vs370/"),
        ("VS373", "https://www.milesight.cn/lorawan/sensor/vs373/"),
        ("WS201", "https://www.milesight.cn/lorawan/sensor/ws201/"),
        ("WS202", "https://www.milesight.cn/lorawan/sensor/ws202/"),
        ("WS203", "https://www.milesight.cn/lorawan/sensor/ws203/"),
        ("WS303", "https://www.milesight.cn/lorawan/sensor/ws303/"),
        ("WS302", "https://www.milesight.cn/lorawan/sensor/ws302/"),
        ("TS101", "https://www.milesight.cn/lorawan/sensor/ts101/"),
        ("TS201", "https://www.milesight.cn/lorawan/sensor/ts201/"),
        ("CTH01", "https://www.milesight.cn/lorawan/sensor/cth01/"),
        ("CT101", "https://www.milesight.cn/lorawan/sensor/ct10x/"),
        ("GS301", "https://www.milesight.cn/lorawan/sensor/gs301/"),
        ("GS524N", "https://www.milesight.cn/lorawan/sensor/gs524n/"),
        ("AT101", "https://www.milesight.cn/lorawan/sensor/at101/"),
        ("WTS506", "https://www.milesight.cn/lorawan/sensor/wts506/"),
    ],
    # LoRaWAN Nodes/Actuators
    "lorawan-node": [
        ("WS101", "https://www.milesight.cn/lorawan/node/ws101/"),
        ("WS136", "https://www.milesight.cn/lorawan/node/ws136ws156/"),
        ("WS50x", "https://www.milesight.cn/lorawan/sensor/ws50x/"),
        ("WS51x", "https://www.milesight.cn/lorawan/node/ws51x/"),
        ("WS52x", "https://www.milesight.cn/lorawan/node/ws52x/"),
        ("WS558", "https://www.milesight.cn/lorawan/node/ws558/"),
        ("ACC10x", "https://www.milesight.cn/4g/node/acc10x/"),
    ],
    # Controllers
    "lorawan-controller": [
        ("UC50x", "https://www.milesight.cn/lorawan/controller/uc50x/"),
        ("UC51x", "https://www.milesight.cn/lorawan/controller/uc51x/"),
        ("UC521", "https://www.milesight.cn/lorawan/controller/uc521/"),
        ("UC100", "https://www.milesight.cn/lorawan/dtu/uc100/"),
        ("UC1152", "https://www.milesight.cn/lorawan/dtu/uc11xx/"),
    ],
    # Cellular
    "cellular-router": [
        ("UR75", "https://www.milesight.cn/cellular/router/ur75-5g/"),
        ("UR32", "https://www.milesight.cn/cellular/router/ur3x/"),
    ],
    "cellular-cpe": [
        ("UF51", "https://www.milesight.cn/cellular/5g/uf51/"),
    ],
    # Security
    "sensing-camera": [
        ("SC541", "https://www.milesight.cn/sensing-camera/x1-sc541/"),
    ],
    # Tools
    "tool": [
        ("FT101", "https://www.milesight.cn/lorawan/node/ft101/"),
        ("SCT01", "https://www.milesight.cn/lorawan/node/sct01/"),
    ],
    # Display
    "lorawan-sensor_display": [  # DS3604 goes to lorawan-sensor category
        ("DS3604", "https://www.milesight.cn/iot-display/ds3604/"),
    ],
    # NB-IoT variants
    "nbiot-sensor": [
        ("EM300-TH-NB", "https://www.milesight.cn/nbiot/sensor/em300-th/"),
        ("EM300-SLD-NB", "https://www.milesight.cn/nbiot/sensor/em300-sldzld/"),
        ("EM300-ZLD-NB", "https://www.milesight.cn/nbiot/sensor/em300-sldzld/"),
        ("EM300-MCS-NB", "https://www.milesight.cn/nbiot/sensor/em300-mcs/"),
    ],
}

# Pre-built product data for products we've already scraped in detail.
# This allows instant import without web scraping for known products.
# Models not in this dict will be scraped from the website.
PREBUILT = {
    "UG67": {
        "name": "UG67 室外型基站网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/01/ug67-product-1.png",
        "comm_methods": [
            {"method_id": "Ethernet", "details": "1× 10/100/1000Mbps (PoE)"},
            {"method_id": "LoRaWAN", "details": "8通道, CN470"},
            {"method_id": "4G", "details": "LTE CAT4, 2FF SIM"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "BACnet/IP"}, {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "12V DC (M12航插)"},
            {"power_id": "PoE", "voltage_range": "802.3af"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "Modbus RTU/ASC"},
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试"},
            {"interface_name": "GPS", "quantity": 1, "description": "内置GPS定位"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "processor": "4核 1.5GHz ARM Cortex-A53", "memory": "512MB DDR4", "flash_storage": "8GB eMMC",
            "lora_chipset": "Semtech SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "20dBm", "rx_sensitivity": "-140dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP67", "dimensions": "240×164×90.9mm", "weight": "1463g",
            "operating_temp": "-40°C~70°C", "avg_power": "3.6W", "peak_power": "4.8W",
            "mounting": "壁挂/抱杆",
        },
    },
    "UG65": {
        "name": "UG65 室内型基站网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/ug65-product-1.png",
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
        "sensor_capabilities": [],
        "specs": {
            "processor": "4核 1.5GHz ARM Cortex-A53", "memory": "512MB DDR4", "flash_storage": "8GB eMMC",
            "lora_chipset": "Semtech SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "20dBm", "rx_sensitivity": "-140dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP65", "dimensions": "180×110×55.5mm", "weight": "548g",
            "operating_temp": "-40°C~70°C", "avg_power": "2.9W", "peak_power": "4.2W",
            "mounting": "桌面/壁挂/抱杆",
        },
    },
    "UG63": {
        "name": "UG63 轻量级室内网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/12/ug63-v2-front.png",
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
        "hardware_interfaces": [
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "processor": "1核 ARM Cortex-A7", "memory": "256MB DDR2", "flash_storage": "256MB NAND",
            "lora_chipset": "Semtech SX1308", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "20dBm", "rx_sensitivity": "-139dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 500, "built_in_ns": True, "docker": False,
            "ip_rating": "IP30", "dimensions": "135×115×42mm", "weight": "350g",
            "operating_temp": "-20°C~55°C", "avg_power": "2.5W", "peak_power": "3.5W",
            "mounting": "桌面/壁挂",
        },
    },
    "UG56": {
        "name": "UG56 室内型基站网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/09/UG56-1.png",
        "comm_methods": [
            {"method_id": "Ethernet", "details": "1× 10/100Mbps (PoE)"},
            {"method_id": "LoRaWAN", "details": "8通道, CN470, 27dBm"},
            {"method_id": "WiFi", "details": "802.11 b/g/n, 2.4GHz"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "BACnet/IP"}, {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3af"},
            {"power_id": "USB-C", "voltage_range": "5V/2A"},
        ],
        "hardware_interfaces": [
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "processor": "4核 1.3GHz ARM Cortex-A35", "memory": "512MB DDR3", "flash_storage": "8GB eMMC",
            "lora_chipset": "SX1302", "lora_channels": 8, "frequency_band": "CN470",
            "tx_power": "27dBm", "rx_sensitivity": "-140dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP30", "dimensions": "110×75×24mm", "weight": "186g",
            "operating_temp": "-20°C~60°C", "mounting": "桌面/壁挂",
        },
    },
    "EG71": {
        "name": "EG71 楼宇物联网网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2026/01/product-lorawan-node-eg71-banner-1.png",
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
            {"protocol_id": "SNMP", "direction": "both"},
            {"protocol_id": "SSH", "direction": "both"},
            {"protocol_id": "VPN", "direction": "both"},
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
            "tx_power": "27dBm", "rx_sensitivity": "-140dBm", "lora_class": "Class A/B/C",
            "max_endpoints": 2000, "built_in_ns": True, "docker": True,
            "ip_rating": "IP30", "dimensions": "123×90×36mm", "weight": "375.6g",
            "operating_temp": "-40°C~60°C", "avg_power": "8.2W", "peak_power": "11.24W",
            "mounting": "壁挂/DIN导轨",
        },
    },
    "AM307": {
        "name": "AM307 多合一室内环境监测传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/09/am300-1.png",
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
    },
    "EM300-TH": {
        "name": "EM300-TH 温湿度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em300-th-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
        ],
        "specs": {
            "nfc_config": True, "ip_rating": "IP67", "dimensions": "88.5×85.3×27mm",
            "weight": "", "operating_temp": "-30°C~70°C",
        },
    },
    "EM300-SLD": {
        "name": "EM300-SLD 点式水浸传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em300-sld-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "水浸", "measure_range": "两点检测", "accuracy": "≥0.3mm水位触发", "resolution": ""},
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.6×85.2×27mm", "operating_temp": "-30°C~70°C"},
    },
    "EM300-ZLD": {
        "name": "EM300-ZLD 绳式水浸传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em300-zld-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "水浸", "measure_range": "范围检测(绳长3m)", "accuracy": "≥0.3mm水位触发", "resolution": ""},
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.6×85.2×27mm", "operating_temp": "-30°C~70°C"},
    },
    "EM300-MLD": {
        "name": "EM300-MLD 贴片式水浸传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/08/em300-mld-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "水浸", "measure_range": "面积检测(40×40cm感应膜)", "accuracy": "≥0.3mm水位触发", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.6×85.2×27mm", "operating_temp": "-30°C~70°C"},
    },
    "EM300-MCS": {
        "name": "EM300-MCS 门磁感应传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em300-mcs-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "门磁", "measure_range": "感应距离20~30mm", "accuracy": "", "resolution": ""},
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.6×85.2×27mm", "operating_temp": "-30°C~70°C"},
    },
    "EM300-DI": {
        "name": "EM300-DI 脉冲计数器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/11/em300-di.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×4000mAh ER18505", "battery_life": ">10年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "DI", "quantity": 1, "description": "干接点/脉冲计数, 最大2kHz"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.6×85.2×27mm", "weight": "145g", "operating_temp": "-30°C~70°C"},
    },
    "EM320-TILT": {
        "name": "EM320-TILT 倾斜传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/09/em320-tilt-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": ">3年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "倾斜", "measure_range": "-90°~90° (3轴)", "accuracy": "±1°", "resolution": "0.01°"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "85×58×18mm", "operating_temp": "-30°C~60°C"},
    },
    "EM320-TH": {
        "name": "EM320-TH 温湿度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/12/em320-th-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-30°C~60°C", "accuracy": "±0.2°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "85×58×18mm", "operating_temp": "-30°C~60°C"},
    },
    "EM400-MUD": {
        "name": "EM400-MUD 多功能超声波测距传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/02/em400-mud-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×9000mAh ER26500", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "3~450cm", "accuracy": "±(1+0.3%×S)cm", "resolution": "1mm"},
            {"metric_id": "温度", "measure_range": "-40~125°C", "accuracy": "", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "118×65×30mm", "operating_temp": "-30°C~70°C"},
    },
    "EM400-TLD": {
        "name": "EM400-TLD ToF激光测距传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/02/em400-tld-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×9000mAh ER26500", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "2~350cm (ToF激光)", "accuracy": "±2cm", "resolution": "1mm"},
            {"metric_id": "温度", "measure_range": "-40~125°C", "accuracy": "", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "118×65×30mm", "operating_temp": "-30°C~70°C"},
    },
    "EM400-UDL": {
        "name": "EM400-UDL 超声波测距传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/02/em400-udl-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×9000mAh ER26500", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "25~1000cm (超声波)", "accuracy": "±(1+0.3%×S)cm", "resolution": "1mm"},
            {"metric_id": "温度", "measure_range": "-40~125°C", "accuracy": "", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "118×65×30mm", "operating_temp": "-30°C~70°C"},
    },
    "EM410-RDL": {
        "name": "EM410-RDL 雷达测距传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/em410-slide.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": "7年(1440min上报)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "0.3~12m (毫米波雷达)", "accuracy": "±2mm", "resolution": "1mm"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "R100×85mm", "weight": "400g", "operating_temp": "-40°C~70°C"},
    },
    "EM500-PP": {
        "name": "EM500-PP 管道压力传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-pp-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "压力", "measure_range": "0~1600kPa (16Bar)", "accuracy": "±0.5% FS", "resolution": "1kPa"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.4×71×69.5mm", "operating_temp": "-30°C~70°C"},
    },
    "EM500-PT100": {
        "name": "EM500-PT100 温度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-pt100-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-200°C~800°C (PT100铂电阻)", "accuracy": "±0.5~2°C (依型号)", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.4×71×69.5mm", "operating_temp": "-30°C~70°C"},
    },
    "EM500-LGT": {
        "name": "EM500-LGT 光照传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-lgt-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "光照", "measure_range": "0~100000lux", "accuracy": "±3%", "resolution": "1lux"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.4×71×69.5mm", "operating_temp": "-30°C~60°C"},
    },
    "EM500-SMTC": {
        "name": "EM500-SMTC 土壤水分温度电导率传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-smt-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~80°C", "accuracy": "±0.5°C", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.4×71×69.5mm", "operating_temp": "-30°C~70°C"},
    },
    "EM500-SWL": {
        "name": "EM500-SWL 投入式液位传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-swl-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "液位", "measure_range": "0~3/5/10m (可定制至200m)", "accuracy": "±0.5% FS", "resolution": "0.01m"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "105.4×71×69.5mm", "operating_temp": "-30°C~70°C"},
    },
    "EM500-UDL": {
        "name": "EM500-UDL 超声波测距传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-udl-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "0.25~10m (超声波)", "accuracy": "±1% FS", "resolution": "1mm"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "156.1×71×69.5mm", "operating_temp": "-30°C~65°C"},
    },
    "EM500-CO2": {
        "name": "EM500-CO2 二氧化碳传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/08/em500-co2-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "19000mAh ER34615", "battery_life": ">10年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "CO2", "measure_range": "400~5000ppm", "accuracy": "±(30ppm+3%)", "resolution": "1ppm"},
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
            {"metric_id": "气压", "measure_range": "300~1100hPa", "accuracy": "±1hPa", "resolution": "0.1hPa"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "147.9×71×69.5mm", "operating_temp": "-30°C~70°C"},
    },
    "VS121": {
        "name": "VS121 空间人数传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/05/vs121-right.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [{"power_id": "USB-C", "voltage_range": "5V/2A"}],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "7m直径", "accuracy": "95%+", "resolution": ""},
        ],
        "specs": {"nfc_config": False, "ip_rating": "IP30", "dimensions": "85×85×20mm", "weight": "126.9g", "operating_temp": "-5°C~55°C"},
    },
    "UR75": {
        "name": "UR75 5G工业路由器",
        "category_slug": "cellular-router",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/10/ur75-5g-front.png",
        "comm_methods": [
            {"method_id": "5G", "details": "NR Sub-6GHz, 双nano SIM"},
            {"method_id": "WiFi", "details": "WiFi 6, 2.4/5GHz (可选)"},
            {"method_id": "Ethernet", "details": "1×WAN + 4×LAN 千兆 (PoE可选)"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}, {"protocol_id": "HTTPS"},
            {"protocol_id": "ModbusTCP"}, {"protocol_id": "ModbusRTU"},
            {"protocol_id": "SNMP"}, {"protocol_id": "SSH"}, {"protocol_id": "VPN"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "9-48V DC"},
            {"power_id": "PoE", "voltage_range": "802.3af/at"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "3.5mm端子排, 300~230400bps"},
            {"interface_name": "RS232", "quantity": 1, "description": "3.5mm端子排"},
            {"interface_name": "DI", "quantity": 1, "description": "干接点, 电气隔离"},
            {"interface_name": "DO", "quantity": 1, "description": "湿接点, 0.3A@30VDC"},
            {"interface_name": "USB", "quantity": 1, "description": "Type-C (USB 3.0)"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "processor": "4核 2GHz ARM Cortex-A55", "memory": "1GB LPDDR4x", "flash_storage": "1GB NAND",
            "ip_rating": "IP30", "dimensions": "135×115×36.4mm",
            "operating_temp": "-40°C~70°C", "mounting": "桌面/DIN导轨/壁挂",
        },
    },
    "UC50x": {
        "name": "UC50x 多功能数据采集器",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/03/uc50x-1.png",
        "comm_methods": [
            {"method_id": "LoRaWAN", "details": "CN470"},
            {"method_id": "4G", "details": "LTE CAT1, Micro SIM"},
        ],
        "comm_protocols": [
            {"protocol_id": "MQTT"}, {"protocol_id": "ModbusRTU"},
        ],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "5~24VDC (M12航插)"},
            {"power_id": "Battery", "voltage_range": "2×2550mAh (UC501太阳能+充电电池) / 3×9000mAh ER26500 (UC502)", "battery_life": "UC501: 太阳能 / UC502: >10年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485/RS232", "quantity": 1, "description": "软件切换, 1200~115200bps"},
            {"interface_name": "SDI-12", "quantity": 1, "description": "SDI-12 V1.4"},
            {"interface_name": "AI", "quantity": 2, "description": "4-20mA/0-10V(拨码切换), 12位"},
            {"interface_name": "GPIO", "quantity": 2, "description": "DI/DO/脉冲计数"},
            {"interface_name": "USB", "quantity": 1, "description": "Type-C 调试配置"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP67", "dimensions": "116×116×45.5mm", "operating_temp": "-20°C~60°C(UC501) / -30°C~70°C(UC502)"},
    },
    "TS101": {
        "name": "TS101 探针温度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/04/ts101-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×4000mAh ER18505", "battery_life": "10年(1小时上报)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±0.5°C", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "92×92×26mm (主体)", "operating_temp": "-30°C~70°C"},
    },
    "CTH01": {
        "name": "CTH01 智能电力监测终端",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2026/03/product-lorawan-sensor-cth01-banner-1-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "12V DC (±10%)"},
        ],
        "hardware_interfaces": [
            {"interface_name": "电压接口", "quantity": 3, "description": "3相/单相, 100~500V AC"},
            {"interface_name": "电流接口", "quantity": 12, "description": "RJ11, 兼容开口CT和罗氏线圈"},
            {"interface_name": "NTC温度", "quantity": 1, "description": "外接NTC, -20~100°C"},
        ],
        "sensor_capabilities": [
            {"metric_id": "电流", "measure_range": "100~4000A (依CT)", "accuracy": "±1% (IEC 62053-21)", "resolution": "1mA"},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "49.3×98×90mm", "weight": "165g", "operating_temp": "-20°C~70°C", "mounting": "DIN 35导轨"},
    },
    "CT101": {
        "name": "CT101/103/105 智能电流互感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/02/ct10x-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "感应自供电 (USB-C备用)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "电流", "measure_range": "CT101:100A / CT103:250A / CT105:500A", "accuracy": "±1%", "resolution": "1mA"},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "主体38×34.5×16mm", "operating_temp": "-20°C~70°C(主体)/-40°C~55°C(探头)"},
    },
    "GS301": {
        "name": "GS301 卫生间异味传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/12/gs301-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "4×4000mAh ER18505", "battery_life": ">3年(10min上报)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~85°C", "accuracy": "±0.2°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "120×85×32.5mm", "operating_temp": "-40°C~55°C"},
    },
    "GS524N": {
        "name": "GS524N 独立式光电感烟火灾探测报警器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/08/gs524n-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×CR17450 2400mAh", "battery_life": ">3年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-20°C~70°C", "accuracy": "±3°C", "resolution": "1°C"},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "Ø104×39.9mm", "weight": "140g", "operating_temp": "-10°C~50°C"},
    },
    "AT101": {
        "name": "AT101 室外资产定位传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/05/at101-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "4×2700mAh ER14505", "battery_life": ">15年(2次/天)"},
        ],
        "hardware_interfaces": [
            {"interface_name": "GNSS", "quantity": 1, "description": "GPS/GLONASS/Galileo/北斗"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~125°C", "accuracy": "", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "110×70×30mm", "weight": "202g", "operating_temp": "-30°C~70°C"},
    },
    "WTS506": {
        "name": "WTS506 气象站",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/09/wts-product1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470, Class C"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "太阳能15W+2×2550mAh充电电池"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~85°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
            {"metric_id": "气压", "measure_range": "500~1100hPa", "accuracy": "±0.5hPa", "resolution": "0.1hPa"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP65", "dimensions": "传感器ф160×263×ф73mm, 主机116×116×45.5mm", "weight": "2.15kg(传感器)", "operating_temp": "-40°C~85°C"},
    },
    "DS3604": {
        "name": "DS3604 智慧电子墨水屏",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/01/ds3604-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "3×CR2450 590mAh", "battery_life": "Class A:~5年 / Class B:~1年"},
        ],
        "sensor_capabilities": [],
        "specs": {
            "nfc_config": True, "screen": "4.2寸三色电子墨水屏(400×300)", "data_storage": "",
            "ip_rating": "IP30", "dimensions": "99×87×10.5mm", "operating_temp": "0°C~40°C",
        },
    },
    "WS50x": {
        "name": "WS50x 智能开关面板",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/11/ws50x-upPC-onekey.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "90-250VAC 50/60Hz"},
        ],
        "hardware_interfaces": [
            {"interface_name": "继电器输出", "quantity": 3, "description": "1/2/3键, 每路10A(阻性)/5A(容性)"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "86×86×41mm", "operating_temp": "-20°C~60°C"},
    },
    "VS321": {
        "name": "VS321 无线空间人数传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/06/product-lorawan-sensor-vs321-banner-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "4×2700mAh ER14505", "battery_life": "~7.5年(SF10)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "129°×93° FOV, 2.4-4m安装", "accuracy": "95%", "resolution": ""},
            {"metric_id": "温度", "measure_range": "-40°C~125°C", "accuracy": "±1°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2.5%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": False, "ip_rating": "IP30", "dimensions": "100×100×26mm", "operating_temp": "0°C~30°C"},
    },
    "VS330": {
        "name": "VS330 卫生间占用传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/01/vs330-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "3×4000mAh ER18505", "battery_life": ">3年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人体存在", "measure_range": "ToF+PIR双技术, 4~350cm", "accuracy": ">99.5%", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "Ø100×24mm", "operating_temp": "-20°C~60°C"},
    },
    "VS340": {
        "name": "VS340 工位占用传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/06/vs340-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×4000mAh ER18505", "battery_life": "4年(100次/天)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人体存在", "measure_range": "PIR检测, H107°×V107°, 1m", "accuracy": "95%", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "73×73×22mm", "weight": "90g", "operating_temp": "-20°C~60°C"},
    },
    "VS370": {
        "name": "VS370 雷达人体存在传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/vs370-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "~5年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人体存在", "measure_range": "24GHz雷达, 150°, 7.5m移动/4.8m微动", "accuracy": "99%", "resolution": ""},
            {"metric_id": "光照", "measure_range": "1~8000lux (明/暗判断)", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "Ø70×48.5mm", "weight": "89.6g", "operating_temp": "0°C~30°C"},
    },
    "WS201": {
        "name": "WS201 智能余量监测传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/03/ws201-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×CR2450 590mAh", "battery_life": "~2年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "1~55cm (ToF红外测距)", "accuracy": "±1cm", "resolution": "1mm"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "66×38×12mm", "operating_temp": "-20°C~60°C"},
    },
    "WS202": {
        "name": "WS202 PIR&光照传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/09/ws202-product-im3.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×1650mAh ER14335", "battery_life": "~4年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "光照", "measure_range": "明/暗状态(可设阈值)", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "50×50×23.8mm", "operating_temp": "-30°C~60°C"},
    },
    "WS203": {
        "name": "WS203 PIR&温湿度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/08/ws203-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×4000mAh ER18505", "battery_life": "~5年(100次/天)"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-20°C~60°C", "accuracy": "±0.2°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±2%RH", "resolution": "0.5%RH"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "73×73×22mm", "weight": "90g", "operating_temp": "-20°C~60°C"},
    },
    "WS303": {
        "name": "WS303 智能水浸传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/03/ws303-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×CR2450 590mAh", "battery_life": "5年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "水浸", "measure_range": "两点检测", "accuracy": "≥0.5mm水位触发", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "Ø63×14mm", "operating_temp": "-10°C~60°C"},
    },
    "WS302": {
        "name": "WS302 噪声传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2022/07/ws302-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "4年"},
        ],
        "sensor_capabilities": [
            {"metric_id": "噪声", "measure_range": "30~120dBA", "accuracy": "±3dB", "resolution": "0.1dB"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "68×65×20.5mm", "operating_temp": "-20°C~60°C"},
    },
    "WS101": {
        "name": "WS101 智能按键/一键报警器",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2021/06/ws101-product-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×1650mAh ER14335", "battery_life": ">5年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "按键", "quantity": 1, "description": "单击/双击/长按, LED+蜂鸣器反馈"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "50×50×18mm", "operating_temp": "-30°C~60°C"},
    },
    # === Remaining products ===
    "AM319": {
        "name": "AM319 多合一室内环境监测传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/09/am300-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "~2年"},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-20°C~60°C", "accuracy": "±0.3°C", "resolution": "0.1°C"},
            {"metric_id": "湿度", "measure_range": "0~100%RH", "accuracy": "±3%RH", "resolution": "0.5%RH"},
            {"metric_id": "CO2", "measure_range": "0~5000ppm", "accuracy": "±(30+3%)ppm", "resolution": "1ppm"},
            {"metric_id": "TVOC", "measure_range": "0~60000μg/m³", "accuracy": "", "resolution": "1μg/m³"},
            {"metric_id": "PM2.5", "measure_range": "0~1000μg/m³", "accuracy": "±10μg/m³", "resolution": "1μg/m³"},
            {"metric_id": "气压", "measure_range": "300~1100hPa", "accuracy": "±1hPa", "resolution": "0.1hPa"},
            {"metric_id": "光照", "measure_range": "0~188000lux", "accuracy": "", "resolution": "1lux"},
            {"metric_id": "噪声", "measure_range": "30~120dBA", "accuracy": "±3dB", "resolution": "0.1dB"},
            {"metric_id": "人体存在", "measure_range": "PIR检测", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "112×112×36mm", "weight": "165g", "operating_temp": "-20°C~60°C"},
    },
    "VS125": {
        "name": "VS125 AI双目客流统计传感器",
        "category_slug": "lorawan-sensor_display",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/12/vs125-1.png",
        "comm_methods": [{"method_id": "Ethernet", "details": "10/100Mbps RJ45, PoE"}, {"method_id": "4G", "details": "LTE Cat1(蜂窝版)"}],
        "comm_protocols": [{"protocol_id": "HTTP"}, {"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3af PoE / 12V/1A DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 1, "description": "10/100Mbps PoE"},
            {"interface_name": "DI", "quantity": 1, "description": "开发中"},
            {"interface_name": "DO", "quantity": 2, "description": "继电器输出"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "双目AI, 精度99.8%, 2.2~6m安装高度", "accuracy": "99.8%", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "185×85×34mm", "weight": "275g", "operating_temp": "-20°C~50°C"},
    },
    "VS126": {
        "name": "VS126 AI超高安装客流统计传感器",
        "category_slug": "lorawan-sensor_display",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/12/vs126-1.png",
        "comm_methods": [{"method_id": "Ethernet", "details": "10/100Mbps RJ45, PoE"}, {"method_id": "4G", "details": "LTE(蜂窝版)"}],
        "comm_protocols": [{"protocol_id": "HTTP"}, {"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3af PoE / 12V/1A DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 2, "description": "PoE+级联"},
            {"interface_name": "DI", "quantity": 1, "description": ""},
            {"interface_name": "DO", "quantity": 2, "description": ""},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "双目AI, 6~15m安装高度, 精度99.8%", "accuracy": "99.8%", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "435×75×38.5mm", "weight": "792g", "operating_temp": "-20°C~60°C"},
    },
    "VS133": {
        "name": "VS133 AI ToF人数统计传感器",
        "category_slug": "lorawan-sensor_display",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/vs133-1.png",
        "comm_methods": [{"method_id": "Ethernet", "details": "10/100Mbps RJ45, 802.3at PoE"}],
        "comm_protocols": [{"protocol_id": "HTTP"}, {"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3at PoE", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 1, "description": "10/100Mbps PoE"},
            {"interface_name": "DI", "quantity": 1, "description": "开发中"},
            {"interface_name": "DO", "quantity": 1, "description": ""},
            {"interface_name": "RS485", "quantity": 1, "description": "开发中"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "ToF 940nm, 0.5~3.5m, 精度99.8%", "accuracy": "99.8%, ±3.5cm", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "180×26×72mm", "weight": "226g", "operating_temp": "-20°C~50°C"},
    },
    "VS135": {
        "name": "VS135 AI ToF人数统计传感器Pro",
        "category_slug": "lorawan-sensor_display",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/03/vs135-1.png",
        "comm_methods": [{"method_id": "Ethernet", "details": "10/100Mbps RJ45, 802.3at PoE"}, {"method_id": "4G", "details": "LTE Cat4"}, {"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "HTTP"}, {"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3at PoE / 12V/2A DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 1, "description": "PoE版"},
            {"interface_name": "DI", "quantity": 1, "description": "PoE版"},
            {"interface_name": "DO", "quantity": 1, "description": "SPST继电器, 1A/60VDC"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "ToF 940nm, 标准0.5~3.5m/高装2~6.5m, 精度99.8%", "accuracy": "99.8%, ±3.5cm/±6.5cm", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "200×35×85mm", "weight": "419g", "operating_temp": "-20°C~50°C"},
    },
    "VS351": {
        "name": "VS351 AI热电堆人数统计传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/vs351-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "热电堆+雷达版电池", "battery_life": "~1.6年(30min间隔)"},
            {"power_id": "USB-C", "voltage_range": "Type-C 5V", "battery_life": ""},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "热电堆16×16红外阵列, 2~3m安装, 双向计数", "accuracy": "80~90%", "resolution": ""},
            {"metric_id": "温度", "measure_range": "-30°C~70°C", "accuracy": "±2°C", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "70×68×32mm(主体)", "operating_temp": "-20°C~60°C"},
    },
    "VS360": {
        "name": "VS360 出入口人数统计传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/vs360-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "~3年(主设备, 12h/天)"},
        ],
        "hardware_interfaces": [
            {"interface_name": "OLED", "quantity": 1, "description": "主设备显示屏"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "红外对管, 0.7~1.2m安装, 1.2~3m检测范围, 双向计数", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "76×62×20mm", "operating_temp": "-20°C~50°C"},
    },
    "VS361": {
        "name": "VS361 店外客流统计传感器",
        "category_slug": "lorawan-sensor_display",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/vs361-1.png",
        "comm_methods": [{"method_id": "Ethernet", "details": "PoE供电"}],
        "comm_protocols": [{"protocol_id": "HTTP"}, {"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "PoE", "voltage_range": "802.3af PoE / 12-60V DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "NPN输出", "quantity": 1, "description": "集电极开路, 1mA@5VDC"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "红外漫反射, 1~9m可调, 单向检测", "accuracy": "", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP65", "dimensions": "73.5×80×36mm", "weight": "122g", "operating_temp": "-20°C~50°C"},
    },
    "VS373": {
        "name": "VS373 雷达跌倒检测传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/vs373-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470, Class C"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "USB-C", "voltage_range": "Type-C 5V/3A", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "DO", "quantity": 1, "description": "自定义告警输出"},
            {"interface_name": "蜂鸣器", "quantity": 1, "description": "本地告警"},
        ],
        "sensor_capabilities": [
            {"metric_id": "人体存在", "measure_range": "4D毫米波雷达, 24T/22R天线, 140°×70°, 4×5m²", "accuracy": "跌倒误报<1%", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP65", "dimensions": "110×82×15mm", "weight": "214.5g", "operating_temp": "0°C~50°C"},
    },
    "WS301": {
        "name": "WS301 无线门磁传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/03/ws301-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×1200mAh ER14250", "battery_life": ">5年(30次/天)"},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "门磁", "measure_range": "感应距离<15mm", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "50.5×31×18mm(传感器)", "operating_temp": "-20°C~60°C"},
    },
    "EM310-UDL": {
        "name": "EM310-UDL 超声波测距传感器(已退市)",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/02/em310-udl-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×3500mAh ER17505", "battery_life": ">10年(20次/天)"},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "距离", "measure_range": "3~450cm(盲区3cm)", "accuracy": "±(1+0.3%×S)cm", "resolution": "1mm"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "111×62×40mm", "weight": "168g", "operating_temp": "-15°C~60°C"},
    },
    "EM310-TILT": {
        "name": "EM310-TILT 倾斜传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/09/em310-tilt-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×3500mAh ER17505", "battery_life": ">5年(144次/天)"},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "倾斜", "measure_range": "-90°~90°(X+Y+Z三轴)", "accuracy": "±1°(0~±89°)", "resolution": "0.01°"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "111×62×33mm", "weight": "135g", "operating_temp": "-20°C~60°C"},
    },
    "TS201": {
        "name": "TS201 温度传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/ts201-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×2700mAh ER14505", "battery_life": ">10年(25°C)"},
        ],
        "hardware_interfaces": [
            {"interface_name": "M12航空头", "quantity": 1, "description": "5-PIN防水, DS18B20探头1.5m线"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~125°C", "accuracy": "±0.5°C(10~85°C)", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "58×65×25mm", "operating_temp": "-30°C~55°C"},
    },
    "TS301": {
        "name": "TS301 温度传感器(食品级探头)",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/ts301-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×2700mAh ER14505", "battery_life": ">5年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "探头接口", "quantity": 1, "description": "食品级探头"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-40°C~125°C", "accuracy": "±0.5°C", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "58×65×25mm", "operating_temp": "-30°C~55°C"},
    },
    "SG50": {
        "name": "SG50 超低功耗太阳能网关",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/09/sg50-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "8通道, CN470"}, {"method_id": "4G", "details": "LTE/GSM"}, {"method_id": "WiFi", "details": "802.11b/g/n 2.4GHz(配置)"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "HTTP"}],
        "power_supplies": [
            {"power_id": "Solar", "voltage_range": "12~24V DC太阳能板 + 25000mAh锂电池", "battery_life": "4天(零日照)"},
            {"power_id": "USB-C", "voltage_range": "5V/2A", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "N-type天线", "quantity": 1, "description": "LoRa, 含60cm玻璃钢天线"},
            {"interface_name": "4G天线", "quantity": 1, "description": "与GPS共享外部天线"},
            {"interface_name": "WiFi天线", "quantity": 1, "description": "外部天线"},
            {"interface_name": "Nano SIM", "quantity": 1, "description": "4G"},
            {"interface_name": "USB-C", "quantity": 1, "description": "供电+调试"},
            {"interface_name": "M12航空头", "quantity": 1, "description": "太阳能+DC供电"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP67", "dimensions": "250×157.5×46mm", "weight": "1755g(含电池)", "operating_temp": "-30°C~70°C"},
    },
    "UC51x": {
        "name": "UC51x 电磁阀控制器",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/uc51x-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470, Class A/B/C"}, {"method_id": "4G", "details": "LTE(UC511-4G版)"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "TCP"}],
        "power_supplies": [
            {"power_id": "Solar", "voltage_range": "6V/1.7W太阳能板 + 2×2550mAh充电电池", "battery_life": "ClassA约3年"},
            {"power_id": "DC", "voltage_range": "5~24V DC(外接)", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "电磁阀接口", "quantity": 2, "description": "12V脉冲电磁阀"},
            {"interface_name": "GPIO", "quantity": 2, "description": "干接点, 开关量+脉冲计数"},
            {"interface_name": "M12航空头", "quantity": 2, "description": "含1.5m航空线"},
            {"interface_name": "Type-C", "quantity": 1, "description": "内部配置口"},
        ],
        "sensor_capabilities": [
            {"metric_id": "压力", "measure_range": "0~1600kPa(可选配)", "accuracy": "±0.5%FS", "resolution": "1kPa"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "116×116×45.5mm", "weight": "425g", "operating_temp": "-20°C~60°C"},
    },
    "UC521": {
        "name": "UC521 电动阀控制器",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/uc521-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}, {"method_id": "4G", "details": "LTE(4G版)"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "TCP"}],
        "power_supplies": [
            {"power_id": "Solar", "voltage_range": "6V/1.7W太阳能板 + 3×2550mAh充电电池", "battery_life": "ClassA约2个月(无光照)"},
        ],
        "hardware_interfaces": [
            {"interface_name": "电动阀接口", "quantity": 2, "description": "DC+/DC-, 12V"},
            {"interface_name": "脉冲监测", "quantity": 2, "description": "流量计/水表"},
            {"interface_name": "压力采集", "quantity": 2, "description": "可选配"},
            {"interface_name": "M12航空头", "quantity": 2, "description": "防水连接器"},
        ],
        "sensor_capabilities": [
            {"metric_id": "压力", "measure_range": "0~1600kPa(可选配)", "accuracy": "±0.5%FS", "resolution": "1kPa"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP67", "dimensions": "116×116×45.5mm", "operating_temp": "-20°C~60°C"},
    },
    "UR32": {
        "name": "UR32 4G工业路由器",
        "category_slug": "cellular-router",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/06/ur32-front.png",
        "comm_methods": [{"method_id": "4G", "details": "LTE Cat4"}, {"method_id": "Ethernet", "details": "1×GE WAN, 4×GE LAN"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "VPN"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "12~48V DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45 WAN", "quantity": 1, "description": "GE"},
            {"interface_name": "RJ45 LAN", "quantity": 4, "description": "GE"},
            {"interface_name": "RS232", "quantity": 1, "description": ""},
            {"interface_name": "RS485", "quantity": 1, "description": ""},
            {"interface_name": "DI", "quantity": 1, "description": ""},
            {"interface_name": "DO", "quantity": 1, "description": "继电器"},
            {"interface_name": "SIM", "quantity": 1, "description": "Nano SIM"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "150×114×42mm", "weight": "390g", "operating_temp": "-40°C~70°C"},
    },
    "UR35": {
        "name": "UR35 4G工业路由器",
        "category_slug": "cellular-router",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2023/06/ur35-front.png",
        "comm_methods": [{"method_id": "4G", "details": "LTE Cat6"}, {"method_id": "Ethernet", "details": "1×GE WAN+LAN, 3×GE LAN"}, {"method_id": "WiFi", "details": "802.11b/g/n/ac(可选)"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "VPN"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "12~48V DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 5, "description": "1 WAN+LAN + 3 LAN, GE"},
            {"interface_name": "RS232", "quantity": 1, "description": ""},
            {"interface_name": "RS485", "quantity": 1, "description": ""},
            {"interface_name": "DI", "quantity": 1, "description": ""},
            {"interface_name": "DO", "quantity": 1, "description": "继电器"},
            {"interface_name": "SIM", "quantity": 2, "description": "Nano SIM双卡"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "150×114×42mm", "weight": "420g", "operating_temp": "-40°C~70°C"},
    },
    "UF51": {
        "name": "UF51 5G CPE",
        "category_slug": "cellular-router",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/05/uf51-1.png",
        "comm_methods": [{"method_id": "5G", "details": "NR SA/NSA"}, {"method_id": "Ethernet", "details": "1×GE RJ45"}],
        "comm_protocols": [{"protocol_id": "MQTT"}, {"protocol_id": "VPN"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "12V/2A DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RJ45", "quantity": 1, "description": "GE"},
            {"interface_name": "SIM", "quantity": 1, "description": "Nano SIM"},
            {"interface_name": "5G天线", "quantity": 2, "description": "SMA外接"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "180×140×55mm", "weight": "680g", "operating_temp": "-40°C~70°C"},
    },
    "WS51x": {
        "name": "WS51x 智能插座面板",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/ws51x-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "100~240VAC 50/60Hz", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "插座", "quantity": 1, "description": "10A/16A"},
        ],
        "sensor_capabilities": [
            {"metric_id": "电流", "measure_range": "0~16A", "accuracy": "", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "86×86×39.5mm", "operating_temp": "0°C~45°C"},
    },
    "WS52x": {
        "name": "WS52x 智能移动插座",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/ws52x-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "100~240VAC 50/60Hz", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "插座", "quantity": 1, "description": "10A"},
        ],
        "sensor_capabilities": [
            {"metric_id": "电流", "measure_range": "0~10A", "accuracy": "", "resolution": ""},
        ],
        "specs": {"ip_rating": "IP30", "dimensions": "51×51×63mm", "operating_temp": "0°C~45°C"},
    },
    "WS558": {
        "name": "WS558 智能灯光控制器",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/ws558-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "100~240VAC 50/60Hz", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "继电器输出", "quantity": 1, "description": "灯光控制"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "46×46×23mm(暗装)", "operating_temp": "0°C~45°C"},
    },
    "VS350": {
        "name": "VS350 过道人数统计传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/08/vs350-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "~3年"},
        ],
        "hardware_interfaces": [],
        "sensor_capabilities": [
            {"metric_id": "人数", "measure_range": "红外对管, 0.7~1.2m安装, 双向计数", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "76×62×20mm", "operating_temp": "-20°C~50°C"},
    },
    "WS136": {
        "name": "WS136 智能情景面板",
        "category_slug": "lorawan-node",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/10/ws136-1.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "100~240VAC 50/60Hz", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "按键", "quantity": 6, "description": "6键场景控制"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "86×86×12mm", "operating_temp": "0°C~45°C"},
    },
    "CT303": {
        "name": "CT303/305/310 智能三相电流互感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2025/02/ct3xx-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "1×3600mAh ER18505", "battery_life": "~3年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "互感器接口", "quantity": 3, "description": "三相电流采集"},
        ],
        "sensor_capabilities": [
            {"metric_id": "电流", "measure_range": "0~100A/150A/200A(开口式)", "accuracy": "±1%FS", "resolution": "0.01A"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "110×70×30mm", "operating_temp": "-20°C~60°C"},
    },
    "EM300-CL": {
        "name": "EM300-CL 闭门器传感器",
        "category_slug": "lorawan-sensor",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/09/em300-cl-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "2×2700mAh ER14505", "battery_life": "~4年"},
        ],
        "hardware_interfaces": [
            {"interface_name": "干簧管", "quantity": 1, "description": "门状态检测"},
        ],
        "sensor_capabilities": [
            {"metric_id": "门磁", "measure_range": "开门/关门状态", "accuracy": "", "resolution": ""},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP54", "dimensions": "72×60×22mm", "operating_temp": "-20°C~60°C"},
    },
    "ACC101": {
        "name": "ACC101 智能分体空调控制器",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/acc101-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}, {"method_id": "4G", "details": "LTE(4G版)"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "AC", "voltage_range": "100~240VAC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "红外发射", "quantity": 1, "description": "空调遥控"},
            {"interface_name": "温度探头", "quantity": 1, "description": "回风温度"},
        ],
        "sensor_capabilities": [
            {"metric_id": "温度", "measure_range": "-20°C~60°C", "accuracy": "±0.5°C", "resolution": "0.1°C"},
        ],
        "specs": {"nfc_config": True, "ip_rating": "IP30", "dimensions": "86×86×15mm", "operating_temp": "0°C~45°C"},
    },
    "UC100": {
        "name": "UC100 无线数传终端",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/uc100-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "5~24V DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "表计数据采集"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "95×68×27mm", "weight": "120g", "operating_temp": "-20°C~60°C"},
    },
    "UC1152": {
        "name": "UC1152 无线数传终端(工业级)",
        "category_slug": "lorawan-controller",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/06/uc1152-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "CN470"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "DC", "voltage_range": "5~24V DC", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "RS485", "quantity": 1, "description": "工业级表计数据采集"},
            {"interface_name": "M12航空头", "quantity": 1, "description": "防水连接"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP67", "dimensions": "111×62×40mm", "weight": "180g", "operating_temp": "-30°C~70°C"},
    },
    "FT101": {
        "name": "FT101 多功能路测仪",
        "category_slug": "lorawan-gateway",
        "image_url": "https://www.milesight.cn/wp-content/uploads/2024/03/ft101-front.png",
        "comm_methods": [{"method_id": "LoRaWAN", "details": "多频段扫描"}, {"method_id": "WiFi", "details": "802.11b/g/n"}],
        "comm_protocols": [{"protocol_id": "MQTT"}],
        "power_supplies": [
            {"power_id": "Battery", "voltage_range": "内置锂电池", "battery_life": "~8小时"},
            {"power_id": "USB-C", "voltage_range": "5V/2A", "battery_life": ""},
        ],
        "hardware_interfaces": [
            {"interface_name": "USB-C", "quantity": 1, "description": "供电+数据"},
            {"interface_name": "天线接口", "quantity": 1, "description": "SMA外接"},
        ],
        "sensor_capabilities": [],
        "specs": {"ip_rating": "IP30", "dimensions": "155×77×28mm", "weight": "260g", "operating_temp": "-20°C~60°C"},
    },
}


def api_call(path, method="GET", data=None):
    url = f"{API_BASE}{path}"
    kwargs = {}
    if data is not None:
        kwargs["json"] = data
    try:
        resp = http_requests.request(method, url, **kwargs, timeout=30)
        if resp.status_code >= 400:
            print(f"  API ERROR {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        print(f"  API ERROR: {e}")
        return None


def load_dict_maps():
    global COMM_METHOD_MAP, PROTOCOL_MAP, POWER_MAP, SENSOR_METRIC_MAP, MANUFACTURER_ID

    for name, path in [("comm_methods", "/dicts/comm-methods"), ("comm_protocols", "/dicts/comm-protocols"),
                       ("power_supplies", "/dicts/power-supplies"), ("sensor_metrics", "/dicts/sensor-metrics"),
                       ("manufacturers", "/dicts/manufacturers")]:
        resp = api_call(path)
        if not resp:
            continue
        key = list(resp.keys())[0]
        items = resp[key]
        for item in items:
            if name == "comm_methods":
                COMM_METHOD_MAP[item["name"]] = item["id"]
            elif name == "comm_protocols":
                PROTOCOL_MAP[item["name"]] = item["id"]
            elif name == "power_supplies":
                POWER_MAP[item["name"]] = item["id"]
            elif name == "sensor_metrics":
                SENSOR_METRIC_MAP[item["name"]] = item["id"]
            elif name == "manufacturers":
                if item["name"] == "Milesight":
                    MANUFACTURER_ID = item["id"]


def load_category_map():
    resp = api_call("/categories")
    if resp:
        for c in resp.get("categories", []):
            CATEGORY_MAP[c["slug"]] = c["id"]


def load_existing_products():
    """Get map of model -> product id for upsert."""
    existing = {}
    page = 1
    while True:
        resp = api_call(f"/products?per_page=100&page={page}")
        if not resp:
            break
        for p in resp.get("products", []):
            if p.get("model"):
                existing[p["model"]] = p["id"]
        if len(resp.get("products", [])) < 100:
            break
        page += 1
    return existing


def resolve_ids(product_data):
    """Replace string dict names with actual IDs."""
    data = product_data.copy()

    # Comm methods
    resolved = []
    for cm in data.get("comm_methods", []):
        mid = COMM_METHOD_MAP.get(cm.get("method_id", ""))
        if mid:
            resolved.append({"method_id": mid, "details": cm.get("details", "")})
    data["comm_methods"] = resolved

    # Protocols
    resolved = []
    for cp in data.get("comm_protocols", []):
        pid = PROTOCOL_MAP.get(cp.get("protocol_id", ""))
        if pid:
            resolved.append({"protocol_id": pid, "direction": cp.get("direction", "both")})
    data["comm_protocols"] = resolved

    # Power supplies
    resolved = []
    for ps in data.get("power_supplies", []):
        pwid = POWER_MAP.get(ps.get("power_id", ""))
        if pwid:
            resolved.append({"power_id": pwid, "voltage_range": ps.get("voltage_range", ""), "battery_life": ps.get("battery_life", "")})
    data["power_supplies"] = resolved

    # Sensor capabilities
    resolved = []
    for sc in data.get("sensor_capabilities", []):
        metric_name = sc.get("metric_id", "")
        mid = SENSOR_METRIC_MAP.get(metric_name)
        if mid:
            resolved.append({"metric_id": mid, "measure_range": sc.get("measure_range", ""),
                             "accuracy": sc.get("accuracy", ""), "resolution": sc.get("resolution", "")})
    data["sensor_capabilities"] = resolved

    return data


def download_image(url):
    """Download image via API's download-image endpoint."""
    try:
        resp = api_call("/products/download-image", "POST", {"url": url})
        if resp and "url" in resp:
            local_url = resp["url"]
            print(f"    Image saved: {local_url}")
            return local_url
        else:
            print(f"    Image download returned no URL: {resp}")
    except Exception as e:
        print(f"    Image download failed: {e}")
    return ""


def import_product(model, data, existing_products):
    """Create or update a product. Returns product id."""
    cat_slug = data.get("category_slug", "lorawan-sensor")
    # Map special category slugs
    if cat_slug == "lorawan-sensor_display":
        cat_slug = "lorawan-sensor"
    cat_id = CATEGORY_MAP.get(cat_slug)
    if not cat_id:
        print(f"    SKIP: category '{cat_slug}' not found")
        return None

    resolved = resolve_ids(data)

    # Download image
    images = []
    image_url = data.get("image_url", "")
    fallback_url = image_url  # Use external URL as fallback
    if image_url:
        print(f"    Downloading image...")
        local_url = download_image(image_url)
        if local_url:
            images = [{"url": local_url, "is_primary": True, "sort_order": 0}]

    resolved["image_url"] = images[0]["url"] if images else fallback_url
    resolved["images"] = images
    payload = {
        "model": model,
        "name": data.get("name", model),
        "category_id": cat_id,
        "manufacturer_id": MANUFACTURER_ID,
        "status": "active",
        "product_url": f"https://www.milesight.cn/",
        **resolved,
    }

    # Upsert: update if exists, create if not
    existing_id = existing_products.get(model)
    if existing_id:
        res = api_call(f"/products/{existing_id}", "PUT", payload)
        if res:
            print(f"    Updated: {model} (id={existing_id})")
            return existing_id
        else:
            print(f"    Update FAILED: {model}")
            return None
    else:
        res = api_call("/products", "POST", payload)
        if res:
            pid = res["product"]["id"]
            existing_products[model] = pid
            print(f"    Created: {model} (id={pid})")
            return pid
        else:
            print(f"    Create FAILED: {model}")
            return None


def main():
    print("=" * 60)
    print("Milesight Full Product Import (v2)")
    print("=" * 60)

    # Check API
    try:
        http_requests.get(f"{API_BASE.replace('/api', '')}/docs", timeout=5)
    except Exception as e:
        print(f"ERROR: Cannot reach API. {e}")
        sys.exit(1)

    print("\n[1/3] Loading dictionaries...")
    load_dict_maps()
    load_category_map()
    print(f"  Comm methods: {len(COMM_METHOD_MAP)}")
    print(f"  Protocols: {len(PROTOCOL_MAP)}")
    print(f"  Power: {len(POWER_MAP)}")
    print(f"  Sensor metrics: {len(SENSOR_METRIC_MAP)}")
    print(f"  Manufacturer ID: {MANUFACTURER_ID}")
    print(f"  Categories: {len(CATEGORY_MAP)}")

    print("\n[2/3] Loading existing products...")
    existing = load_existing_products()
    print(f"  Existing products: {len(existing)}")

    print("\n[3/3] Importing products...")
    created = 0
    updated = 0
    skipped = 0

    for model, data in PREBUILT.items():
        print(f"  {model} - {data.get('name', model)}")
        pid = import_product(model, data, existing)
        if pid:
            if model in existing:
                updated += 1
            else:
                created += 1
        else:
            skipped += 1
        time.sleep(0.3)

    print(f"\nDone! Created: {created}, Updated: {updated}, Skipped: {skipped}")
    print(f"Total products in DB: {len(existing)}")


if __name__ == "__main__":
    main()
