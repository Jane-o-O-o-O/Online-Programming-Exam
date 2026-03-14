from django.shortcuts import render


def app_shell(request):
    return render(request, "app.html")
