# GitHub Commits to Redmine Issues

สร้าง Redmine issues จาก git commits แบบ bulk ผ่าน Redmine REST API

## Setup

```bash
python3 -m pip install -r requirements.txt
```

สร้าง `.env` จากตัวอย่าง:

```bash
cp .env.example .env
```

แล้วแก้ `.env` เป็น API key, project, tracker, author ของคนที่รันเอง

## Dry Run

ดูรายการก่อน ยังไม่ post จริง:

```bash
python3 main.py --repo /path/to/github/repo --since 2026-06-01
```

กรองเฉพาะ commit ของคนรัน:

```bash
python3 main.py --repo /path/to/github/repo --since 2026-06-01 --author "Your Git Name Or Email"
```

## Post จริง

```bash
python3 main.py --repo /path/to/github/repo --since 2026-06-01 --post
```

ใส่ข้อมูลให้ครบแบบตัวอย่าง issue เดิม:

```bash
python3 main.py --repo /path/to/github/repo --limit 1 \
  --post
```

ค่า default ตอน `--post`:

- มอบหมายให้ user เจ้าของ API key
- status เป็น `Closed`
- `% สำเร็จ` เป็น `100`
- `เวลาที่ใช้โดยประมาณ` ประเมินจาก commit
- `AI Score` ประเมินจาก commit และส่งเป็น custom field เมื่อมี `REDMINE_AI_SCORE_FIELD_ID`

ค่าพวกนี้แก้ผ่าน `.env` ได้ทั้งหมด โดยแต่ละคนควรมี `.env` ของตัวเอง และไฟล์ `.env` ถูก ignore ไม่เข้า git

จำกัดจำนวน:

```bash
python3 main.py --repo /path/to/github/repo --limit 20 --post
```

## Docker

Build image:

```bash
docker build -t redmine-github .
```

Dry run โดย mount git repo เข้า `/repo`:

```bash
docker run --rm --env-file .env -v /path/to/github/repo:/repo redmine-github --repo /repo --since 2026-06-01
```

Post จริง:

```bash
docker run --rm --env-file .env -v /path/to/github/repo:/repo redmine-github --repo /repo --since 2026-06-01 --post
```

## โครงสร้าง

```text
Dockerfile                                   container image สำหรับ CLI
.env.example                                 template ENV สำหรับแต่ละคน
main.py                                      entrypoint
redmine_github/cli.py                        CLI arguments
redmine_github/config.py                     อ่าน .env และ environment variables
redmine_github/models.py                     dataclass กลาง
redmine_github/controllers/import_controller.py  flow import commits -> issues
redmine_github/services/git_service.py       อ่าน git log
redmine_github/services/redmine_service.py   POST /issues.json
redmine_github/views/cli_view.py             output ใน terminal
tests.py                                     self-check แบบ stdlib
```
