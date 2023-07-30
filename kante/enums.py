from django.db.models import TextChoices


class ProvenanceAction(TextChoices):
    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    RELATE = "RELATE", "Relate"
    UNRELATE = "UNRELATE", "Unrelate"
