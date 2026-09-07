from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from typing import Literal

import requests
from openai import OpenAI
from pydantic import BaseModel, Field


NOTION_VERSION = "2026-03-11"
MAX_DIFF_CHARS = 40_000


class DevelopmentChange(BaseModel):
    title: str = Field(description="짧고 구체적인 변경 제목")
    change_type: Literal[
        "Feature",
        "Fix",
        "Refactor",
        "Docs",
        "Infra",
        "Test",
        "Chore",
    ]
    summary: str = Field(description="무엇이 바뀌었는지 2~4문장으로 요약")
    reason: str = Field(description="변경 목적이나 배경. 알 수 없으면 코드에서 추론 가능한 범위만 작성")
    architecture_impact: bool = Field(
        description="모듈 경계, 데이터 흐름, 외부 의존성, 배포 구조 등 시스템 구조에 영향이 있으면 true"
    )


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def is_zero_sha(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def collect_change(before_sha: str, after_sha: str) -> tuple[list[str], str]:
    if not before_sha or is_zero_sha(before_sha):
        files = run_git("show", "--pretty=format:", "--name-only", after_sha).splitlines()
        diff = run_git("show", "--pretty=format:", "--unified=2", after_sha)
    else:
        files = run_git("diff", "--name-only", before_sha, after_sha).splitlines()
        diff = run_git("diff", "--unified=2", before_sha, after_sha)

    files = [f.strip() for f in files if f.strip()]

    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[DIFF TRUNCATED]"

    return files, diff


def parse_ai_result(
    commit_message: str,
    changed_files: list[str],
    diff: str,
) -> DevelopmentChange:
    client = OpenAI()
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    prompt = f"""
당신은 GitHub 변경사항을 개발 문서로 변환하는 Software Documentation Agent다.

다음 변경을 분석해서 DevelopmentChange 스키마에 맞게 작성하라.

규칙:
- 실제 diff에서 확인되지 않는 사실을 만들지 말 것.
- 사소한 포맷/설정 변경은 Chore 또는 Docs로 분류할 것.
- architecture_impact는 시스템 구성, 계층, 데이터 흐름, 외부 서비스,
  DB, Agent orchestration, API 구조, 배포/CI 구조가 바뀌는 경우에만 true로 할 것.
- 한국어로 작성할 것.
- summary는 간결하게 작성할 것.

Commit message:
{commit_message}

Changed files:
{chr(10).join(changed_files) or "(none)"}

Git diff:
{diff or "(empty diff)"}
""".strip()

    response = client.responses.parse(
        model=model,
        input=prompt,
        text_format=DevelopmentChange,
    )

    for output in response.output:
        if output.type != "message":
            continue
        for item in output.content:
            if item.type == "output_text" and item.parsed:
                return item.parsed

    raise RuntimeError("OpenAI response did not contain a parsed DevelopmentChange.")


def rich_text(value: str, limit: int = 1900) -> dict:
    value = value.strip()
    if len(value) > limit:
        value = value[: limit - 3] + "..."
    return {
        "rich_text": [
            {
                "type": "text",
                "text": {"content": value},
            }
        ]
    }


def write_notion_log(
    analysis: DevelopmentChange,
    changed_files: list[str],
    commit_sha: str,
    commit_url: str,
    branch: str,
) -> str:
    notion_token = required_env("NOTION_API_KEY")
    data_source_id = required_env("NOTION_DEV_LOGS_DATA_SOURCE_ID")
    project_page_id = required_env("NOTION_PROJECT_PAGE_ID")

    today = datetime.now(timezone.utc).date().isoformat()

    payload = {
        "parent": {
            "type": "data_source_id",
            "data_source_id": data_source_id,
        },
        "properties": {
            "Title": {
                "title": [
                    {
                        "type": "text",
                        "text": {"content": analysis.title[:1900]},
                    }
                ]
            },
            "Project": {
                "relation": [{"id": project_page_id}],
            },
            "Date": {
                "date": {"start": today},
            },
            "Commit": rich_text(commit_sha),
            "Branch": rich_text(branch),
            "Change Type": {
                "select": {"name": analysis.change_type},
            },
            "Summary": rich_text(analysis.summary),
            "Changed Files": rich_text(", ".join(changed_files) or "(none)"),
            "Reason": rich_text(analysis.reason),
            "Architecture Impact": {
                "checkbox": analysis.architecture_impact,
            },
            "GitHub URL": {
                "url": commit_url,
            },
        },
    }

    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        },
        json=payload,
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Notion API failed ({response.status_code}): {response.text}"
        )

    return response.json()["url"]


def main() -> None:
    required_env("OPENAI_API_KEY")
    required_env("NOTION_API_KEY")

    before_sha = os.getenv("BEFORE_SHA", "").strip()
    after_sha = required_env("AFTER_SHA")
    repository = required_env("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_REF_NAME", "unknown")
    server_url = os.getenv("GITHUB_SERVER_URL", "https://github.com")

    changed_files, diff = collect_change(before_sha, after_sha)
    commit_message = run_git("log", "-1", "--pretty=%B", after_sha)
    commit_url = f"{server_url}/{repository}/commit/{after_sha}"

    analysis = parse_ai_result(
        commit_message=commit_message,
        changed_files=changed_files,
        diff=diff,
    )

    notion_url = write_notion_log(
        analysis=analysis,
        changed_files=changed_files,
        commit_sha=after_sha,
        commit_url=commit_url,
        branch=branch,
    )

    print("AI Development Log created successfully.")
    print(f"Change type: {analysis.change_type}")
    print(f"Architecture impact: {analysis.architecture_impact}")
    print(f"Notion: {notion_url}")


if __name__ == "__main__":
    main()
