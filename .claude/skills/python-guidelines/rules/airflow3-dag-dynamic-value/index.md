# airflow3-dag-dynamic-value (AIR304)

Preview (since [0.15.6](https://github.com/astral-sh/ruff/releases/tag/0.15.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27airflow3-dag-dynamic-value%27%20OR%20AIR304)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fairflow%2Frules%2Fruntime_value_in_dag_or_task.rs#L39)

Derived from the **[Airflow](../#airflow-air)** linter.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for calls to runtime-varying functions (such as `datetime.now()`)
used as arguments in Airflow Dag or task constructors.

## Why is this bad?

Using runtime-varying values as arguments to Dag or task constructors
causes the serialized Dag hash to change on every parse, creating
infinite Dag versions in the `dag_version` and `serialized_dag` tables.
This leads to unbounded database growth and can eventually cause
out-of-memory conditions.

## Example

```python
from datetime import datetime

from airflow import DAG

dag = DAG(dag_id="my_dag", start_date=datetime.now())
```

Use instead:

```python
from datetime import datetime

from airflow import DAG

dag = DAG(dag_id="my_dag", start_date=datetime(2024, 1, 1))
```
