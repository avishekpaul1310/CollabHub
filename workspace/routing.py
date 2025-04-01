from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<work_item_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/thread/(?P<work_item_id>\d+)/(?P<thread_id>\d+)/$', consumers.ThreadConsumer.as_asgi()),
    re_path(r'ws/file/(?P<work_item_id>\d+)/$', consumers.FileConsumer.as_asgi()),
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]