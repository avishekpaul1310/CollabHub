from django.shortcuts import render, redirect
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm
from django.conf import settings
import os

def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'Account created for {username}! You can now log in.')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})

@login_required
def profile(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
    
    context = {
        'u_form': u_form,
        'p_form': p_form
    }
    return render(request, 'users/profile.html', context)

@login_required
def remove_profile_picture(request):
    if request.method == 'POST':
        profile = request.user.profile
        
        # Check if profile has a custom image (not the default)
        if profile.avatar and 'default.png' not in profile.avatar.path:
            # Get the file path
            file_path = profile.avatar.path
            
            # Check if file exists and delete it
            if os.path.exists(file_path):
                os.remove(file_path)
            
            # Reset avatar field to default
            profile.avatar = 'default.png'
            profile.save()
            
            messages.success(request, 'Profile picture removed successfully!')
        else:
            messages.info(request, 'No custom profile picture to remove.')
            
    return redirect('profile')