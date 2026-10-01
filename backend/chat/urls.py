from django.urls import path

from .views import ChatView, ConversationDetailView, ConversationListView

urlpatterns = [
    path(
        "conversations/",
        ConversationListView.as_view(),
        name="conversation-list",
    ),
    path(
        "conversations/<uuid:conversation_id>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path("", ChatView.as_view(), name="chat"),
]
