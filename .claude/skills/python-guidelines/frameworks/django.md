# Django Rules (Python)

7 rules that apply when the project uses **django**.
Load this file only if the project's manifest imports or depends on
`django`.

---

### django-all-with-model-form (DJ007)
Avoid the use of `fields = "__all__"` in Django `ModelForm` classes.
❌ 
```
from django.forms import ModelForm
class PostForm(ModelForm):
    class Meta:
        model = Post
        fields = "__all__"
```
✅ 
```
from django.forms import ModelForm
class PostForm(ModelForm):
    class Meta:
        model = Post
        fields = ["title", "content"]
```

### django-exclude-with-model-form (DJ006)
Avoid the use of `exclude` in Django `ModelForm` classes.
❌ 
```
from django.forms import ModelForm
class PostForm(ModelForm):
    class Meta:
        model = Post
        exclude = ["author"]
```
✅ 
```
from django.forms import ModelForm
class PostForm(ModelForm):
    class Meta:
        model = Post
        fields = ["title", "content"]
```

### django-locals-in-render-function (DJ003)
Avoid the use of `locals()` in `render` functions.
❌ 
```
from django.shortcuts import render
def index(request):
    posts = Post.objects.all()
    return render(request, "app/index.html", locals())
```
✅ 
```
from django.shortcuts import render
def index(request):
    posts = Post.objects.all()
    context = {"posts": posts}
    return render(request, "app/index.html", context)
```

### django-model-without-dunder-str (DJ008)
Ensure a `__str__` method is defined in Django models.
❌ 
```
from django.db import models
class MyModel(models.Model):
    field = models.CharField(max_length=255)
```
✅ 
```
from django.db import models
class MyModel(models.Model):
    field = models.CharField(max_length=255)
    def __str__(self):
        return f"{self.field}"
```

### django-non-leading-receiver-decorator (DJ013)
Ensure Django's `@receiver` decorator is listed first, prior to any other decorators.
❌ 
```
from django.dispatch import receiver
from django.db.models.signals import post_save
@transaction.atomic
@receiver(post_save, sender=MyModel)
def my_handler(sender, instance, created, **kwargs):
    pass
```
✅ 
```
from django.dispatch import receiver
from django.db.models.signals import post_save
@receiver(post_save, sender=MyModel)
@transaction.atomic
def my_handler(sender, instance, created, **kwargs):
    pass
```

### django-nullable-model-string-field (DJ001)
Nullable string-based fields (like `CharField` and `TextField`) in Django models.
❌ 
```
from django.db import models
class MyModel(models.Model):
    field = models.CharField(max_length=255, null=True)
```
✅ 
```
from django.db import models
class MyModel(models.Model):
    field = models.CharField(max_length=255, default="")
```

### django-unordered-body-content-in-model (DJ012)
Avoid the order of Model's inner classes, methods, and fields as per the Django Style Guide.
❌ 
```
from django.db import models
class StrBeforeFieldModel(models.Model):
    class Meta:
        verbose_name = "test"
        verbose_name_plural = "tests"
    def __str__(self):
…
```
✅ 
```
from django.db import models
class StrBeforeFieldModel(models.Model):
    first_name = models.CharField(max_length=32)
    last_name = models.CharField(max_length=40)
    class Meta:
        verbose_name = "test"
…
```
