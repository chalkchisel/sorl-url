from django.conf import settings
from django.dispatch import receiver, Signal
from django.db.models.signals import post_save
from django.db.models.loading import get_model
from sorl_url.utils import THUMBNAIL_OPTIONS

precache_sorl = Signal(providing_args=['instance', 'config'])


@receiver(post_save)
def spawn_pre_cache_signal(sender, instance, created, **kwargs):
    configs = THUMBNAIL_OPTIONS.get(sender, {})
    for config in configs:
        if config and config.precache:
            precache_sorl.send(sender=sender, instance=instance,
                model_config=config)


def handle_precache(sender, instance, model_config, **kwargs):
    generated = []
    try:
        all_fields = model_config.keys()
        model_options = model_config.options
        backend = model_config.get_backend()
        for geometry, extra_opts in model_config.precache.items():
            fields = extra_opts.pop('fields', all_fields)
            options = dict(model_options)
            options.update(extra_opts)
            for field_name in fields:
                file_field = getattr(instance, field_name)
                thumbnail = backend.get_thumbnail(file_field, geometry, **options)
                generated.append(thumbnail)
    except:
        if not kwargs.get('fail_silently', True):
            raise
    return generated


try:
    import celery
except ImportError:
    celery = None

if celery:
    # We put this at this module level so a developer can gain
    # access even if SORL_URL_PRECACHE != 'celery'
    @celery.task(ignore_result=True)
    def handle_precache_task(sender_model, instance_model, instance_pk,
        model_config, **kwargs):
        sender = get_model(*sender_model.split('.'))
        instance = get_model(*instance_model.split('.'))\
            .objects.get(pk=instance_pk)
        handle_precache(sender, instance, model_config, **kwargs)

    def delay_precache(sender, instance, model_config, **kwargs):
        sender_model = "%s.%s" % (sender._meta.app_label,
            sender._meta.object_name)
        instance_model = "%s.%s" % (instance._meta.app_label,
            instance._meta.object_name)
        kwargs.pop('signal', None)  # Signals can't be pickled
        handle_precache_task.delay(sender_model, instance_model,
            instance.pk, model_config, **kwargs)

# A developer may choose to use a method other than Django signals
# (e.g. non-Celery task queue) to handle the precache actions.
_precache = getattr(settings, 'SORL_URL_PRECACHE', True)
if celery and _precache == "celery":
    precache_sorl.connect(delay_precache)
elif _precache:
    precache_sorl.connect(handle_precache)
