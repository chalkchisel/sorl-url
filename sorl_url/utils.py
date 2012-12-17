import hashlib
import json
import zlib
from django.core import signing
from django.core.urlresolvers import reverse
from django.db.models import get_model, Model
from django.utils.encoding import smart_str
from django.utils.functional import SimpleLazyObject, empty
from django.utils.importlib import import_module
from sorl.thumbnail.base import EXTENSIONS
from sorl.thumbnail.conf import settings

NO_DEFAULT = object()

_SETTINGS_HASH = None


def get_settings_hash():
    global _SETTINGS_HASH
    if _SETTINGS_HASH is None:
        _SETTINGS_HASH = hashlib.md5(json.dumps({
            'SORL_URL_CONFIG': settings.SORL_URL_CONFIG,
            'THUMBNAIL_FORMAT': settings.THUMBNAIL_FORMAT,
            'THUMBNAIL_COLORSPACE': settings.THUMBNAIL_COLORSPACE,
            'THUMBNAIL_UPSCALE': settings.THUMBNAIL_UPSCALE,
            'THUMBNAIL_QUALITY': settings.THUMBNAIL_QUALITY,
            'THUMBNAIL_PROGRESSIVE': settings.THUMBNAIL_PROGRESSIVE,
            'THUMBNAIL_ORIENTATION': settings.THUMBNAIL_ORIENTATION,
            'THUMBNAIL_DUMMY': settings.THUMBNAIL_DUMMY,
            'THUMBNAIL_DUMMY_SOURCE': settings.THUMBNAIL_DUMMY_SOURCE,
            'THUMBNAIL_DUMMY_RATIO': settings.THUMBNAIL_DUMMY_RATIO
        })).hexdigest()
    return _SETTINGS_HASH


def generate_key():
    m = hashlib.sha256(settings.SECRET_KEY)
    return m.digest()


def generate_salt(model_name, field_name, instance_key, instance=None):
    if instance is None:
        field_config = THUMBNAIL_OPTIONS[model_name][field_name]
        instance = field_config.get_instance(instance_key)

    field_value = getattr(instance, field_name).name

    return "sorl-%s(%s).%s=[%s]{%s}" % (model_name, instance_key, field_name, field_value, get_settings_hash())


def serialize_and_sign(payload, salt, compress=False):
    data = signing.JSONSerializer().dumps(payload)

    prefix = ""

    if compress:
        compressed = zlib.compress(data, 9)
        if len(compressed) < (len(data) - 1):  # Only use the compressed version if it's actually smaller
            data = compressed
            prefix = "."
    encoded = prefix + signing.b64_encode(data)
    return signing.Signer(None, salt=salt).sign(encoded)


def verify_and_load(candidate, salt):
    payload = smart_str(signing.Signer(None, salt=salt).unsign(candidate))
    if payload[0] == '.':
        data = zlib.decompress(signing.b64_decode(payload[1:]))
    else:
        data = signing.b64_decode(payload)
    return signing.JSONSerializer().loads(data)


def encode_for_url(payload, model_name, field_name, instance_key, instance=None, compress=True):
    salt = generate_salt(model_name, field_name, instance_key, instance=instance)
    return serialize_and_sign(payload, salt=salt, compress=compress)


def decode_from_url(encoded, model_name, field_name, instance_key, instance=None):
    salt = generate_salt(model_name, field_name, instance_key, instance=instance)
    return verify_and_load(encoded, salt=salt)


def lookup_field(obj, ref):
    current = obj
    for attr in ref.split('__'):
        current = getattr(current, attr)
    return current


class GettableWithConfig(object):
    _config = None
    _config_data = None

    def __init__(self, config):
        self._config_data = config

    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, item):
        return item in self.config

    @property
    def config(self):
        if self._config is None:
            self._config = self.build_config()
        return self._config

    def get(self, key, default=NO_DEFAULT):
        if default is NO_DEFAULT:
            return self.config.get(key)
        else:
            return self.config.get(key, default)

    def build_config(self):
        raise NotImplementedError()


class ThumbnailOptions(GettableWithConfig):
    def build_config(self):
        data = self._config_data if self._config_data else \
            getattr(settings, 'SORL_URL_CONFIG', {})

        config = {}
        for config_key, model_config in data.items():
            model_config = ModelConfig(model_config, config_key)
            model = model_config.model

            # Create a name-based mapping
            config[config_key] = model_config

            # Also keep a record of all the configurations associated with each model
            config.setdefault(model, [])
            config[model].append(model_config)

        return config

    def find_config_for_field(self, model, field):
        if isinstance(model, basestring):
            model = get_model(*(model.split('.')))

        configs = self.get(model, [])

        for config in configs:
            if field in config:
                return config[field]

    def build_url(self, instance, field, geometry_string, model=None, **options):
        model = model if model else type(instance)
        if model is SimpleLazyObject:
            if instance._wrapped == empty:
                instance._setup()
            model = type(instance._wrapped)

        field_config = self.find_config_for_field(model, field)

        if field_config is None:
            if isinstance(model, basestring):
                model_name = model
            else:
                model_name = "%s.%s" % (model._meta.app_label, model._meta.object_name)

            raise ValueError("No mapping defined for %s.%s" % (model_name, field))

        model_config = field_config.model_config

        # If the instance isn't a model, we assume it's a value-appropriate key
        # for example, it's allowable to specify ``model`` and an ID for instance
        # rather than an actual instance.
        # NOTE: This doesn't add any real efficiency (and may make thing less
        #       efficient in some cases), as we perform an instance lookup to
        #       be able to use the field's value in the generation of a salt.
        if isinstance(instance, Model):
            key = instance if not isinstance(instance, Model) else \
            lookup_field(instance, model_config.get_key_field())
        else:
            key = instance
            instance = field_config.get_instance(key)

        extension = EXTENSIONS[options.pop('format',
            field_config.options.get('format', settings.THUMBNAIL_FORMAT))]  # We transmit format information in the URL, not in options.

        config = {'geometry': geometry_string}
        if options:
            config['options'] = options

        encoded_config = encode_for_url(config, model_config.name,
            field_config.field, key, instance=instance)

        return "%s?config=%s" % (
            reverse('sorl_url', kwargs={
                'model_name': model_config.name,
                'field_name': field_config.field,
                'key': key,
                'extension': extension
            }),
            encoded_config
        )


class ModelConfig(GettableWithConfig):
    _backend = None

    def __init__(self, config, name):
        super(ModelConfig, self).__init__(config)
        self.model = get_model(*(config['model'].split('.')))
        self.name = name
        self.options = config.get('options', {})

    def get_instance(self, key):
        return self.model.objects.get(**{
            self.get_key_field(): self.get_key_filter()(key)
        })

    def get_key_field(self):
        return self._config_data.get('key_field', 'id')

    def get_key_filter(self):
        key_filter = self._config_data.get('key_filter', lambda x: int(x))
        if key_filter is None:
            key_filter = lambda x: x
        return key_filter

    def get_backend(self):
        if self._backend is None:
            backend = self._config_data.get('backend', 'sorl.thumbnail.default.backend')  # Don't worry, this respects settings.THUMBNAIL_BACKEND

            mod_name, classname = backend.rsplit('.', 1)
            mod = import_module(mod_name)
            self._backend = getattr(mod, classname)

        return self._backend

    def build_config(self):
        config = {}

        for field in self._config_data['fields']:
            if isinstance(field, basestring):
                config[field] = FieldConfig(self, field)
            else:
                field, options = field
                config[field] = FieldConfig(self, field, options)

        return config


class FieldConfig(object):
    def __init__(self, model_config, field, options=None):
        self.model_config = model_config
        self.field = field
        self._options = options or {}

    @property
    def options(self):
        opts = dict(self.model_config.options)
        opts.update(self._options)
        return opts

    def get_instance(self, key):
        return self.model_config.get_instance(key)

THUMBNAIL_OPTIONS = ThumbnailOptions(None)
