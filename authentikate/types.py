from strawberry import auto
import strawberry_django
from authentikate.models import App, User


@strawberry_django.type(User, pagination=True)
class User:
    id: auto


@strawberry_django.type(App, pagination=True)
class App:
    id: auto
