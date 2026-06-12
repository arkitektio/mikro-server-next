from django.db import models
from django.contrib.auth import get_user_model
from koherent.fields import ProvenanceField
from koherent.models import Task as KoherentTask
from authentikate.models import Organization, Membership
from kante.types import Info
from taggit.managers import TaggableManager
from datalayer.models import BigFileStore, ParquetStore


class DatasetManager(models.Manager):
    def get_current_default(self, info: Info, created_through: KoherentTask | None = None) -> "Dataset":
        potential = self.filter(creator=info.context.request.user, organization=info.context.request.organization, membership=info.context.request.membership, is_default=True).first()
        if not potential:
            return self.create(creator=info.context.request.user, organization=info.context.request.organization, membership=info.context.request.membership, name="Default", is_default=True, created_through=created_through, created_through_by_id=created_through.assigner_id if created_through else None)

        return potential


class Dataset(models.Model):
    """
    A dataset is a collection of data files and metadata files.
    It mimics the concept of a folder in a file system and is the top level
    object in the data model.

    """

    creator = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="created_datasets",
        help_text="The user that created the dataset",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="The time the dataset was created")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children")
    name = models.CharField(max_length=200, help_text="The name of the dataset")
    description_two = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        help_text="The description of the dataset, this is a second description field",
    )
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="datasets")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    description = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        help_text="The description of the dataset",
    )
    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_datasets",
        blank=True,
        help_text="The users that have pinned the dataset",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether the dataset is the current default dataset for the user",
    )
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()
    tags = TaggableManager()

    objects = DatasetManager()

    def __str__(self) -> str:
        return super().__str__()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["creator", "is_default", "organization"],
                name="unique_default_per_creator",
                condition=models.Q(is_default=True),
            ),
            models.UniqueConstraint(
                fields=["parent", "name"],
                name="only_one_dataset_per_parent_and_name",
            ),
        ]


class File(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="files")
    origins = models.ManyToManyField(
        "self",
        related_name="derived",
        symmetrical=False,
    )
    store = models.ForeignKey(
        BigFileStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the file",
    )
    name = models.CharField(max_length=1000, help_text="The name of the file", default="")
    created_at = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True)
    organization = models.ForeignKey(
        "authentikate.Organization",
        on_delete=models.CASCADE,
        related_name="files",
    )
    size = models.BigIntegerField(help_text="The size of the file in bytes", null=True, blank=True)
    content_type = models.CharField(max_length=1000, help_text="The content type of the file", null=True, blank=True)
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="files")
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )

    provenance = ProvenanceField()


class Table(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name="tables")
    origins = models.ManyToManyField(
        "self",
        related_name="derived",
        symmetrical=False,
    )
    store = models.ForeignKey(
        ParquetStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the table",
    )
    name = models.CharField(max_length=1000, help_text="The name of the image", default="")
    created_at = models.DateTimeField(auto_now_add=True)
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    created_through = models.ForeignKey(
        "koherent.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)ss",
        help_text="The task this object was created through, if any",
    )
    created_through_by = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_%(class)ss",
        help_text="The assigner of the creating task, denormalized for fast filtering",
    )
    provenance = ProvenanceField()


class Experiment(models.Model):
    name = models.CharField(max_length=1000, help_text="The name of the experiment")
    description = models.CharField(
        max_length=1000,
        help_text="The description of the experiment",
        null=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

    provenance = ProvenanceField()


class Mesh(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, null=True, blank=True, related_name="meshes")
    name = models.CharField(max_length=1000, help_text="The name of the mesh")
    store = models.ForeignKey(
        BigFileStore,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The store of the mesh",
    )
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    pinned_by = models.ManyToManyField(
        get_user_model(),
        related_name="pinned_meshes",
        help_text="The users that have pinned the images",
    )
