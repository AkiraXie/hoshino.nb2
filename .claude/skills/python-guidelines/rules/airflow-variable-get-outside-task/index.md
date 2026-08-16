# airflow-variable-get-outside-task (AIR003)

Preview (since [0.15.6](https://github.com/astral-sh/ruff/releases/tag/0.15.6)) ·
[Related issues](https://github.com/astral-sh/ruff/issues?q=sort%3Aupdated-desc%20is%3Aissue%20is%3Aopen%20(%27airflow-variable-get-outside-task%27%20OR%20AIR003)) ·
[View source](https://github.com/astral-sh/ruff/blob/main/crates%2Fruff_linter%2Fsrc%2Frules%2Fairflow%2Frules%2Fvariable_get_outside_task.rs#L56)

Derived from the **[Airflow](../#airflow-air)** linter.

This rule is unstable and in [preview](../../preview/). The `--preview` flag is required for use.

## What it does

Checks for `Variable.get()` calls outside of Airflow task execution
context (i.e., outside `@task`-decorated functions and operator
`execute()` methods).

## Why is this bad?

Calling `Variable.get()` at module level or in operator constructor
arguments causes a database query every time the Dag file is parsed
by the scheduler. This can degrade Dag parsing performance and, in
some cases, cause the Dag file to time out before it is fully parsed.

Instead, pass Airflow Variables to operators via Jinja templates
(`{{ var.value.my_var }}` or `{{ var.json.my_var }}`), which defer
the lookup until task execution.

`Variable.get()` inside `@task`-decorated functions and operator
`execute()` methods is fine because those only run during task
execution, not during Dag parsing.

Note that this rule may produce false positives for helper functions
that are only invoked at task execution time (e.g., passed as
`python_callable` to `PythonOperator`). In such cases, suppress the
diagnostic with `# noqa: AIR003`.

## Example

```python
from airflow.sdk import Variable
from airflow.operators.bash import BashOperator

foo = Variable.get("foo")
BashOperator(task_id="bad", bash_command="echo $FOO", env={"FOO": foo})
```

Use instead:

```python
from airflow.operators.bash import BashOperator

BashOperator(
    task_id="good",
    bash_command="echo $FOO",
    env={"FOO": "{{ var.value.foo }}"},
)
```
