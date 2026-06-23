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
- ถ้ามี `REDMINE_PARENT_ISSUE_ID` จะสร้าง commit issue เป็น subtask ของ issue นั้น
- `เวลาที่ใช้โดยประมาณ` ประเมินจาก keyword, จำนวนไฟล์, จำนวนบรรทัด, commit body และ path ที่แก้ แล้วคูณเผื่อ `2x`
- `AI Score` ประเมินเป็นชั่วโมง โดยคิดจาก `25-50%` ของเวลาประมาณ และส่งเข้า custom field เมื่อมี `REDMINE_AI_SCORE_FIELD_ID`
- `เวลาที่ใช้` auto-fill ให้น้อยกว่าเวลาประมาณ โดยเหลือ buffer อย่างน้อย `0.5` ชั่วโมง เมื่อมี `REDMINE_ACTIVITY_ID`
- ถ้า `เวลาที่ใช้` ต่ำกว่า `0.5` หรือ Redmine ไม่รับ time entry ของ issue นั้น โปรแกรมจะข้าม time entry แล้วทำงานต่อ
- ถ้า commit มี description/body โปรแกรมจะเพิ่มเป็น Note ใน issue หลังสร้าง

ค่าพวกนี้แก้ผ่าน `.env` ได้ทั้งหมด โดยแต่ละคนควรมี `.env` ของตัวเอง และไฟล์ `.env` ถูก ignore ไม่เข้า git

จำกัดจำนวน:

```bash
python3 main.py --repo /path/to/github/repo --limit 20 --post
```

## โครงสร้าง

```text
.env.example                                 template ENV สำหรับแต่ละคน
main.py                                      entrypoint
redmine_github/cli.py                        CLI arguments
redmine_github/importer.py                   อ่าน git log, ประเมินเวลา, import commits -> issues
redmine_github/redmine.py                    อ่าน .env และเรียก Redmine API
tests.py                                     self-check แบบ stdlib
```
