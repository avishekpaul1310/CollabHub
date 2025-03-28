from django.urls import re_path
from workspace.consumers import ChatConsumer, NotificationConsumer, ThreadConsumer

websocket_urlpatterns = [
    re_path(r'ws/chat/(?P<work_item_id>\w+)/$', ChatConsumer.as_asgi()),
    re_path(r'ws/thread/(?P<thread_id>\w+)/$', ThreadConsumer.as_asgi()),
    re_path(r'ws/notifications/$', NotificationConsumer.as_asgi()),
]