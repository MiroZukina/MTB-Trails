from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.core.cache import cache
from django.db.models import Sum, Count, Q
import os
import math
import requests
from .models import Profile, Post, Comment, DIFFICULTY_COLORS
from django.contrib import messages
from django import forms
from .forms import PostForm, CommentForm, SignUpForm, ProfilePicForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    s = (math.sin(dLat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(s), math.sqrt(1 - s))


def _parse_gpx(gpx_file, max_points=500):
    import gpxpy
    content = gpx_file.read()
    try:
        gpx = gpxpy.parse(content)
    except Exception as e:
        raise ValueError(f"Invalid GPX file: {e}")

    all_pts = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                all_pts.append((
                    float(pt.latitude), float(pt.longitude),
                    float(pt.elevation) if pt.elevation is not None else None,
                ))
    if not all_pts:
        for route_obj in gpx.routes:
            for pt in route_obj.points:
                all_pts.append((
                    float(pt.latitude), float(pt.longitude),
                    float(pt.elevation) if pt.elevation is not None else None,
                ))

    if len(all_pts) < 2:
        raise ValueError("GPX file must contain at least 2 track/route points.")

    # Downsample evenly, always keeping first and last points
    if len(all_pts) > max_points:
        indices = [int(i * (len(all_pts) - 1) / (max_points - 1)) for i in range(max_points)]
        all_pts = [all_pts[i] for i in indices]

    route = [[pt[0], pt[1]] for pt in all_pts]

    has_elev = any(pt[2] is not None for pt in all_pts)
    if has_elev:
        elevations = [pt[2] for pt in all_pts]
        total_ascent_m = 0
        for i in range(1, len(all_pts)):
            e_curr, e_prev = all_pts[i][2], all_pts[i - 1][2]
            if e_curr is not None and e_prev is not None and e_curr > e_prev:
                total_ascent_m += e_curr - e_prev
        total_ascent_m = round(total_ascent_m)
    else:
        elevations = None
        total_ascent_m = None

    return route, elevations, total_ascent_m


def _maybe_parse_attachment_as_gpx(post, request):
    """If the post has no route yet and its attachment is a .gpx file, feed it
    through the same GPX parser used for gpx_file uploads. Parsing failures are
    swallowed — the attachment is still kept as a plain file, not an error."""
    if post.route or not post.attachment:
        return
    attachment_file = request.FILES.get('attachment')
    if not attachment_file or not attachment_file.name.lower().endswith('.gpx'):
        return
    try:
        attachment_file.seek(0)
        route, elevations, total_ascent_m = _parse_gpx(attachment_file)
        post.route = route
        post.latitude = route[0][0]
        post.longitude = route[0][1]
        post.elevations = elevations
        post.total_ascent_m = total_ascent_m
    except ValueError:
        pass
    finally:
        try:
            attachment_file.seek(0)
        except Exception:
            pass


WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY', '')

# Create your views here.
def home(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user

            gpx_file = request.FILES.get('gpx_file')
            gpx_ok = True
            if gpx_file:
                if gpx_file.size > 5 * 1024 * 1024:
                    messages.error(request, "GPX file must be under 5 MB.")
                    gpx_ok = False
                elif not gpx_file.name.lower().endswith('.gpx'):
                    messages.error(request, "Only .gpx files are accepted.")
                    gpx_ok = False
                else:
                    try:
                        route, elevations, total_ascent_m = _parse_gpx(gpx_file)
                        post.route = route
                        post.latitude = route[0][0]
                        post.longitude = route[0][1]
                        post.elevations = elevations
                        post.total_ascent_m = total_ascent_m
                    except ValueError as e:
                        messages.error(request, str(e))
                        gpx_ok = False

            _maybe_parse_attachment_as_gpx(post, request)

            if gpx_ok:
                post.save()
                messages.success(request, "Your Post Has Been Posted")
                return redirect('home')
    else:
        form = PostForm()

    posts = Post.objects.all().order_by("-created_at")
    comments = Comment.objects.all().order_by("-created_at")
    comment_form = CommentForm()

    if request.method == 'POST':
        post_id = request.POST.get('post_id')
        if post_id:
            comment_form = CommentForm(request.POST, request.FILES)
            if comment_form.is_valid():
                comment_post = posts.filter(pk=post_id).first()
                if comment_post is not None:
                    new_comment = comment_form.save(commit=False)
                    new_comment.user = request.user
                    new_comment.post = comment_post
                    new_comment.save()
                    messages.success(request, "Your Comment Has Been Posted")
                    return redirect('home')
                else:
                    messages.error(request, "Couldn't find the post to comment on.")

    # Near me: sort located posts by distance when ?lat=&lng= provided
    near_lat = request.GET.get('lat', '').strip()
    near_lng = request.GET.get('lng', '').strip()
    near_mode = False
    if near_lat and near_lng:
        try:
            nlat, nlng = float(near_lat), float(near_lng)
            located = []
            unlocated = []
            for p in posts:
                if p.has_location:
                    p.distance_km = round(_haversine_km(nlat, nlng, float(p.latitude), float(p.longitude)), 1)
                    located.append(p)
                else:
                    p.distance_km = None
                    unlocated.append(p)
            located.sort(key=lambda p: p.distance_km)
            posts = located + unlocated
            near_mode = True
        except (ValueError, TypeError):
            pass

    return render(request, 'home.html', {
        "posts": posts,
        "form": form,
        "comments": comments,
        "comment_form": comment_form,
        "near_mode": near_mode,
        "near_lat": near_lat,
        "near_lng": near_lng,
    })




def profile_list(request):
    if request.user.is_authenticated:
       profiles = Profile.objects.exclude(user=request.user)
       return render(request, 'profile_list.html', {"profiles":profiles})
    else:
        messages.success(request,("You Must Be Logged In To Viwe This Page...") )
        return redirect('home')
    

    

def profile(request, pk):
    if request.user.is_authenticated:
        profile = Profile.objects.get(user_id=pk)
        posts = Post.objects.filter(user_id=pk).order_by("-created_at")
        comment_form = CommentForm()

        if request.method == "POST":
            current_user_profile = request.user.profile
            action = request.POST.get('follow')

            if action == "unfollow":
                current_user_profile.follows.remove(profile)
            elif action == "follow":
                current_user_profile.follows.add(profile)
            current_user_profile.save()

            post_id = request.POST.get('post_id')
            if post_id:
                comment_form = CommentForm(request.POST, request.FILES)
                if comment_form.is_valid():
                    comment_post = posts.filter(pk=post_id).first()
                    if comment_post is not None:
                        new_comment = comment_form.save(commit=False)
                        new_comment.user = request.user
                        new_comment.post = comment_post
                        new_comment.save()
                        messages.success(request, "Your Comment Has Been Posted")
                        return redirect('profile', pk=pk)
                    else:
                        messages.error(request, "Couldn't find the post to comment on.")

        stats = posts.aggregate(
            total_distance_km=Sum('length_km'),
            total_ascent_m=Sum('total_ascent_m'),
            trail_count=Count('id', filter=Q(route__isnull=False)),
            pinned_count=Count('id', filter=Q(
                latitude__isnull=False, longitude__isnull=False, route__isnull=True
            )),
            green_count=Count('id', filter=Q(difficulty='green')),
            blue_count=Count('id', filter=Q(difficulty='blue')),
            red_count=Count('id', filter=Q(difficulty='red')),
            black_count=Count('id', filter=Q(difficulty='black')),
        )

        located_posts = posts.filter(latitude__isnull=False, longitude__isnull=False)

        map_data = [{
            'id': p.id,
            'lat': float(p.latitude),
            'lng': float(p.longitude),
            'body': p.body[:120],
            'author': p.user.username,
            'location': p.location_name,
            'length_km': float(p.length_km) if p.length_km else None,
            'route': p.route,
            'difficulty': p.difficulty or '',
            'diff_color': DIFFICULTY_COLORS.get(p.difficulty, '#e03030'),
            'diff_label': p.difficulty_label,
            'url': f'/post_show/{p.id}',
        } for p in located_posts]

        recent_trails = located_posts.order_by('-created_at')[:5]

        return render(request, "profile.html", {
            "profile": profile,
            "posts": posts,
            "comment_form": comment_form,
            "stats": stats,
            "map_data": map_data,
            "recent_trails": recent_trails,
        })
    else:
        messages.success(request, "You Must Be Logged In To View This Page...")
        return redirect('home')
    
    

    
def unfollow(request, pk):
    if request.user.is_authenticated:
        #get the profile to unfollow
        profile = Profile.objects.get(user_id=pk)
        #Unfollow the user
        request.user.profile.follows.remove(profile)
        #save our profile
        request.user.profile.save()
        messages.success(request,(f"You Have Successfully Unfollowd {profile.user.username}") )
        return redirect(request.META.get("HTTP_REFERER"))

    else:
        messages.success(request,("You Must Be Logged In To Viwe This Page...") )
        return redirect('home')
    

def follow(request, pk):
    if request.user.is_authenticated:
        #get the profile to follow
        profile = Profile.objects.get(user_id=pk)
        #follow the user
        request.user.profile.follows.add(profile)
        #save our profile
        request.user.profile.save()
        messages.success(request,(f"You Have Successfully Followd {profile.user.username}") )
        return redirect(request.META.get("HTTP_REFERER"))

    else:
        messages.success(request,("You Must Be Logged In To Viwe This Page...") )
        return redirect('home')

def login_user(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST["password"]
        user= authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request,("You Have Been Logged In On This Page...") )
            return redirect('home')
        else:
            messages.success(request,("There was an error logging in. Please Try Again...") )
            return redirect('login')

    else:
        return render(request, "login.html")


def logout_user(request):
    logout(request)
    messages.success(request,("You Have Been Logged Out...") )
    return redirect('home')

def register_user(request):
    form = SignUpForm()
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
           form.save()
           username = form.cleaned_data['username']
           password = form.cleaned_data['password1']
           user = authenticate(username=username, password=password )
           login(request, user)
           messages.success(request,("You Have Been successfully registred! Welcom!") )
           return redirect('home')
        

    return render(request, "register.html", {'form': form})

def update_user(request):
    if request.user.is_authenticated:
        current_user = User.objects.get(id=request.user.id)
        profile_user = Profile.objects.get(user_id=request.user.id)
        user_form = SignUpForm(request.POST or  None, request.FILES or None, instance=current_user ) 
        profile_form = ProfilePicForm(request.POST or  None, request.FILES or None, instance=profile_user ) 
        user_form.fields['username'].required = False

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            login(request, current_user)
            messages.success(request, f'Your Profile Has Been Updated!')
            return redirect('home')
        return render(request, "update_user.html", {'user_form': user_form,'profile_form':profile_form})
    else:
        messages.success(request, f'You Must Be logged In To View That Page...')
        return redirect('home')




    

def post_like(request, pk):
    if request.user.is_authenticated:
       post = get_object_or_404(Post, id=pk)
       if post.likes.filter(id=request.user.id):
          post.likes.remove(request.user)
       else:
          post.likes.add(request.user)

       
       return redirect(request.META.get("HTTP_REFERER"))


    else:
       messages.success(request, f'You Must Be logged In To View That Page...')
       return redirect('home')
    
def post_show(request, pk):
    post = get_object_or_404(Post, id=pk)
    comment_form = CommentForm()

    if request.method == 'POST':
        comment_form = CommentForm(request.POST, request.FILES)
        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.user = request.user
            new_comment.post = post
            new_comment.save()
            messages.success(request, "Your Comment Has Been Posted")
            return redirect('post_show', pk=pk)

    trail_weather = None
    if post.has_location and WEATHER_API_KEY:
        clat = round(float(post.latitude), 2)
        clng = round(float(post.longitude), 2)
        cache_key = f'trail_wx_{clat}_{clng}'
        trail_weather = cache.get(cache_key)
        if trail_weather is None:
            try:
                url = (f'https://api.openweathermap.org/data/2.5/weather'
                       f'?lat={clat}&lon={clng}&appid={WEATHER_API_KEY}')
                data = requests.get(url, timeout=5).json()
                if data.get('cod') == 200:
                    rain = data.get('rain', {})
                    rain_mm = rain.get('1h') or rain.get('3h')
                    trail_weather = {
                        'temp': round(data['main']['temp'] - 273.15),
                        'description': data['weather'][0]['description'],
                        'icon': data['weather'][0]['icon'],
                        'wind_kmh': round(data['wind']['speed'] * 3.6),
                        'humidity': data['main']['humidity'],
                        'rain_mm': rain_mm,
                    }
                    cache.set(cache_key, trail_weather, 1800)
            except Exception:
                pass
    return render(request, "post_show.html", {'post': post, 'trail_weather': trail_weather, 'comment_form': comment_form})
    
def delete_post(request, pk):
    if request.user.is_authenticated:
        post = get_object_or_404(Post, id=pk)
        #chacke to see if you own the post
        if request.user.username == post.user.username:
             #delete post
             post.delete()
             messages.success(request, "THe Post Has Been Deleted!")
             return redirect(request.META.get("HTTP_REFERER"))
        else:
             messages.success(request, "You Don't Own That post")
             return redirect('home')

    else:
         messages.success(request, f'PLease Log In To Continue..')
         return redirect(request.META.get("HTTP_REFERER"))



def edit_post(request, pk):
    if request.user.is_authenticated:
        post = get_object_or_404(Post, id=pk)
        if request.user.username == post.user.username:
            form = PostForm(request.POST or None, request.FILES or None, instance=post)
            if request.method == "POST":
                if form.is_valid():
                    post = form.save(commit=False)
                    post.user = request.user

                    gpx_file = request.FILES.get('gpx_file')
                    gpx_ok = True
                    if gpx_file:
                        if gpx_file.size > 5 * 1024 * 1024:
                            messages.error(request, "GPX file must be under 5 MB.")
                            gpx_ok = False
                        elif not gpx_file.name.lower().endswith('.gpx'):
                            messages.error(request, "Only .gpx files are accepted.")
                            gpx_ok = False
                        else:
                            try:
                                route, elevations, total_ascent_m = _parse_gpx(gpx_file)
                                post.route = route
                                post.latitude = route[0][0]
                                post.longitude = route[0][1]
                                post.elevations = elevations
                                post.total_ascent_m = total_ascent_m
                            except ValueError as e:
                                messages.error(request, str(e))
                                gpx_ok = False

                    _maybe_parse_attachment_as_gpx(post, request)

                    if gpx_ok:
                        post.save()
                        messages.success(request, "Your Post Has Been Updated!")
                        return redirect('home')
            return render(request, "edit_post.html", {"form": form, 'post': post})
        else:
            messages.success(request, "You Don't Own That post")
            return redirect('home')
    else:
        messages.success(request, "Please Log In To Continue.")
        return redirect('home')


def weather_widget(request):
    city = request.GET.get('city', '').strip()
    lat = request.GET.get('lat', '').strip()
    lon = request.GET.get('lon', '').strip()

    if city:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}'
    elif lat and lon:
        url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}'
    else:
        return JsonResponse({'error': 'Provide a city name or coordinates'}, status=400)

    try:
        data = requests.get(url, timeout=5).json()
        if data.get('cod') != 200:
            return JsonResponse({'error': data.get('message', 'City not found')}, status=404)
        wind_kmh = round(data['wind']['speed'] * 3.6)
        humidity = data['main']['humidity']
        if wind_kmh < 20 and humidity < 80:
            trail_status = 'Good to Ride'
            trail_class = 'condition-good'
        elif wind_kmh < 40 and humidity < 90:
            trail_status = 'Rideable'
            trail_class = 'condition-ok'
        else:
            trail_status = 'Tough Conditions'
            trail_class = 'condition-bad'
        return JsonResponse({
            'city': data['name'],
            'temperature': round(data['main']['temp'] - 273.15),
            'description': data['weather'][0]['description'],
            'icon': data['weather'][0]['icon'],
            'humidity': humidity,
            'wind_speed': wind_kmh,
            'trail_status': trail_status,
            'trail_class': trail_class,
        })
    except Exception:
        return JsonResponse({'error': 'Weather service unavailable'}, status=503)


def explore(request):
    posts = Post.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).select_related('user').order_by('-created_at')

    map_data = []
    for p in posts:
        map_data.append({
            'id': p.id,
            'lat': float(p.latitude),
            'lng': float(p.longitude),
            'body': p.body[:120],
            'author': p.user.username,
            'location': p.location_name,
            'length_km': float(p.length_km) if p.length_km else None,
            'route': p.route,
            'difficulty': p.difficulty or '',
            'diff_color': DIFFICULTY_COLORS.get(p.difficulty, '#e03030'),
            'diff_label': p.difficulty_label,
            'url': f'/post_show/{p.id}',
        })

    return render(request, 'explore.html', {'map_data': map_data})
