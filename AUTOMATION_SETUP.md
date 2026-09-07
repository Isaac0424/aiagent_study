# AI Development Documentation V1

대상 Repository: `Isaac0424/aiagent_study`

## 동작

```text
push to main
    ↓
GitHub Actions
    ↓
git diff
    ↓
OpenAI Responses API
    ↓
Pydantic DevelopmentChange
    ↓
Notion Development Logs
```

## 필요한 GitHub Actions Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret

1. `OPENAI_API_KEY`
2. `NOTION_API_KEY`

`NOTION_API_KEY`는 Notion에서 별도의 Integration을 만든 뒤 발급받습니다.
해당 Integration에 `AI Development System`의 데이터베이스 접근 권한을 공유해야 합니다.

## 현재 연결된 Notion 대상

- Project page: `aiagent_study`
- Development Logs data source: 자동 기록 대상
- Architecture 업데이트는 V2에서 추가

## 설치할 파일

```text
.github/workflows/ai-development-docs.yml
automation/change_analyzer.py
requirements-ai-docs.txt
```

## 권장 적용 방법

직접 main에 넣기보다 별도 브랜치에서 추가 후 PR로 병합합니다.

```bash
git checkout -b chore/ai-dev-automation-v1

# 파일 복사

git add .
git commit -m "chore: add AI development documentation automation"
git push origin chore/ai-dev-automation-v1
```

GitHub에서 PR을 생성하고 두 Secrets를 설정한 다음 `main`에 병합합니다.

병합 이후 다음 push부터 Notion Development Logs에 자동 기록됩니다.
