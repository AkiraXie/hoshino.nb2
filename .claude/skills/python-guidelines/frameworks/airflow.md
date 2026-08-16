# Airflow Rules (Python)

11 rules that apply when the project uses **airflow**.
Load this file only if the project's manifest imports or depends on
`airflow`.

---

### airflow-dag-no-schedule-argument (AIR002)
Avoid a `DAG()` class or `@dag()` decorator without an explicit `schedule` (or `schedule_interval` for Airflow 1) parameter.

### airflow-variable-get-outside-task (AIR003)
Avoid `Variable.get()` calls outside of Airflow task execution context (i.e., outside `@task`-decorated functions and operator `execute()` methods).
❌ 
```
from airflow.sdk import Variable
from airflow.operators.bash import BashOperator
foo = Variable.get("foo")
BashOperator(task_id="bad", bash_command="echo $FOO", env={"FOO": foo})
```
✅ 
```
from airflow.operators.bash import BashOperator
BashOperator(
    task_id="good",
    bash_command="echo $FOO",
    env={"FOO": "{{ var.value.foo }}"},
)
```

### airflow-variable-name-task-id-mismatch (AIR001)
Ensure the task variable name matches the `task_id` value for Airflow Operators.
❌ 
```
from airflow.operators import PythonOperator
incorrect_name = PythonOperator(task_id="my_task")
```
✅ 
```
from airflow.operators import PythonOperator
my_task = PythonOperator(task_id="my_task")
```

### airflow-xcom-pull-in-template-string (AIR201)
Avoid Airflow operator keyword arguments that use a Jinja template string containing a single `xcom_pull` call to retrieve another task's output.
❌ 
```
from airflow.operators.python import PythonOperator
task_1 = PythonOperator(task_id="task_1", python_callable=my_func)
task_2 = PythonOperator(
    task_id="task_2",
    op_args="{{ ti.xcom_pull(task_ids='task_1') }}",
)
```
✅ 
```
from airflow.operators.python import PythonOperator
task_1 = PythonOperator(task_id="task_1", python_callable=my_func)
task_2 = PythonOperator(
    task_id="task_2",
    op_args=task_1.output,
)
```

### airflow3-dag-dynamic-value (AIR304)
Avoid calls to runtime-varying functions (such as `datetime.now()`) used as arguments in Airflow Dag or task constructors.
❌ 
```
from datetime import datetime
from airflow import DAG
dag = DAG(dag_id="my_dag", start_date=datetime.now())
```
✅ 
```
from datetime import datetime
from airflow import DAG
dag = DAG(dag_id="my_dag", start_date=datetime(2024, 1, 1))
```

### airflow3-incompatible-function-signature (AIR303)
Avoid Airflow function calls that will raise a runtime error in Airflow 3.0 due to function signature changes, such as functions that changed to accept only keyword arguments, parameter reordering, or parameter type changes.

### airflow3-moved-to-provider (AIR302)
Avoid uses of Airflow functions and values that have been moved to its providers (e.g., `apache-airflow-providers-fab`).
❌ 
```
from airflow.auth.managers.fab.fab_auth_manager import FabAuthManager
fab_auth_manager_app = FabAuthManager().get_fastapi_app()
```
✅ 
```
from airflow.providers.fab.auth_manager.fab_auth_manager import FabAuthManager
fab_auth_manager_app = FabAuthManager().get_fastapi_app()
```

### airflow3-removal (AIR301)
Avoid uses of deprecated Airflow functions and values.
❌ 
```
from airflow.utils.dates import days_ago
yesterday = days_ago(today, 1)
```
✅ 
```
from datetime import timedelta
yesterday = today - timedelta(days=1)
```

### airflow3-suggested-to-move-to-provider (AIR312)
Avoid uses of Airflow functions and values that have been moved to its providers but still have a compatibility layer (e.g., `apache-airflow-providers-standard`).
❌ 
```
from airflow.operators.python import PythonOperator
def print_context(ds=None, **kwargs):
    print(kwargs)
    print(ds)
print_the_context = PythonOperator(
    task_id="print_the_context", python_callable=print_context
…
```
✅ 
```
from airflow.providers.standard.operators.python import PythonOperator
def print_context(ds=None, **kwargs):
    print(kwargs)
    print(ds)
print_the_context = PythonOperator(
    task_id="print_the_context", python_callable=print_context
…
```

### airflow3-suggested-update (AIR311)
Avoid uses of deprecated Airflow functions and values that still have a compatibility layer.
❌ 
```
from airflow import Dataset
Dataset(uri="test://test/")
```
✅ 
```
from airflow.sdk import Asset
Asset(uri="test://test/")
```

### airflow31-moved (AIR321)
Avoid uses of deprecated or moved Airflow functions and values in Airflow 3.1.
❌ 
```
from airflow.utils.timezone import convert_to_utc
from datetime import datetime
convert_to_utc(datetime.now())
```
✅ 
```
from airflow.sdk.timezone import convert_to_utc
from datetime import datetime
convert_to_utc(datetime.now())
```
