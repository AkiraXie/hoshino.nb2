# airflow-xcom-pull-in-template-string (AIR201)

Preview (since [0.15.11](https://github.com/astral-sh/ruff/releases/tag/0.15.11)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27airflow-xcom-pull-in-template-string%27%20OR%20AIR201)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fairflow%2Frules%2Fxcom_pull_in_template_string.rs#L51)

Derived from the **[Airflow](../#airflow-air)** linter.

Fix is sometimes available.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for Airflow operator keyword arguments that use a Jinja template
string containing a single `xcom_pull` call to retrieve another task's
output.

## Why is this bad?

Using `{{ ti.xcom_pull(task_ids='some_task') }}` as a string template to
access the output of an upstream task is less readable and more
error-prone than using the `.output` attribute on the task object
directly. The `.output` attribute provides better IDE support and makes
task dependencies more explicit.

## Example

```python
from airflow.operators.python import PythonOperator

task_1 = PythonOperator(task_id="task_1", python_callable=my_func)
task_2 = PythonOperator(
    task_id="task_2",
    op_args="{{ ti.xcom_pull(task_ids='task_1') }}",
)
```

Use instead:

```python
from airflow.operators.python import PythonOperator

task_1 = PythonOperator(task_id="task_1", python_callable=my_func)
task_2 = PythonOperator(
    task_id="task_2",
    op_args=task_1.output,
)
```

## Fix safety

The fix is always unsafe because the variable in scope that matches the
task ID may not be the Airflow task object that produced the `XCom` value.
