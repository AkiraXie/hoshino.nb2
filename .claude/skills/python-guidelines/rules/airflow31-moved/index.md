# airflow31-moved (AIR321)

Preview (since [0.15.1](https://github.com/astral-sh/ruff/releases/tag/0.15.1)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27airflow31-moved%27%20OR%20AIR321)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fairflow%2Frules%2Fmoved_in_3_1.rs#L33)

Derived from the **[Airflow](../#airflow-air)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for uses of deprecated or moved Airflow functions and values in Airflow 3.1.

## Why is this bad?

Airflow 3.1 deprecated or moved various functions, members, and other values.

## Example

```python
from airflow.utils.timezone import convert_to_utc
from datetime import datetime

convert_to_utc(datetime.now())
```

Use instead:

```python
from airflow.sdk.timezone import convert_to_utc
from datetime import datetime

convert_to_utc(datetime.now())
```
