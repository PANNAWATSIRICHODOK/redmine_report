# Git Commits to Redmine

สร้าง Redmine issues จาก git commits แบบ bulk ผ่าน Redmine API

## ติดตั้ง

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
```

แก้ `.env` ให้เป็นค่า Redmine/API key/project/tracker ของคนที่รันเอง

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
python3 main.py --repo /path/to/git/repo --post
```

กัน commit ซ้ำด้วย commit SHA ถ้าเคยสร้างแล้วจะขึ้น `skipped existing`

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

## ไฟล์หลัก

```text
main.py
redmine_github/cli.py
redmine_github/importer.py
redmine_github/redmine.py
```
