# Setup Guide

## Prerequisites

- Python 3.12 or newer

## Create Virtual Environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

If `python3.12` is unavailable, use your Python 3.12+ executable.

## Install Dependencies

```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

## Environment Configuration

```bash
cp .env.example .env
```

Update `.env` values for your local environment. Do not commit `.env`.
