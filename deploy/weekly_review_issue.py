"""Upsert one weekly merged-strategy review Issue for manual ChatGPT handoff."""
import os
from pathlib import Path
from india_trader.research_review import _api_request

TITLE = "[Weekly AI Review] Paper trading strategy improvement"
MARKER = "<!-- merged-paper-ai-review-v1 -->"


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    content = Path("trader/backtests/merged_strategy_review.md").read_text()
    run = os.environ.get("GITHUB_RUN_ID", "")
    body = MARKER + "\n" + content + "\n"
    if run:
        body += f"Full JSON and markdown artifacts: https://github.com/{repo}/actions/runs/{run}\n"
    body += "\nReview only: no automatic trading strategy modifications.\n"
    root = "/repos/" + repo + "/issues"
    existing = None
    for page in range(1, 6):
        items = _api_request(token, root + f"?state=open&per_page=100&page={page}")
        existing = next((item for item in items if item.get("title") == TITLE
                         and MARKER in (item.get("body") or "")
                         and "pull_request" not in item), None)
        if existing or len(items) < 100:
            break
    if existing:
        result = _api_request(token, root + "/" + str(existing["number"]),
                              method="PATCH", body={"body": body})
    else:
        result = _api_request(token, root, method="POST",
                              body={"title": TITLE, "body": body})
    print("WEEKLY_AI_REVIEW_ISSUE " + result["html_url"])


if __name__ == "__main__":
    main()
