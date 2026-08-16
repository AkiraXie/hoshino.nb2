# airflow3-incompatible-function-signature (AIR303)

Preview (since [0.14.11](https://github.com/astral-sh/ruff/releases/tag/0.14.11)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27airflow3-incompatible-function-signature%27%20OR%20AIR303)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fairflow%2Frules%2Ffunction_signature_change_in_3.rs#L38)

Derived from the **[Airflow](../#airflow-air)** linter.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for Airflow function calls that will raise a runtime error in Airflow 3.0
due to function signature changes, such as functions that changed to accept only
keyword arguments, parameter reordering, or parameter type changes.

## Why is this bad?

Airflow 3.0 introduces changes to function signatures. Code that
worked in Airflow 2.x will raise a runtime error if not updated in Airflow
3.0.

## Example

```python
from airflow.lineage.hook import HookLineageCollector

collector = HookLineageCollector()
# Passing positional arguments will raise a runtime error in Airflow 3.0
collector.create_asset("s3://bucket/key")
```

Use instead:

```python
from airflow.lineage.hook import HookLineageCollector

collector = HookLineageCollector()
# Passing arguments as keyword arguments instead of positional arguments
collector.create_asset(uri="s3://bucket/key")
```
