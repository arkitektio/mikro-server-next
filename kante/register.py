import strawberry_django


def register_model(*args, **kwargs):
    return strawberry_django.type(*args, **kwargs)
