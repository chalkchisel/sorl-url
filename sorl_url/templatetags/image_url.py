import re
from django import template
from django.utils.encoding import smart_str
from sorl.thumbnail.conf import settings
from sorl.thumbnail.images import DummyImageFile
from sorl.thumbnail.templatetags.thumbnail import ThumbnailNodeBase
from sorl_url.utils import THUMBNAIL_OPTIONS


register = template.Library()
kw_pat = re.compile(r'^(?P<key>[\w]+)=(?P<value>.+)$')


@register.tag
def image_url(parser, token):
    return ImageURLNode(parser, token)


class ImageURLNode(ThumbnailNodeBase):
    error_msg = ('Syntax error. Expected: ``image_url SOURCE FIELD_NAME GEOMETRY '
                 '[key1=VAL1 key2=VAL2...] [as VAR]``')

    def __init__(self, parser, token):
        bits = token.split_contents()

        self.direct_usage = not bits[-2] == "as"

        if len(bits) < 4 or len(bits) < 6 and not self.direct_usage:
            raise template.TemplateSyntaxError(self.error_msg)
        self.instance = parser.compile_filter(bits[1])
        self.field = parser.compile_filter(bits[2])
        self.geometry = parser.compile_filter(bits[3])
        self.options = []
        optlist = bits[4:] if self.direct_usage else bits[4:-2]
        for bit in optlist:
            m = kw_pat.match(bit)
            if not m:
                raise template.TemplateSyntaxError(self.error_msg)
            key = smart_str(m.group('key'))
            expr = parser.compile_filter(m.group('value'))
            self.options.append((key, expr))

        if not self.direct_usage:
            self.child_nodelists = ('nodelist_file', 'nodelist_empty')
            self.as_var = bits[-1]
            self.nodelist_file = parser.parse(('empty', 'endimage_url',))
            if parser.next_token().contents == 'empty':
                self.nodelist_empty = parser.parse(('endimage_url',))
                parser.delete_first_token()
        else:
            self.nodelist_file = None
            self.nodelist_empty = parser.create_nodelist()

    def _render(self, context):
        instance = self.instance.resolve(context)
        field = self.field.resolve(context)
        geometry = self.geometry.resolve(context)
        options = {}
        for key, expr in self.options:
            noresolve = {u'True': True, u'False': False, u'None': None}
            value = noresolve.get(unicode(expr), expr.resolve(context))
            if key == 'options':
                options.update(value)
            else:
                options[key] = value
        if settings.THUMBNAIL_DUMMY:
            thumbnail_url = DummyImageFile(geometry).url
        elif getattr(instance, field):
            thumbnail_url = THUMBNAIL_OPTIONS.build_url(instance, field, geometry, **options)
        else:
            return self.nodelist_empty.render(context)

        if self.direct_usage:
            return thumbnail_url
        else:
            context.push()
            context[self.as_var] = thumbnail_url
            output = self.nodelist_file.render(context)
            context.pop()
            return output

    def __repr__(self):
        return "<ImageURLNode>"

    def __iter__(self):
        for node in self.nodelist_file:
            yield node
        for node in self.nodelist_empty:
            yield node
