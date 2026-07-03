"""业务逻辑源自 appium自动化测试_备份.py"""
from __future__ import annotations

import json
import os
import random
import string
import subprocess
import time
import uuid

import pymysql
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait

from loanadvisor.core.config import settings
from loanadvisor.core.login_session import LOGIN_DATA

from loanadvisor.core.config import settings

APPLY_DB_CONFIG = settings.db_config
APPLY_DB_TABLE_FIELDS = settings.db_table_fields
ALLURE_RESULTS_DIR = str(settings.allure_results_dir)
ALLURE_REPORT_DIR = str(settings.allure_report_dir)
_SCRIPT_DIR = str(settings.allure_results_dir.parent.parent)

def verify_apply_db_fields(max_retries=15, retry_interval=5):
    """基本信息提交后：验证各表关键字段不为 NULL，返回验证结果供 Allure 报告使用"""
    customer_id = _get_apply_customer_id()
    customer_mobile = _get_apply_customer_mobile()
    if not customer_id and not customer_mobile:
        return {
            "passed": False,
            "customer_id": customer_id,
            "customer_mobile": customer_mobile,
            "fields": [],
            "errors": ["无法从 LOGIN_DATA 获取 customerId / customer_mobile"],
        }

    print("=== Basic info 提交后 DB 验证 ===")
    print(f"customer_id={customer_id}, customer_mobile={customer_mobile}")
    print(
        "ℹ️ customer_device_info 字段由后端异步写入（app/call/usage 可能晚于 base_info/gps），"
        f"最多等待约 {max_retries * retry_interval}s"
    )

    last_errors = []
    field_results = []
    seen_passed = set()

    for attempt in range(1, max_retries + 1):
        last_errors = []
        field_results = []
        conn = None
        try:
            conn = pymysql.connect(
                **APPLY_DB_CONFIG,
                cursorclass=pymysql.cursors.DictCursor,
            )
            cursor = conn.cursor()

            for table, fields in APPLY_DB_TABLE_FIELDS.items():
                row = _fetch_apply_db_row(
                    cursor, table, fields, customer_id, customer_mobile
                )
                if row is None:
                    err = f"{table}: 未查询到记录"
                    last_errors.append(err)
                    for field in fields:
                        field_results.append({
                            "table": table,
                            "field": field,
                            "value": None,
                            "passed": False,
                            "error": err,
                        })
                    continue

                for field in fields:
                    value = row.get(field)
                    passed = not _apply_db_value_is_null(value)
                    key = (table, field)
                    item = {
                        "table": table,
                        "field": field,
                        "value": value,
                        "passed": passed,
                        "error": None if passed else f"{table}.{field} 为 NULL 或空",
                    }
                    field_results.append(item)
                    if passed:
                        if key not in seen_passed:
                            print(f"✅ {table}.{field} = {value!r}")
                            seen_passed.add(key)
                    else:
                        last_errors.append(item["error"])

            if not last_errors:
                print("✅ Basic info DB 验证全部通过")
                return {
                    "passed": True,
                    "customer_id": customer_id,
                    "customer_mobile": customer_mobile,
                    "fields": field_results,
                    "errors": [],
                }

            print(f"⚠️ DB 验证第 {attempt}/{max_retries} 次未通过（仍缺 {len(last_errors)} 项）:")
            for err in last_errors:
                print(f"   - {err}")

        except Exception as e:
            last_errors = [f"数据库连接/查询异常: {e}"]
            field_results = []
            print(f"⚠️ DB 验证第 {attempt}/{max_retries} 次异常: {e}")
        finally:
            if conn:
                conn.close()

        if attempt < max_retries:
            time.sleep(retry_interval)

    return {
        "passed": False,
        "customer_id": customer_id,
        "customer_mobile": customer_mobile,
        "fields": field_results,
        "errors": last_errors,
    }


def _allure_now_ms():
    return int(time.time() * 1000)


def _allure_make_step(name, status, sub_steps=None, attachment_body=None, attachment_name=None):
    step = {
        "name": name,
        "status": status,
        "start": _allure_now_ms(),
        "stop": _allure_now_ms(),
        "steps": sub_steps or [],
        "attachments": [],
    }
    if attachment_body is not None:
        attach_uuid = str(uuid.uuid4())
        attach_file = f"{attach_uuid}-attachment.txt"
        attach_path = os.path.join(ALLURE_RESULTS_DIR, attach_file)
        with open(attach_path, "w", encoding="utf-8") as f:
            f.write(str(attachment_body))
        step["attachments"].append({
            "name": attachment_name or name,
            "source": attach_file,
            "type": "text/plain",
        })
    return step


def generate_allure_db_report(db_result):
    """将 verify_apply_db_fields 结果写入 Allure 并生成 HTML 报告"""
    print("=== 生成 Allure DB 验证报告 ===")
    os.makedirs(ALLURE_RESULTS_DIR, exist_ok=True)

    table_steps = []
    fields_by_table = {}
    for item in db_result.get("fields") or []:
        fields_by_table.setdefault(item["table"], []).append(item)

    for table, items in fields_by_table.items():
        field_steps = []
        for item in items:
            status = "passed" if item["passed"] else "failed"
            body = item["value"] if item["passed"] else item.get("error")
            field_steps.append(_allure_make_step(
                f"{table}.{item['field']}",
                status,
                attachment_body=body,
                attachment_name=f"{table}.{item['field']}",
            ))
        table_passed = all(x["passed"] for x in items)
        table_steps.append(_allure_make_step(
            f"验证 {table} 表",
            "passed" if table_passed else "failed",
            sub_steps=field_steps,
        ))

    summary = {
        "customer_id": db_result.get("customer_id"),
        "customer_mobile": db_result.get("customer_mobile"),
        "passed": db_result.get("passed"),
        "errors": db_result.get("errors") or [],
    }
    table_steps.insert(0, _allure_make_step(
        "DB 验证概要",
        "passed" if db_result.get("passed") else "failed",
        attachment_body=json.dumps(summary, ensure_ascii=False, indent=2),
        attachment_name="summary.json",
    ))

    test_status = "passed" if db_result.get("passed") else "failed"
    test_uuid = str(uuid.uuid4())
    result = {
        "uuid": test_uuid,
        "historyId": "basic_info_db_verify",
        "name": f"Basic info DB验证 customer_id={db_result.get('customer_id')}",
        "fullName": "run_next_flow.verify_apply_db_fields",
        "status": test_status,
        "stage": "finished",
        "start": _allure_now_ms(),
        "stop": _allure_now_ms(),
        "steps": table_steps,
        "labels": [
            {"name": "feature", "value": "Next流程"},
            {"name": "story", "value": "Basic info DB验证"},
            {"name": "suite", "value": "Appium自动化测试"},
        ],
    }
    if not db_result.get("passed"):
        result["statusDetails"] = {
            "message": "\n".join(db_result.get("errors") or []),
        }

    result_path = os.path.join(ALLURE_RESULTS_DIR, f"{test_uuid}-result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ Allure 结果已写入: {result_path}")

    try:
        proc = subprocess.run(
            [
                "allure", "generate", ALLURE_RESULTS_DIR,
                "-o", ALLURE_REPORT_DIR, "--clean",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        report_index = os.path.join(ALLURE_REPORT_DIR, "index.html")
        print(f"✅ Allure HTML 报告: {report_index}")
        if proc.stdout:
            print(proc.stdout.strip())
    except FileNotFoundError:
        print(f"ℹ️ 未检测到 allure 命令，请手动生成 HTML 报告:")
        print(f"   allure generate \"{ALLURE_RESULTS_DIR}\" -o \"{ALLURE_REPORT_DIR}\" --clean")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Allure 报告生成失败: {e.stderr or e.stdout or e}")
        print(f"   原始结果目录: {ALLURE_RESULTS_DIR}")
