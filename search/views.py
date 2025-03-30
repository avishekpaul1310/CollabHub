from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.db.models import Q
from django.contrib import messages
from django.utils.text import slugify
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
import json
import logging
from datetime import timedelta
from django.utils import timezone

from workspace.models import WorkItem, Message, FileAttachment, Thread, SlowChannel
from .models import SavedSearch, SearchLog, FileIndex
from .forms import SavedSearchForm, AdvancedSearchForm

logger = logging.getLogger(__name__)

@login_required
def search_view(request):
    """Main search view with advanced filters"""
    query = request.GET.get('q', '')
    form = AdvancedSearchForm(request.GET)
    
    # Get saved searches for the user
    saved_searches = SavedSearch.objects.filter(user=request.user)
    
    results = []
    total_results = 0
    
    # Process search and filters when form is valid
    if query or (form.is_valid() and any(form.cleaned_data.values())):
        # Log this search
        log_search(request, query, request.GET.dict(), 0)
        
        # Get filter values from form
        filters = {}
        if form.is_valid():
            filters = form.cleaned_data
            
        # Get content types to search or default to all
        content_types = filters.get('content_types', [])
        if not content_types:
            content_types = ['work_item', 'message', 'thread', 'file', 'channel']
            
        # Initialize counters
        work_items_count = 0
        messages_count = 0
        files_count = 0
        threads_count = 0
        channels_count = 0
        
        # Perform filtered searches based on content types
        work_items = []
        messages = []
        threads = []
        files = []
        channels = []
        
        if 'work_item' in content_types:
            work_items = search_work_items(request.user, query, filters)
            work_items_count = work_items.count()
            
        if 'message' in content_types:
            messages = search_messages(request.user, query, filters)
            messages_count = messages.count()
            
        if 'thread' in content_types:
            threads = search_threads(request.user, query, filters)
            threads_count = threads.count()
            
        if 'file' in content_types:
            files = search_files(request.user, query, filters)
            files_count = files.count()
            
        if 'channel' in content_types:
            channels = search_channels(request.user, query, filters)
            channels_count = channels.count()
        
        # Combine and format results
        results = []
        
        # Add work items to results
        for item in work_items:
            results.append({
                'type': 'work_item',
                'object': item,
                'title': item.title,
                'preview': item.description[:150] + '...' if len(item.description) > 150 else item.description,
                'url': reverse('work_item_detail', args=[item.pk]),
                'date': item.updated_at,
                'owner': item.owner,
                'relevance_score': calculate_relevance(query, item.title, item.description)
            })
        
        # Add messages to results
        for msg in messages:
            results.append({
                'type': 'message',
                'object': msg,
                'title': f"Message in {msg.work_item.title}",
                'preview': msg.content[:150] + '...' if len(msg.content) > 150 else msg.content,
                'url': get_message_url(msg),
                'date': msg.created_at,
                'owner': msg.user,
                'relevance_score': calculate_relevance(query, msg.content)
            })
            
        # Add threads to results
        for thread in threads:
            results.append({
                'type': 'thread',
                'object': thread,
                'title': thread.title,
                'preview': f"Thread in {thread.work_item.title}",
                'url': reverse('thread_detail', args=[thread.work_item.pk, thread.pk]),
                'date': thread.updated_at,
                'owner': thread.created_by,
                'relevance_score': calculate_relevance(query, thread.title)
            })
        
        # Add files to results
        for file in files:
            preview = ""
            if hasattr(file, 'index') and file.index:
                preview = file.index.extracted_text[:150] + '...' if len(file.index.extracted_text) > 150 else file.index.extracted_text
            
            results.append({
                'type': 'file',
                'object': file,
                'title': file.name,
                'preview': preview,
                'url': file.file.url,
                'date': file.uploaded_at,
                'owner': file.uploaded_by,
                'relevance_score': calculate_relevance(query, file.name, preview)
            })
            
        # Add channels to results
        for channel in channels:
            results.append({
                'type': 'channel',
                'object': channel,
                'title': channel.title,
                'preview': channel.description[:150] + '...' if len(channel.description) > 150 else channel.description,
                'url': reverse('slow_channel_detail', args=[channel.pk]),
                'date': channel.created_at,
                'owner': channel.created_by,
                'relevance_score': calculate_relevance(query, channel.title, channel.description)
            })
        
        # Sort results by relevance score and date
        results.sort(key=lambda x: (-x['relevance_score'], -x['date'].timestamp()))
        
        # Update total counts
        total_results = len(results)
        
        # Update search log
        update_search_log(request, query, request.GET.dict(), total_results)
    
    # Pagination
    paginator = Paginator(results, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get recent searches
    recent_searches = SearchLog.objects.filter(user=request.user).order_by('-timestamp')[:5]
    
    context = {
        'query': query,
        'form': form,
        'results': page_obj,
        'total_results': total_results,
        'work_items_count': work_items_count,
        'messages_count': messages_count,
        'files_count': files_count,
        'threads_count': threads_count,
        'channels_count': channels_count,
        'saved_searches': saved_searches,
        'recent_searches': recent_searches,
    }
    
    # AJAX response for filtering
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        result_html = render(request, 'search/partials/search_results.html', context).content.decode('utf-8')
        return JsonResponse({
            'html': result_html,
            'total': total_results,
            'work_items': work_items_count,
            'messages': messages_count,
            'files': files_count,
            'threads': threads_count,
            'channels': channels_count,
        })
    
    return render(request, 'search/search.html', context)

def search_work_items(user, query, filters=None):
    """Search for work items with proper permission checks"""
    if filters is None:
        filters = {}
        
    # Base query: user must be owner or collaborator
    items = WorkItem.objects.filter(
        Q(owner=user) | Q(collaborators=user)
    ).distinct()
    
    # Apply text search if query provided
    if query:
        items = items.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query)
        )
    
    # Apply filters
    if filters.get('type'):
        items = items.filter(type=filters['type'])
        
    if filters.get('owner'):
        # Look up owner by username
        owner_filter = filters['owner']
        items = items.filter(owner__username__icontains=owner_filter)
        
    if filters.get('user'):
        # Check if created by this user (owner)
        user_filter = filters['user']
        items = items.filter(owner__username__icontains=user_filter)
        
    if filters.get('date_from'):
        items = items.filter(created_at__gte=filters['date_from'])
        
    if filters.get('date_to'):
        items = items.filter(created_at__lte=filters['date_to'])
        
    if filters.get('recent'):
        days = int(filters['recent'])
        items = items.filter(updated_at__gte=timezone.now() - timedelta(days=days))
    
    return items

def search_messages(user, query, filters=None):
    """Search for messages with proper permission checks"""
    if filters is None:
        filters = {}
        
    # Base query: only messages in work items the user can access
    accessible_work_items = WorkItem.objects.filter(
        Q(owner=user) | Q(collaborators=user)
    ).values_list('id', flat=True)
    
    messages = Message.objects.filter(
        work_item_id__in=accessible_work_items
    )
    
    # If searching within threads, also check thread access
    if 'thread' in filters and filters['thread'] == 'only':
        messages = messages.filter(thread__isnull=False)
        
        # For private threads, check access control
        private_threads = Thread.objects.filter(is_public=False).values_list('id', flat=True)
        messages = messages.exclude(
            Q(thread_id__in=private_threads) & 
            ~Q(thread__allowed_users=user) & 
            ~Q(thread__created_by=user) &
            ~Q(thread__work_item__owner=user)
        )
    elif 'thread' in filters and filters['thread'] == 'exclude':
        messages = messages.filter(thread__isnull=True)
    
    # Apply text search if query provided
    if query:
        messages = messages.filter(content__icontains=query)
    
    # Apply filters
    if filters.get('user'):
        messages = messages.filter(user__username=filters['user'])
        
    if filters.get('date_from'):
        messages = messages.filter(created_at__gte=filters['date_from'])
        
    if filters.get('date_to'):
        messages = messages.filter(created_at__lte=filters['date_to'])
        
    if filters.get('recent'):
        days = int(filters['recent'])
        messages = messages.filter(created_at__gte=timezone.now() - timedelta(days=days))
    
    return messages

def search_threads(user, query, filters=None):
    """Search for threads with proper permission checks"""
    if filters is None:
        filters = {}
        
    # Base query: only threads in work items the user can access
    accessible_work_items = WorkItem.objects.filter(
        Q(owner=user) | Q(collaborators=user)
    ).values_list('id', flat=True)
    
    # Start with an empty queryset
    threads = Thread.objects.none()
    
    # Get public threads
    public_threads = Thread.objects.filter(
        work_item_id__in=accessible_work_items,
        is_public=True
    )
    
    # Get accessible private threads
    # User can access private threads if:
    # 1. They created the thread
    # 2. They are in the allowed_users list
    # 3. They are the work item owner (for moderation)
    accessible_private_threads = Thread.objects.filter(
        work_item_id__in=accessible_work_items,
        is_public=False
    ).filter(
        Q(created_by=user) | 
        Q(allowed_users=user) | 
        Q(work_item__owner=user)
    ).distinct()
    
    # Combine threads using UNION instead of | operator
    # We'll use a list to collect the threads and then create a new queryset
    thread_ids = list(public_threads.values_list('id', flat=True))
    thread_ids.extend(list(accessible_private_threads.values_list('id', flat=True)))
    
    # Get unique IDs
    unique_thread_ids = list(set(thread_ids))
    
    # Create a new queryset with the combined IDs
    threads = Thread.objects.filter(id__in=unique_thread_ids)
    
    # Apply text search if query provided
    if query:
        threads = threads.filter(title__icontains=query)
    
    # Apply filters
    if filters.get('user'):
        threads = threads.filter(created_by__username=filters['user'])
        
    if filters.get('date_from'):
        threads = threads.filter(created_at__gte=filters['date_from'])
        
    if filters.get('date_to'):
        threads = threads.filter(created_at__lte=filters['date_to'])
    
    if filters.get('visibility') == 'public':
        threads = threads.filter(is_public=True)
    elif filters.get('visibility') == 'private':
        threads = threads.filter(is_public=False)
        
    if filters.get('recent'):
        days = int(filters['recent'])
        threads = threads.filter(updated_at__gte=timezone.now() - timedelta(days=days))
    
    return threads

def search_files(user, query, filters=None):
    """Search for files with proper permission checks"""
    if filters is None:
        filters = {}
        
    # Base query: only files in work items the user can access
    accessible_work_items = WorkItem.objects.filter(
        Q(owner=user) | Q(collaborators=user)
    ).values_list('id', flat=True)
    
    files = FileAttachment.objects.filter(
        work_item_id__in=accessible_work_items
    )
    
    # Apply text search if query provided
    if query:
        # Search both filenames and indexed content
        file_name_matches = files.filter(name__icontains=query)
        
        # Search in file index (extracted text content)
        indexed_file_ids = FileIndex.objects.filter(
            extracted_text__icontains=query
        ).values_list('file_id', flat=True)
        
        indexed_matches = files.filter(id__in=indexed_file_ids)
        
        # Combine results
        files = (file_name_matches | indexed_matches).distinct()
    
    # Apply filters
    if filters.get('user'):
        files = files.filter(uploaded_by__username=filters['user'])
        
    if filters.get('date_from'):
        files = files.filter(uploaded_at__gte=filters['date_from'])
        
    if filters.get('date_to'):
        files = files.filter(uploaded_at__lte=filters['date_to'])
        
    if filters.get('recent'):
        days = int(filters['recent'])
        files = files.filter(uploaded_at__gte=timezone.now() - timedelta(days=days))
        
    file_type = filters.get('file_type')
    if file_type:
        if file_type == 'document':
            # Match document formats
            files = files.filter(
                Q(name__endswith='.doc') | Q(name__endswith='.docx') | 
                Q(name__endswith='.pdf') | Q(name__endswith='.txt') |
                Q(name__endswith='.rtf') | Q(name__endswith='.odt')
            )
        elif file_type == 'image':
            # Match image formats
            files = files.filter(
                Q(name__endswith='.jpg') | Q(name__endswith='.jpeg') | 
                Q(name__endswith='.png') | Q(name__endswith='.gif') |
                Q(name__endswith='.bmp') | Q(name__endswith='.svg')
            )
        elif file_type == 'spreadsheet':
            # Match spreadsheet formats
            files = files.filter(
                Q(name__endswith='.xls') | Q(name__endswith='.xlsx') | 
                Q(name__endswith='.csv') | Q(name__endswith='.ods')
            )
        elif file_type == 'code':
            # Match code formats
            files = files.filter(
                Q(name__endswith='.py') | Q(name__endswith='.js') | 
                Q(name__endswith='.java') | Q(name__endswith='.c') |
                Q(name__endswith='.cpp') | Q(name__endswith='.h') |
                Q(name__endswith='.cs') | Q(name__endswith='.php') |
                Q(name__endswith='.rb') | Q(name__endswith='.html') |
                Q(name__endswith='.css') | Q(name__endswith='.ts')
            )
    
    return files

def search_channels(user, query, filters=None):
    """Search for slow channels with proper permission checks"""
    if filters is None:
        filters = {}
        
    # Only channels the user is participating in
    channels = SlowChannel.objects.filter(participants=user)
    
    # Apply text search if query provided
    if query:
        channels = channels.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query)
        )
    
    # Apply filters
    if filters.get('user'):
        channels = channels.filter(created_by__username=filters['user'])
        
    if filters.get('date_from'):
        channels = channels.filter(created_at__gte=filters['date_from'])
        
    if filters.get('date_to'):
        channels = channels.filter(created_at__lte=filters['date_to'])
        
    if filters.get('recent'):
        days = int(filters['recent'])
        channels = channels.filter(created_at__gte=timezone.now() - timedelta(days=days))
        
    if filters.get('channel_type'):
        channels = channels.filter(type=filters['channel_type'])
    
    return channels

def calculate_relevance(query, *fields):
    """
    Calculate a simple relevance score for search results
    Higher scores indicate better matches
    """
    if not query:
        return 0
    
    score = 0
    query_terms = query.lower().split()
    
    for field in fields:
        if not field:
            continue
            
        field_lower = field.lower()
        
        # Exact match has highest priority
        if query.lower() == field_lower:
            score += 10
            
        # Title starts with query
        elif field_lower.startswith(query.lower()):
            score += 5
            
        # Check for individual terms
        for term in query_terms:
            if term in field_lower:
                score += 1
                
                # Bonus for whole word matches
                if f" {term} " in f" {field_lower} ":
                    score += 1
    
    return score

def get_message_url(message):
    """Get the URL for a message (in a thread or work item)"""
    if message.thread:
        return reverse('thread_detail', args=[message.work_item.pk, message.thread.pk]) + f'#message-{message.id}'
    else:
        return reverse('work_item_detail', args=[message.work_item.pk]) + f'#chat-messages'

def log_search(request, query, filters, count=0):
    """Log a search query to the user's search history"""
    try:
        # Convert filters to JSON string
        filters_json = json.dumps(filters)
        
        # Create the search log entry
        SearchLog.objects.create(
            user=request.user,
            query=query,
            filters=filters_json,
            results_count=count
        )
    except Exception as e:
        logger.error(f"Error logging search: {str(e)}")

def update_search_log(request, query, filters, count):
    """Update the most recent search log with the result count"""
    try:
        # Convert filters to JSON string
        filters_json = json.dumps(filters)
        
        # Find the most recent matching search log and update it
        recent_log = SearchLog.objects.filter(
            user=request.user,
            query=query,
            filters=filters_json
        ).order_by('-timestamp').first()
        
        if recent_log:
            recent_log.results_count = count
            recent_log.save()
    except Exception as e:
        logger.error(f"Error updating search log: {str(e)}")

@login_required
def saved_search_list(request):
    """View to list, create, and manage saved searches"""
    saved_searches = SavedSearch.objects.filter(user=request.user)
    form = SavedSearchForm()
    
    if request.method == 'POST':
        form = SavedSearchForm(request.POST)
        if form.is_valid():
            saved_search = form.save(commit=False)
            saved_search.user = request.user
            
            # Convert the current search filters to JSON
            current_filters = {}
            for key, value in request.GET.items():
                if key not in ['q', 'page', 'csrfmiddlewaretoken'] and value:
                    current_filters[key] = value
                    
            saved_search.query = request.GET.get('q', '')
            saved_search.filters = json.dumps(current_filters)
            saved_search.save()
            
            messages.success(request, f'Search "{saved_search.name}" has been saved')
            return redirect('saved_searches')
    
    context = {
        'saved_searches': saved_searches,
        'form': form
    }
    
    return render(request, 'search/saved_searches.html', context)

@login_required
def saved_search_detail(request, slug):
    """Load and execute a saved search"""
    saved_search = get_object_or_404(SavedSearch, slug=slug, user=request.user)
    
    # Get the saved query and filters
    query = saved_search.query
    filters = saved_search.get_filters()
    
    # Redirect to search view with these parameters
    url = reverse('search')
    params = {'q': query}
    params.update(filters)
    
    # Build query string manually to handle lists
    query_params = []
    for key, value in params.items():
        if isinstance(value, list):
            for item in value:
                query_params.append(f"{key}={item}")
        else:
            query_params.append(f"{key}={value}")
    
    query_string = "&".join(query_params)
    
    return redirect(f"{url}?{query_string}")

@login_required
@require_POST
def delete_saved_search(request, pk):
    """Delete a saved search"""
    saved_search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    name = saved_search.name
    saved_search.delete()
    
    messages.success(request, f'Saved search "{name}" has been deleted')
    
    # Return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
        
    return redirect('saved_searches')

@login_required
@require_POST
def set_default_search(request, pk):
    """Set a search as the user's default"""
    saved_search = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    
    # Unset any existing defaults
    SavedSearch.objects.filter(user=request.user, is_default=True).update(is_default=False)
    
    # Set this as default
    saved_search.is_default = True
    saved_search.save()
    
    messages.success(request, f'"{saved_search.name}" is now your default search')
    
    # Return JSON for AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
        
    return redirect('saved_searches')

@login_required
def clear_search_history(request):
    """Clear the user's search history"""
    if request.method == 'POST':
        SearchLog.objects.filter(user=request.user).delete()
        messages.success(request, 'Your search history has been cleared')
        
        # Return JSON for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success'})
    
    return redirect('search')