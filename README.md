# GitHub Commits to Redmine Issues

สร้าง Redmine issues จาก git commits แบบ bulk ผ่าน Redmine REST API

## Setup

```bash
python3 -m pip install -r requirements.txt
```

สร้าง `.env`:

```env
REDMINE_BASE_URL=http://redmine.biccorp.com
REDMINE_API_KEY=your-api-key
REDMINE_VERIFY_SSL=true
REDMINE_PROJECT_ID=1
REDMINE_TRACKER_ID=1
```

## Dry Run

ดูรายการก่อน ยังไม่ post จริง:

```bash
python3 main.py --repo /path/to/github/repo --since 2026-06-01
```

## Post จริง

```bash
python3 main.py --repo /path/to/github/repo --since 2026-06-01 --post
```

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
