#!/bin/sh
# publish.sh — 建仓并推送（需要 GITHUB_TOKEN，或用 SSH 推送到已存在的空仓）
#
# A. 有 token（repo scope）：自动建仓 + 推送
#    GITHUB_TOKEN=ghp_xxx ./scripts/publish.sh
# B. 没有 token：先在 GitHub 网页建一个空仓（不勾 README），然后
#    ./scripts/publish.sh            # 走 SSH，用本机已认证的 key
#
# 可选环境变量：REPO_NAME（默认 dsh-workflow-kit）、PRIVATE=1（建私有仓）
set -e
OWNER="${OWNER:-ff4554825-sys}"
NAME="${REPO_NAME:-dsh-workflow-kit}"
BRANCH="${BRANCH:-main}"
DESC="任务日志 v1.0：schema 校验、交付门、流程指标、aborted 根因案例"

cd "$(dirname "$0")/.."

if [ -n "$GITHUB_TOKEN" ]; then
  echo "== 用 token 建仓 $OWNER/$NAME =="
  code=$(curl -s -o /tmp/publish-resp.json -w '%{http_code}' -X POST \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H 'Accept: application/vnd.github+json' \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$NAME\",\"description\":\"$DESC\",\"private\":${PRIVATE:-false}}")
  echo "HTTP $code"
  cat /tmp/publish-resp.json | head -c 400; echo
  case "$code" in
    201) ;;
    422) echo "（仓库已存在，直接推送）" ;;
    *) echo "建仓失败，见上方响应"; exit 1 ;;
  esac
fi

echo "== 推送 =="
git remote get-url origin >/dev/null 2>&1 || \
  git remote add origin "git@github.com:$OWNER/$NAME.git"
git push -u origin "$BRANCH"
echo "完成：https://github.com/$OWNER/$NAME"
