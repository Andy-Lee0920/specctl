import argparse
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path
from importlib.resources import files

import yaml


SPEC_DIR = Path("docs/specs")
TEAM_FILE = Path(".specctl/team.yml")

REQUIRED_SECTIONS = [
    "## Target User",
    "## Problem",
    "## P0",
    "## P1",
    "## P2",
    "## Not Building",
    "## User Flow",
    "## AI Behavior",
    "## Validation Plan",
    "## Demo Acceptance Criteria",
]


def run(cmd, capture=False, check=True):
    if capture:
        result = subprocess.run(cmd, text=True, capture_output=True, check=check)
        return result.stdout.strip()

    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, text=True, check=check)
    return ""


def template_text(name):
    return files("specctl.templates").joinpath(name).read_text(encoding="utf-8")


def write_file_if_missing(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        print(f"SKIP existing {path}")
        return

    path.write_text(content, encoding="utf-8")
    print(f"CREATED {path}")


def init_repo(args):
    write_file_if_missing(".specctl/team.yml", template_text("team.yml"))
    write_file_if_missing("templates/SPEC_TEMPLATE.md", template_text("SPEC_TEMPLATE.md"))
    write_file_if_missing(".github/pull_request_template.md", template_text("pull_request_template.md"))
    write_file_if_missing(".github/workflows/spec-check.yml", template_text("spec-check.yml"))

    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    write_file_if_missing("docs/specs/.gitkeep", "")

    print("\n✅ specctl initialized.")
    print("Next:")
    print("  1. Edit .specctl/team.yml")
    print("  2. git add .specctl .github templates docs")
    print('  3. git commit -m "chore: add spec workflow"')
    print("  4. git push")


def current_branch():
    return run(["git", "branch", "--show-current"], capture=True)


def start_spec(args):
    feature = args.feature_name
    spec_path = SPEC_DIR / f"{feature}.md"
    branch = f"spec/{feature}"

    if spec_path.exists():
        print(f"❌ Spec already exists: {spec_path}")
        sys.exit(1)

    run(["git", "switch", "main"])
    run(["git", "pull", "origin", "main"])
    run(["git", "switch", "-c", branch])

    content = template_text("SPEC_TEMPLATE.md").replace("{{FEATURE_NAME}}", feature)
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(content, encoding="utf-8")

    print(f"\n✅ Created {spec_path}")
    print("Next:")
    print(f"  1. Edit {spec_path}")
    print(f"  2. specctl check {spec_path}")
    print(f"  3. specctl submit {spec_path} --notify --email")


def check_spec_file(spec_file):
    path = Path(spec_file)

    if not path.exists():
        print(f"❌ File not found: {path}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    errors = []

    for section in REQUIRED_SECTIONS:
        if section not in text:
            errors.append(f"Missing section: {section}")

    lower = text.lower()

    if "## ai behavior" in lower:
        if "model" not in lower:
            errors.append("AI Behavior should include model")
        if "input" not in lower:
            errors.append("AI Behavior should include input")
        if "output" not in lower:
            errors.append("AI Behavior should include output")
        if "fallback" not in lower and "failure" not in lower:
            errors.append("AI Behavior should include failure/fallback")

    if errors:
        print("❌ SPEC CHECK FAILED\n")
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}")
        sys.exit(1)

    print("✅ SPEC CHECK PASSED")


def check_spec(args):
    check_spec_file(args.spec_file)


def changed_files_against_head():
    output = run(["git", "diff", "--name-only", "HEAD"], capture=True)
    return [line for line in output.splitlines() if line.strip()]


def changed_files_against_base(base):
    output = run(["git", "diff", "--name-only", f"{base}...HEAD"], capture=True)
    return [line for line in output.splitlines() if line.strip()]


def ensure_spec_only(changed_files):
    invalid = [
        f for f in changed_files
        if not f.startswith("docs/specs/")
    ]

    if invalid:
        print("❌ Spec-only check failed.")
        print("Spec PR must only change files under docs/specs/.\n")
        print("Invalid files:")
        for f in invalid:
            print(f"- {f}")
        sys.exit(1)

    print("✅ Only spec files changed")


def load_team_members():
    if not TEAM_FILE.exists():
        print("⚠️ .specctl/team.yml not found. Skipping notification.")
        return []

    data = yaml.safe_load(TEAM_FILE.read_text(encoding="utf-8")) or {}
    members = data.get("members", [])

    github_ids = []
    for member in members:
        github = member.get("github")
        if github and "github-id" not in github:
            github_ids.append(github)

    return github_ids

def load_team_emails():
    if not TEAM_FILE.exists():
        print("⚠️ .specctl/team.yml not found. Skipping email notification.")
        return []

    data = yaml.safe_load(TEAM_FILE.read_text(encoding="utf-8")) or {}
    members = data.get("members", [])

    emails = []

    for member in members:
        email = member.get("email")
        if email and "example.com" not in email:
            emails.append(email)

    return emails


def create_pr(spec_file):
    branch = current_branch()
    title = f"Spec: {Path(spec_file).stem}"

    body = f"""Spec-only PR for `{spec_file}`.

Please review:
1. Is the target user specific?
2. Are P0 / P1 / P2 priorities reasonable?
3. Is "Not Building" clear?
4. If AI is used, are model/input/output/fallback clear?
5. Is the validation plan testable with a real user?
"""

    try:
        url = run(
            [
                "gh",
                "pr",
                "create",
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ],
            capture=True,
        )
        print(f"✅ Created PR: {url}")
        return url

    except FileNotFoundError:
        print("❌ GitHub CLI `gh` is not installed.")
        print("Install GitHub CLI, then run:")
        print("  gh auth login")
        sys.exit(1)

    except subprocess.CalledProcessError:
        print("⚠️ Could not create a new PR. Checking whether a PR already exists for this branch...")

        try:
            existing_url = run(
                [
                    "gh",
                    "pr",
                    "view",
                    branch,
                    "--json",
                    "url",
                    "--jq",
                    ".url",
                ],
                capture=True,
            )

            if existing_url:
                print(f"✅ Existing PR found: {existing_url}")
                return existing_url

        except subprocess.CalledProcessError:
            pass

        print("❌ Failed to create or find PR.")
        print("Please check GitHub CLI authentication:")
        print("  gh auth status")
        print("  gh auth login")
        sys.exit(1)

def notify_reviewers(spec_file):
    github_ids = load_team_members()

    if not github_ids:
        print("⚠️ No GitHub reviewers found in .specctl/team.yml")
        return

    mentions = " ".join(f"@{github_id}" for github_id in github_ids)

    body = f"""{mentions}

Spec review requested for `{spec_file}`.

Please review:
1. Is the target user specific?
2. Are P0 / P1 / P2 priorities reasonable?
3. Is "Not Building" clear?
4. If AI is used, are model/input/output/fallback clear?
5. Is the validation plan testable with a real user?
"""

    try:
        run(["gh", "pr", "comment", "--body", body])
        print("✅ Posted reviewer mention comment")
    except subprocess.CalledProcessError:
        print("⚠️ Failed to post reviewer comment")
        print("You can manually mention reviewers in the PR.")


def submit_spec(args):
    spec_file = args.spec_file

    check_spec_file(spec_file)

    changed_files = changed_files_against_head()

    if not changed_files:
        print("❌ No local changes to submit")
        sys.exit(1)

    ensure_spec_only(changed_files)

    run(["git", "add", "docs/specs"])
    run(["git", "commit", "-m", f"docs: add/update spec {Path(spec_file).stem}"])
    run(["git", "push", "-u", "origin", current_branch()])

    pr_url = create_pr(spec_file)

    if args.notify:
        notify_reviewers(spec_file)

    if args.email:
        send_review_email(spec_file, pr_url)

def notify_spec(args):
    spec_file = args.spec_file

    check_spec_file(spec_file)

    branch = current_branch()
    if not branch.startswith("spec/"):
        print(f"⚠️ Current branch is `{branch}`.")
        print("Notifications are usually sent from a spec/* branch.")

    try:
        pr_url = run(
            ["gh", "pr", "view", "--json", "url", "--jq", ".url"],
            capture=True,
        )
        if not pr_url:
            print("❌ No pull request found for the current branch.")
            print("Create a PR first, then run this command again.")
            sys.exit(1)

        print(f"✅ Found PR: {pr_url}")
    except FileNotFoundError:
        print("❌ GitHub CLI `gh` is not installed.")
        print("Install GitHub CLI and run:")
        print(" gh auth login")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ No pull request found for the current branch.")
        print("Create a PR first, then run this command again.")
        sys.exit(1)

    notify_reviewers(spec_file)

def ci_check(args):
    changed_files = changed_files_against_base(args.base)

    if not changed_files:
        print("No changed files.")
        return

    branch = current_branch()

    if branch.startswith("spec/"):
        ensure_spec_only(changed_files)

    spec_files = [
        f for f in changed_files
        if f.startswith("docs/specs/") and f.endswith(".md")
    ]

    for spec_file in spec_files:
        check_spec_file(spec_file)

    print("✅ CI spec check passed")

def build_review_email_body(spec_file, pr_url):
    return f"""새로운 spec review 요청이 도착했습니다.

Spec file:
{spec_file}

Pull Request:
{pr_url}

아래 기준으로 리뷰해주세요.

1. Target user가 충분히 구체적인가?
2. P0 / P1 / P2 우선순위가 적절한가?
3. "Not Building"이 명확한가?
4. AI를 쓴다면 model/input/output/fallback이 명확한가?
5. Validation plan이 실제 사용자 검증으로 이어질 수 있는가?

피드백은 GitHub PR에 comment로 남겨주세요.
"""

def send_review_email(spec_file, pr_url):
    recipients = load_team_emails()

    if not recipients:
        print("⚠️ No reviewer emails found in .specctl/team.yml")
        return

    smtp_host = os.getenv("SPECCTL_SMTP_HOST")
    smtp_port = int(os.getenv("SPECCTL_SMTP_PORT", "587"))
    smtp_username = os.getenv("SPECCTL_SMTP_USERNAME")
    smtp_password = os.getenv("SPECCTL_SMTP_PASSWORD")
    email_from = os.getenv("SPECCTL_EMAIL_FROM", smtp_username)

    missing = []

    if not smtp_host:
        missing.append("SPECCTL_SMTP_HOST")
    if not smtp_username:
        missing.append("SPECCTL_SMTP_USERNAME")
    if not smtp_password:
        missing.append("SPECCTL_SMTP_PASSWORD")
    if not email_from:
        missing.append("SPECCTL_EMAIL_FROM")

    if missing:
        print("⚠️ Email notification skipped.")
        print("Missing environment variables:")
        for name in missing:
            print(f"- {name}")
        print("\nExample:")
        print('  export SPECCTL_SMTP_HOST="smtp.gmail.com"')
        print('  export SPECCTL_SMTP_PORT="587"')
        print('  export SPECCTL_SMTP_USERNAME="your-email@example.com"')
        print('  export SPECCTL_SMTP_PASSWORD="your-app-password"')
        print('  export SPECCTL_EMAIL_FROM="your-email@example.com"')
        return

    subject = f"[Spec Review Needed] {Path(spec_file).stem}"
    body = build_review_email_body(spec_file, pr_url)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)

        print(f"✅ Sent review email to {len(recipients)} reviewer(s)")

    except Exception as e:
        print("⚠️ Failed to send review email.")
        print(f"Reason: {e}")
        print("GitHub PR was still created successfully.")

def main():
    parser = argparse.ArgumentParser(prog="specctl")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init")
    p.set_defaults(func=init_repo)

    p = sub.add_parser("start")
    p.add_argument("feature_name")
    p.set_defaults(func=start_spec)

    p = sub.add_parser("check")
    p.add_argument("spec_file")
    p.set_defaults(func=check_spec)

    p = sub.add_parser("submit")
    p.add_argument("spec_file")
    p.add_argument("--notify", action="store_true")
    p.set_defaults(func=submit_spec)

    p = sub.add_parser("notify")
    p.add_argument("spec_file")
    p.set_defaults(func=notify_spec)

    p = sub.add_parser("ci-check")
    p.add_argument("--base", default="origin/main")
    p.set_defaults(func=ci_check)

    args = parser.parse_args()
    args.func(args)