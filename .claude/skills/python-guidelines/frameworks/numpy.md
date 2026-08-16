# Numpy Rules (Python)

4 rules that apply when the project uses **numpy**.
Load this file only if the project's manifest imports or depends on
`numpy`.

---

### numpy-deprecated-function (NPY003)
Avoid uses of deprecated NumPy functions.
❌ 
```
import numpy as np
np.alltrue([True, False])
```
✅ 
```
import numpy as np
np.all([True, False])
```

### numpy-deprecated-type-alias (NPY001)
Avoid deprecated NumPy type aliases.
❌ 
```
import numpy as np
np.int
```
✅ `int`

### numpy-legacy-random (NPY002)
Avoid the use of legacy `np.random` function calls.
❌ 
```
import numpy as np
np.random.seed(1337)
np.random.normal()
```
✅ 
```
rng = np.random.default_rng(1337)
rng.normal()
```

### numpy2-deprecation (NPY201)
Avoid uses of NumPy functions and constants that were removed from the main namespace in NumPy 2.0.
❌ 
```
import numpy as np
arr1 = [np.Infinity, np.NaN, np.nan, np.PINF, np.inf]
arr2 = [np.float_(1.5), np.float64(5.1)]
np.round_(arr2)
```
✅ 
```
import numpy as np
arr1 = [np.inf, np.nan, np.nan, np.inf, np.inf]
arr2 = [np.float64(1.5), np.float64(5.1)]
np.round(arr2)
```
