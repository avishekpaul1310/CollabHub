def get_user_unread_count(user, thread=None, work_item=None):
    """Get count of unread messages for a user in a specific thread or work item"""
    from django.db.models import Q, Exists, OuterRef
    from workspace.models import Message, MessageReadReceipt
    
    # Base query to get all messages that could be visible to this user
    base_query = Message.objects.filter(
        ~Q(user=user)  # Exclude messages sent by the user
    )
    
    # Filter by thread or work item if specified
    if thread:
        base_query = base_query.filter(thread=thread)
    elif work_item:
        base_query = base_query.filter(work_item=work_item)
    
    # Filter to get only messages the user hasn't read yet
    receipts_subquery = MessageReadReceipt.objects.filter(
        message=OuterRef('pk'),
        user=user
    )
    
    unread_messages = base_query.filter(~Exists(receipts_subquery))
    
    return unread_messages.count()