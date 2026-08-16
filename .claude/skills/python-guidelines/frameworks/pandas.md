# Pandas Rules (Python)

13 rules that apply when the project uses **pandas**.
Load this file only if the project's manifest imports or depends on
`pandas`.

---

### pandas-df-variable-name (PD901)
Avoid assignments to the variable `df`.
❌ 
```
import pandas as pd
df = pd.read_csv("animals.csv")
```
✅ 
```
import pandas as pd
animals = pd.read_csv("animals.csv")
```

### pandas-nunique-constant-series-check (PD101)
Avoid uses of `.nunique()` to check if a Pandas Series is constant (i.e., contains only one unique value).
❌ 
```
import pandas as pd
data = pd.Series(range(1000))
if data.nunique() <= 1:
    print("Series is constant")
```
✅ 
```
import pandas as pd
data = pd.Series(range(1000))
array = data.to_numpy()
if array.shape[0] == 0 or (array[0] == array).all():
    print("Series is constant")
```

### pandas-use-of-dot-at (PD008)
Avoid uses of `.at` on Pandas objects.
❌ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.at["Maria"]
```
✅ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.loc["Maria"]
```

### pandas-use-of-dot-iat (PD009)
Avoid uses of `.iat` on Pandas objects.
❌ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.iat[0]
```
✅ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.iloc[0]
```

### pandas-use-of-dot-is-null (PD003)
Avoid uses of `.isnull` on Pandas objects.
❌ 
```
import pandas as pd
animals_df = pd.read_csv("animals.csv")
pd.isnull(animals_df)
```
✅ 
```
import pandas as pd
animals_df = pd.read_csv("animals.csv")
pd.isna(animals_df)
```

### pandas-use-of-dot-ix (PD007)
Avoid uses of `.ix` on Pandas objects.
❌ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.ix[0]  # 0th row or row with label 0?
```
✅ 
```
import pandas as pd
students_df = pd.read_csv("students.csv")
students_df.iloc[0]  # 0th row.
```

### pandas-use-of-dot-not-null (PD004)
Avoid uses of `.notnull` on Pandas objects.
❌ 
```
import pandas as pd
animals_df = pd.read_csv("animals.csv")
pd.notnull(animals_df)
```
✅ 
```
import pandas as pd
animals_df = pd.read_csv("animals.csv")
pd.notna(animals_df)
```

### pandas-use-of-dot-pivot-or-unstack (PD010)
Avoid uses of `.pivot` or `.unstack` on Pandas objects.
❌ 
```
import pandas as pd
df = pd.read_csv("cities.csv")
df.pivot(index="city", columns="year", values="population")
```
✅ 
```
import pandas as pd
df = pd.read_csv("cities.csv")
df.pivot_table(index="city", columns="year", values="population")
```

### pandas-use-of-dot-read-table (PD012)
Avoid uses of `pd.read_table` to read CSV files.
❌ 
```
import pandas as pd
cities_df = pd.read_table("cities.csv", sep=",")
```
✅ 
```
import pandas as pd
cities_df = pd.read_csv("cities.csv")
```

### pandas-use-of-dot-stack (PD013)
Avoid uses of `.stack` on Pandas objects.
❌ 
```
import pandas as pd
cities_df = pd.read_csv("cities.csv")
cities_df.set_index("city").stack()
```
✅ 
```
import pandas as pd
cities_df = pd.read_csv("cities.csv")
cities_df.melt(id_vars="city")
```

### pandas-use-of-dot-values (PD011)
Avoid uses of `.values` on Pandas Series and Index objects.
❌ 
```
import pandas as pd
animals = pd.read_csv("animals.csv").values  # Ambiguous.
```
✅ 
```
import pandas as pd
animals = pd.read_csv("animals.csv").to_numpy()  # Explicit.
```

### pandas-use-of-inplace-argument (PD002)
Avoid `inplace=True` usages in `pandas` function and method calls.
❌ 
```
import pandas as pd
students = pd.read_csv("students.csv")
students.sort_values("name", inplace=True)
```
✅ 
```
import pandas as pd
students = pd.read_csv("students.csv").sort_values("name")
```

### pandas-use-of-pd-merge (PD015)
Avoid uses of `pd.merge` on Pandas objects.
❌ 
```
import pandas as pd
cats_df = pd.read_csv("cats.csv")
dogs_df = pd.read_csv("dogs.csv")
rabbits_df = pd.read_csv("rabbits.csv")
pets_df = pd.merge(pd.merge(cats_df, dogs_df), rabbits_df)  # Hard to read.
```
✅ 
```
import pandas as pd
cats_df = pd.read_csv("cats.csv")
dogs_df = pd.read_csv("dogs.csv")
rabbits_df = pd.read_csv("rabbits.csv")
pets_df = cats_df.merge(dogs_df).merge(rabbits_df)
```
