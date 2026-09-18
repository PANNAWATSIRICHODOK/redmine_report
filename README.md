# Git Commits to Redmine

สร้าง Redmine issues จาก git commits แบบ bulk ผ่าน Redmine API

## ติดตั้ง

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

แก้ `.env` ให้เป็นค่า Redmine/API key/project/tracker ของคนที่รันเอง
ตั้ง `GIT_REPO_PATH` แล้วสามารถละ `--repo` ได้

## ทดสอบก่อน Post

```bash
python3 main.py --repo /path/to/git/repo --limit 5
```

ตัวอย่าง:

```bash
python3 main.py --repo /path/to/your/git/repo --limit 5
```

## Post จริง

ลอง 1 commit ก่อน:

```bash
python3 main.py --repo /path/to/git/repo --limit 1 --post
```

Post ตามช่วงวันที่ commit:

```bash
python3 main.py --repo /path/to/git/repo --since 2026-01-01 --until 2026-06-22 --post
```

Post ทั้งหมดตาม filter ใน `.env`:

```bash
python3 main.py --post
```

กัน commit ซ้ำด้วย commit SHA ถ้าเคยสร้างแล้วจะขึ้น `skipped existing`
Issue ใหม่ใช้ 1 manday = 8 ชั่วโมง, เวลาประมาณมากกว่าเวลาที่ใช้ 1.5 ชั่วโมง และวันครบกำหนดเป็นวันถัดจากวันที่ปิดงาน
เวลาที่ใช้รวมอย่างน้อย 8 ชั่วโมงต่อวันที่มี commit เช่น มี commit 2 วันต้องรวมอย่างน้อย 16 ชั่วโมง และมากกว่านั้นได้ โดยวันที่ต่ำกว่าเกณฑ์จะกระจายเวลาเพิ่มตามน้ำหนักแต่ละ commit

ถ้าเป็น Feature เดี่ยวที่ไม่อยู่ใต้ Parent ให้ขึ้นต้น commit ด้วย `[standalone]` โปรแกรมจะตัด marker ออกจากชื่อ Issue, ไม่ใส่ Parent และใช้ `REDMINE_FEATURE_TRACKER_ID`
ถ้าทั้งรอบเป็น Feature เดี่ยวทั้งหมด ใช้ `python3 main.py --standalone --post`

## ENV

ตั้งค่าจาก `.env.example` แล้วแก้ใน `.env` ของแต่ละคน

- `REDMINE_BASE_URL`: URL Redmine
- `REDMINE_API_KEY`: API key ของคนที่รัน
- `REDMINE_PROJECT_ID`: project ปลายทาง
- `REDMINE_TRACKER_ID`: tracker เช่น Feature หรือ Support
- `REDMINE_PARENT_ISSUE_ID`: ใส่ถ้าต้องการสร้างเป็น subtask
- `GIT_AUTHOR`: ใส่เพื่อกรองเฉพาะ commit ของตัวเอง

## Test

```bash
python3 tests.py
```

## Automation บน macOS

`automation.py` สแกน Git repositories ใต้ `GIT_SCAN_ROOT`, ตรวจ commit ซ้ำ และจับคู่ Project ด้วย Git remote URL ถ้าไม่พบจะสร้าง Project ใหม่เมื่อใช้ `--post`

```bash
.venv/bin/python automation.py --force --limit 1
.venv/bin/python automation.py --force --limit 1 --post
```

LaunchAgent `com.bic.git-to-redmine.plist` เรียกงานเวลา 16:00 วันที่ 26–28 และ Python เลือกเฉพาะวันที่ 28 หรือวันศุกร์ก่อนหน้า พร้อม notification ตอนเริ่ม/จบ และบันทึกที่ `automation.log`

## ไฟล์หลัก

```text
main.py
redmine_github/cli.py
redmine_github/importer.py
redmine_github/redmine.py
```
