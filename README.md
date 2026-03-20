# Redmine Worklog Report

เว็บรายงานข้อมูล time entries และ issue intelligence ของผู้ใช้ปัจจุบันจาก Redmine API โดยไม่ต้องติดตั้งเฟรมเวิร์กเว็บเพิ่ม ใช้ Python stdlib + `requests`

## สิ่งที่ทำได้

- ดึงผู้ใช้ปัจจุบันจาก `users/current.json`
- ดึง time entries ทั้งหมดของผู้ใช้นั้นแบบแบ่งหน้าอัตโนมัติจาก `time_entries.json`
- ดึง issue details เพิ่มเพื่อดูผู้แจ้ง, customer, company, status และ subject
- โหลดข้อมูล time entries ทั้งหมดเป็นค่าเริ่มต้น และกรองช่วงวันที่ผ่านหน้าเว็บได้
- sync master user/department จาก Superset (`E-Office : MySQL`) ผ่าน Superset API โดยไม่ต่อฐานข้อมูลตรง
- ใช้ Redmine API และ Superset API สดทุกครั้งที่โหลดรายงาน
- ใช้ batch issue fetch ผ่าน `GET /issues.json?issue_id=...` เพื่อลด N+1 calls ไป Redmine
- รองรับ `UserAliases.csv` สำหรับ map ชื่อจาก Redmine ไปยังชื่อใน master directory
- สรุปงานรายปีตามแผนก ผู้แจ้ง บริษัท และ issue
- แสดงรายชื่อที่ยังจับคู่แผนกไม่ได้ เพื่อช่วยเตรียม alias เพิ่ม
- โค้ดแยกเป็น `app/config.py`, `app/clients.py`, `app/reporting.py`, `app/server.py` เพื่อให้ดูแลง่ายขึ้น
- ตั้ง `sys.dont_write_bytecode` เพื่อไม่ให้เกิด `__pycache__` ระหว่างรัน

## การตั้งค่า

1. ใช้ virtualenv ที่มีอยู่ในโปรเจกต์นี้
2. ตั้งค่า environment variables ตามตัวอย่างใน [`.env.example`](/Users/bic-pannawat/Documents/MYPJ/redminePY/.env.example)
3. ใส่ `SUPERSET_*` ให้ครบสำหรับ `E-Office : MySQL`
4. ถ้าชื่อใน Redmine ยังไม่ตรงกับชื่อใน master directory ให้สร้าง `UserAliases.csv` เองในรูปแบบ `redmine_name,directory_name`

ตัวอย่าง `.env`

```env
REDMINE_BASE_URL=https://your-redmine.example.com
REDMINE_API_KEY=replace-with-your-api-key
REDMINE_VERIFY_SSL=true
SUPERSET_BASE_URL=https://superset.example.com
SUPERSET_USERNAME=your-username
SUPERSET_PASSWORD=your-password
SUPERSET_PROVIDER=ldap
SUPERSET_DATABASE_ID=2
SUPERSET_SCHEMA=bgerpshare
SUPERSET_VERIFY_SSL=true
REDMINE_ISSUE_WORKERS=8
REDMINE_ISSUE_BATCH_SIZE=100
HOST=127.0.0.1
PORT=8000
```

## การรัน

```bash
./venv/bin/python main.py
```

จากนั้นเปิด `http://127.0.0.1:8000`

หน้าเว็บจะดึงข้อมูลจริงจาก Redmine และ Superset ทุกครั้งที่เปิดหรือเปลี่ยนช่วงวันที่

## แหล่งข้อมูลผู้ใช้

master query เริ่มต้นจะอ่านจาก `users` และ `department` ใน schema `bgerpshare` ของ `E-Office : MySQL`

ตัวอย่าง `UserAliases.csv`

```csv
redmine_name,directory_name
Thongkorn Raksantinana,Thongkorn Raksantinana
Potjanee Chockpasitvej,Potjanee Chockpasitvej
```

หมายเหตุ: จากข้อมูลจริงที่ตรวจสอบ ชื่อ `Customer` ใน Redmine มักเป็นภาษาอังกฤษแบบ romanized หากชื่อจาก Redmine ไม่ตรงกับชื่อใน master directory โดยตรง ควรใช้ `UserAliases.csv` ช่วย map เพิ่ม

## API ภายในแอป

- `GET /` หน้า dashboard
- `GET /api/report?from=2026-03-01&to=2026-03-31` ข้อมูลรายงานในรูปแบบ JSON
- `GET /health` health check

## แนวคิดเรื่องความเร็ว

- bottleneck หลักของระบบนี้คือการดึง issue details จาก Redmine ไม่ใช่ CPU ของ Python
- ตัวแอปจะใช้ `GET /issues.json?issue_id=...` แบบ batch ก่อน แล้ว fallback เป็นราย issue เฉพาะตัวที่ตกหล่น
- โหมดนี้ไม่มี local store หรือ SQLite ดังนั้นโค้ดเรียบที่สุด แต่ความเร็วจะขึ้นกับ Redmine และ Superset โดยตรงทุกครั้ง
