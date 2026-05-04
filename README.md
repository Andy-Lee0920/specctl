# specctl

Spec-first workflow helper for student projects.

## Install

Recommended:

```bash
pipx install git+https://github.com/Andy-Lee0920/specctl.git
specctl --help
```

If `pipx` is missing on macOS:

```bash
brew install pipx
pipx ensurepath
```

For development:

```bash
git clone https://github.com/Andy-Lee0920/specctl.git
cd specctl
pip install -e .
specctl --help
```

## Quick start

```bash
specctl init
specctl start user-login
specctl submit docs/specs/user-login.md --notify --email
```

## Commands

```bash
specctl init
specctl start <feature_name>
specctl submit <spec_file> [--notify] [--email]
specctl notify <spec_file> [--email]
specctl ci-check [--base origin/main]
```
