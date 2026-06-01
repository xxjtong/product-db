"""Initialize dictionary tables with standard data."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.database import SessionLocal
from app.models.dictionary import (Manufacturer, DictCommMethod, DictCommProtocol,
                                   DictPowerSupply, DictSensorMetric)


def init_all():
    db = SessionLocal()

    # --- Manufacturer ---
    mfg_data = [
        {"name": "Milesight", "website": "https://www.milesight.cn", "description": "星纵物联"},
    ]
    for d in mfg_data:
        if not db.query(Manufacturer).filter_by(name=d["name"]).first():
            db.add(Manufacturer(**d))
    db.commit()
    print(f"Manufacturers: {db.query(Manufacturer).count()}")

    # --- DictCommMethod ---
    methods = [
        # Wired
        ("wired", "Ethernet"),
        ("wired", "RS485"),
        ("wired", "RS232"),
        ("wired", "DryContact"),
        ("wired", "KNX"),
        ("wired", "M-BUS"),
        ("wired", "USB"),
        # Wireless
        ("wireless", "LoRaWAN"),
        ("wireless", "WiFi"),
        ("wireless", "4G"),
        ("wireless", "5G"),
        ("wireless", "NB-IoT"),
        ("wireless", "Zigbee"),
        ("wireless", "BLE"),
        ("wireless", "NFC"),
        ("wireless", "GNSS"),
        ("wireless", "D2D"),
    ]
    for method_type, name in methods:
        if not db.query(DictCommMethod).filter_by(name=name).first():
            db.add(DictCommMethod(method_type=method_type, name=name))
    db.commit()
    print(f"Comm Methods: {db.query(DictCommMethod).count()}")

    # --- DictCommProtocol ---
    protocols = [
        "HTTP", "HTTPS", "MQTT", "MQTTS", "ModbusRTU", "ModbusTCP",
        "BACnet/IP", "BACnet/MS-TP", "TCP", "UDP", "SNMP", "SSH", "VPN", "RTSP", "NTP",
    ]
    for name in protocols:
        if not db.query(DictCommProtocol).filter_by(name=name).first():
            db.add(DictCommProtocol(name=name))
    db.commit()
    print(f"Comm Protocols: {db.query(DictCommProtocol).count()}")

    # --- DictPowerSupply ---
    supplies = [
        ("外接电源", "DC"),
        ("PoE", "PoE"),
        ("内置电池", "Battery"),
        ("外接电源", "USB-C"),
        ("外接电源", "AC"),
        ("新能源", "Solar"),
    ]
    for category, name in supplies:
        if not db.query(DictPowerSupply).filter_by(name=name).first():
            db.add(DictPowerSupply(supply_category=category, name=name))
    db.commit()
    print(f"Power Supplies: {db.query(DictPowerSupply).count()}")

    # --- DictSensorMetric ---
    metrics = [
        ("温度", "℃"),
        ("湿度", "%RH"),
        ("CO2", "ppm"),
        ("TVOC", "μg/m³"),
        ("PM2.5", "μg/m³"),
        ("PM10", "μg/m³"),
        ("气压", "hPa"),
        ("光照", "lux"),
        ("噪声", "dB"),
        ("水浸", None),
        ("门磁", None),
        ("倾斜", "°"),
        ("液位", "m"),
        ("压力", "Pa"),
        ("距离", "m"),
        ("人数", "人"),
        ("人体存在", None),
        ("CO", "ppm"),
        ("O3", "ppm"),
        ("HCHO", "mg/m³"),
        ("电流", "A"),
    ]
    for name, unit in metrics:
        if not db.query(DictSensorMetric).filter_by(name=name).first():
            db.add(DictSensorMetric(name=name, unit=unit))
    db.commit()
    print(f"Sensor Metrics: {db.query(DictSensorMetric).count()}")

    # --- Default admin user ---
    from app.models.user import User
    from app.auth import pwd_ctx
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(
            username="admin",
            password_hash=pwd_ctx.hash("admin"),
            role="admin",
        ))
        db.commit()
        print("Admin user created")

    db.close()
    print("\nAll dictionary data initialized!")


if __name__ == "__main__":
    init_all()
