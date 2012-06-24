from django.conf.urls import patterns
from django.conf.urls import url
from sorl_url.views import image_handler


urlpatterns = patterns('',
    url(r'^(?P<model_name>[\w-]+)/(?P<field_name>[\w-]+)/(?P<key>[\w-]+)\.(?P<extension>[\w]+)$',
        image_handler, name='sorl_url'),
)
