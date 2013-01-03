from django.conf import settings
from django.dispatch import receiver, Signal
from django.db.models.signals import post_save
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
    except Exception, e:
        if not kwargs.get('fail_silently', True):
            raise


# A developer may choose to use a method other than Django signals
# (e.g. Celery) to handle the precache actions.
if getattr(settings, 'SORL_URL_PRECACHE', True):
    precache_sorl.connect(handle_precache)
