from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpResponseRedirect, HttpResponsePermanentRedirect
from django.shortcuts import render_to_response
from django.views.decorators.cache import cache_page
from sorl.thumbnail.conf import settings
from sorl_url.utils import decode_from_url, THUMBNAIL_OPTIONS

VALID_EXTENSIONS = {
    "JPG": "JPEG",
    "PNG": "PNG"
}


@cache_page(60 * 15)
def image_handler(request, model_name, field_name, key, extension):
    extension = extension.upper()
    if extension not in VALID_EXTENSIONS:
        raise Http404("Unknown extension: %s" % extension)

    try:
        field_config = THUMBNAIL_OPTIONS[model_name][field_name]
    except KeyError:
        raise Http404("No configuration found for %s.%s" % (model_name, field_name))

    try:
        instance = field_config.get_instance(key)
    except ObjectDoesNotExist:
        raise Http404("%s with key '%s' not found" % (model_name, key))

    file_field = getattr(instance, field_name)

    config = request.GET.get('config', [])
    if config:
        try:
            config = decode_from_url(config, model_name, field_name, key, instance=instance)
        except:
            if settings.DEBUG:
                raise
            else:
                raise Http404("Could not decode configuration.")
    else:
        raise Http404("No image configuration provided.")

    if settings.THUMBNAIL_DEBUG and \
        request.GET.get('echo', 'no').lower() in ['true', 'yes']:
        return render_to_response("sorl_url/debug.html", config)

    options = dict(field_config.options)
    options.update(config.get('options', {}))
    options['format'] = VALID_EXTENSIONS[extension]

    backend = field_config.model_config.get_backend()
    thumbnail = backend.get_thumbnail(file_field, config['geometry'], **options)

    if getattr(settings, 'SORL_URL_PERMANENT_REDIRECT', False):
        redirect = HttpResponsePermanentRedirect
    else:
        redirect = HttpResponseRedirect

    return redirect(thumbnail.url)
