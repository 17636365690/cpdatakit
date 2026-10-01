"""Verify CSV first use in Chromium against a clean wheel, optionally using local IN718 data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import socket
import subprocess
import zipfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from smoke_browser_installed import _SERVER, run_child, wait_for_server

_IDENTITY = """
import importlib.util, json, pathlib, sys
import cpdatakit
package = pathlib.Path(cpdatakit.__file__).resolve()
assert package.is_relative_to(pathlib.Path(sys.prefix).resolve()), package
assert importlib.util.find_spec('httpx') is None
print(json.dumps({'version': cpdatakit.__version__, 'package': str(package),
                  'runtime_without_httpx': True}))
"""

_READ_BACK = """
import csv, hashlib, io, json, sys
from pathlib import Path
import numpy as np
from cpdatakit import load_hdf5
root = Path(sys.argv[1])
raw = (root / 'input.csv').read_bytes()
assert (root / 'downloaded-source.csv').read_bytes() == raw
records = [row for row in csv.reader(io.StringIO(raw.decode('utf-8-sig')), delimiter=';') if row]
values = np.array([[float(row[i]) for i in [0,1,2,4,5]] for row in records[1:]])
values[:,2] /= 1000
data = load_hdf5(root / 'converted.h5')
names = ['time','extension','force','reported_stress','reported_strain']
assert list(data.data) == names
assert data.metadata['units'] == dict(zip(names, ['s','mm','kN','MPa','dimensionless']))
np.testing.assert_allclose(data.data.to_numpy(), values, rtol=1e-15, atol=1e-12)
manifest = json.loads((root / 'downloaded-manifest.json').read_text(encoding='utf-8'))
assert manifest['source_sha256'] == hashlib.sha256(raw).hexdigest()
assert manifest['excluded_columns'] == [{'index':3, 'source_name':''}]
assert manifest['record_count'] == len(values)
for name in ['first-report.json', 'reused-report.json']:
    report = json.loads((root / name).read_text(encoding='utf-8'))
    assert report['record_count'] == len(values)
    assert report['validation']['valid'] and not report['validation']['errors']
    assert not report['validation']['warnings']
print(json.dumps({'rows':len(values), 'fields':names, 'source_unchanged':True,
    'maximum_absolute_difference':float(np.max(np.abs(data.data.to_numpy()-values))),
    'reports_valid':True}))
"""


def browser_workflow(base: str, root: Path, rows: int, evidence: dict) -> None:
    console, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(accept_downloads=True)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.on("console", lambda message: console.append([message.type, message.text]))
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base)
            page.get_by_label("项目名称", exact=True).fill("CSV installed-wheel acceptance")
            page.get_by_role("button", name="创建项目", exact=True).click()
            page.wait_for_url("**/projects/*")
            pid = page.url.rsplit("/", 1)[-1]

            def resources():
                response = page.request.get(f"{base}/api/projects/{pid}")
                assert response.ok, response.text()
                return response.json()

            def preview(path: Path, expected_status: int):
                page.locator("#csv-file").set_input_files(path)
                with page.expect_response(lambda r: r.url.endswith("/csv-preview")) as pending:
                    page.locator("#csv-preview-button").click()
                response = pending.value
                assert response.status == expected_status, response.text()
                return response.json()

            page.locator("#csv-delimiter").select_option(";")
            preview(root / "malformed.csv", 400)
            expect(page.locator("#csv-status")).to_contain_text("CSV row 2")
            expect(page.locator("#csv-status")).to_contain_text("请核对文件解析设置")
            assert resources()["datasets"] == []
            page.locator("#csv-delimiter").select_option(",")
            preview(root / "input.csv", 200)
            expect(page.locator("#csv-counts")).to_contain_text("1 列")
            expect(page.locator("#csv-status")).to_contain_text("检查分隔符")
            page.locator("#csv-delimiter").select_option(";")
            expect(page.locator("#csv-confirm-form")).to_be_hidden()
            preview(root / "input.csv", 200)
            expect(page.locator("#csv-counts")).to_contain_text(f"{rows} 条记录")
            expect(page.locator("#csv-columns tbody tr")).to_have_count(6)

            force = page.locator('#csv-columns tr[data-index="2"]')
            force.locator('[data-key="dtype"]').select_option("string")
            expect(force.locator('[data-key="input_unit"]')).to_be_disabled()
            expect(force.locator('[data-key="input_unit"]')).to_have_value("")
            force.locator('[data-key="dtype"]').select_option("float")
            settings = json.loads(
                (Path(__file__).parents[1] / "examples/csv-intake/settings.json").read_text(
                    encoding="utf-8"
                )
            )
            declarations = settings["columns"]
            for column in declarations:
                row = page.locator(f'#csv-columns tr[data-index="{column["index"]}"]')
                if not column["include"]:
                    row.locator('[data-key="include"]').uncheck()
                    continue
                for key in ["dtype", "role"]:
                    row.locator(f'[data-key="{key}"]').select_option(column[key])
                for key in ["target", "input_unit", "output_unit"]:
                    row.locator(f'[data-key="{key}"]').fill(column[key])
            description = settings["confirmed_source_definition"]
            if evidence["source_archive_sha256"]:
                description = (
                    f"Mendeley 10.17632/nx55jj48rx.2; {evidence['source_member']}. "
                    "Units confirmed from headers; fourth column excluded. "
                    "Engineering/true stress-strain definitions are not inferred."
                )
            page.locator("#csv-conventions").fill(description)
            force.locator('[data-key="input_unit"]').fill("unconfirmed_unit_xyz")
            page.locator("#csv-confirmed").check()
            with page.expect_response(lambda r: r.url.endswith("/csv-import")) as rejected:
                page.locator("#csv-import-button").click()
            assert rejected.value.status == 400, rejected.value.text()
            expect(page.locator("#csv-status")).to_contain_text("请核对文件解析设置")
            assert resources()["datasets"] == []
            force.locator('[data-key="input_unit"]').fill("N")
            page.locator("#csv-confirmed").check()
            page.locator("#csv-intake").screenshot(path=str(root / "csv-confirmation.png"))
            with page.expect_response(lambda r: r.url.endswith("/csv-import")) as imported:
                page.locator("#csv-import-button").click()
            assert imported.value.status == 201, imported.value.text()
            result = imported.value.json()
            selector = result["schema_selector"]
            expect(page.locator("#csv-status")).to_contain_text("当前数据与规则已选中")
            expect(page.locator("#schema")).to_have_value(selector)
            for label, filename in [
                ("下载原文件", "downloaded-source.csv"),
                ("下载正式规则", "downloaded-schema.json"),
                ("下载导入清单", "downloaded-manifest.json"),
            ]:
                with page.expect_download() as downloaded:
                    page.get_by_role("link", name=label, exact=True).click()
                downloaded.value.save_as(root / filename)

            def submit(operation: str, label: str):
                with page.expect_response(
                    lambda r: r.request.method == "POST" and r.url.endswith(f"/{operation}")
                ) as pending:
                    page.get_by_role("button", name=label, exact=True).click()
                assert pending.value.status == 202, pending.value.text()
                job_id = pending.value.json()["job_id"]
                expect(page.locator(f'[data-job-id="{job_id}"]')).to_have_attribute(
                    "data-job-status", "succeeded"
                )
                return job_id

            def download_artifact(filename: str):
                row = page.locator("#artifacts .artifact-row").filter(has_text=filename)
                with page.expect_download() as downloaded:
                    row.get_by_role("link", name="下载", exact=True).click()
                downloaded.value.save_as(root / filename)
                return row

            page.locator("#report-format").select_option("json")
            page.locator("#report-output").fill("results/first-report.json")
            first_report = submit("report", "生成报告")
            download_artifact("first-report.json")
            page.locator("#convert-output").fill("results/converted.h5")
            converted = submit("convert", "转换并保存")
            converted_row = download_artifact("converted.h5")
            page.locator("#schema").select_option("point")
            with page.expect_response(lambda r: r.url.endswith("/use-as-input")) as activated:
                converted_row.get_by_role("button", name="使用此结果继续处理", exact=True).click()
            assert activated.value.status in (200, 201), activated.value.text()
            reused = activated.value.json()
            expect(page.locator("#dataset")).to_have_value(str(reused["dataset_id"]))
            expect(page.locator("#schema")).to_have_value(selector)
            with page.expect_response(lambda r: r.url.endswith("/use-as-input")) as repeated:
                converted_row.get_by_role("button", name="使用此结果继续处理", exact=True).click()
            assert repeated.value.json()["dataset_id"] == reused["dataset_id"]
            assert len(resources()["datasets"]) == 2
            page.locator("#report-output").fill("results/reused-report.json")
            second_report = submit("report", "生成报告")
            download_artifact("reused-report.json")
            page.reload()
            expect(page.locator("#schema")).to_have_value(selector)
            expect(page.locator("#dataset")).to_have_value(str(reused["dataset_id"]))
            page.screenshot(path=str(root / "reused-result.png"), full_page=True)

            # Exercise the ordinary-upload selection boundary identified in review.
            page.locator("#schema-authoring > summary").click()
            page.get_by_role("button", name="从数据生成规则草案", exact=True).click()
            expect(page.locator("#draft-editor")).to_be_visible()
            page.get_by_text("转换时使用的字段映射", exact=True).click()
            page.locator("#mapping-json").fill('{"mappings":[{"source":"force","target":"force"}]}')
            page.locator("#data-file").set_input_files(root / "converted.h5")
            with page.expect_response(lambda r: r.url.endswith("/inspect")) as uploaded:
                page.get_by_role("button", name="上传并检查", exact=True).click()
            assert uploaded.value.status in (200, 201), uploaded.value.text()
            expect(page.locator("#dataset")).to_have_value(str(uploaded.value.json()["dataset_id"]))
            expect(page.locator("#mapping-json")).to_have_value("")
            expect(page.locator("#schema-draft-json")).to_have_value("")
            expect(page.locator("#draft-editor")).to_be_hidden()
            assert errors == [], errors
            evidence.update(
                browser_version=browser.version,
                project_url=page.url,
                rows=rows,
                imported_dataset=result["dataset_id"],
                reused_dataset=reused["dataset_id"],
                original_schema=selector,
                dataset_count_after_repeated_reuse=2,
                ordinary_upload_cleared_authoring=True,
                jobs={
                    "first_report": first_report,
                    "convert": converted,
                    "reused_report": second_report,
                },
            )
        finally:
            page.screenshot(path=str(root / "final-page.png"), full_page=True)
            (root / "page.html").write_text(page.content(), encoding="utf-8")
            (root / "console.json").write_text(
                json.dumps({"console": console, "page_errors": errors}, indent=2), encoding="utf-8"
            )
            context.tracing.stop(path=str(root / "trace.zip"))
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-zip", type=Path)
    args = parser.parse_args()
    root = args.output_dir.resolve()
    if args.source_zip:
        original = args.source_zip.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        reference = json.loads(
            (Path(__file__).parents[1] / "examples/csv-intake/in718-source.json").read_text(
                encoding="utf-8"
            )
        )
        if digest != reference["archive_sha256"]:
            parser.error(
                "Expected the original IN718 archive from Mendeley "
                f"{reference['doi']} (SHA-256 {reference['archive_sha256']}); got {digest}"
            )
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            member = sorted(n for n in archive.namelist() if n.lower().endswith(".csv"))[0]
            payload = archive.read(member)
    else:
        payload = (Path(__file__).parents[1] / "examples/csv-intake/instrument.csv").read_bytes()
        member, digest = "synthetic-example", None
    root.mkdir(parents=True, exist_ok=False)
    (root / "input.csv").write_bytes(payload)
    (root / "malformed.csv").write_bytes(b"x;y\n1\n")
    rows = (
        len(
            [
                row
                for row in csv.reader(io.StringIO(payload.decode("utf-8-sig")), delimiter=";")
                if row
            ]
        )
        - 1
    )
    python = args.python.absolute()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    evidence = run_child(python, _IDENTITY, root, environment)
    evidence.update(source_member=member, source_archive_sha256=digest)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with (root / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen(
            [str(python), "-X", "utf8", "-c", _SERVER, str(root / "workspace"), str(port)],
            cwd=root,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            wait_for_server(server, base)
            browser_workflow(base, root, rows, evidence)
            evidence["read_back"] = run_child(python, _READ_BACK, root, environment)
        finally:
            try:
                server.communicate("stop\n", timeout=30)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=10)
                raise RuntimeError("Installed CSV server did not stop") from None
    assert server.returncode == 0, server.returncode
    if args.source_zip:
        assert hashlib.sha256(args.source_zip.read_bytes()).hexdigest() == digest
    evidence["server_exit_code"] = server.returncode
    (root / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
