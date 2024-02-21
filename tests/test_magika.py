from magika.prediction_mode import PredictionMode
from strawberry_django.test.client import TestClient
import boto3
from magika import Magika
from magika.content_types import ContentType
from magika.types import ModelFeatures, MagikaResult
from django.conf import settings
from .constants import TEST_BUCKET_NAME
from s3fs import S3FileSystem
from core.datalayer import Datalayer
from s3path import S3Path
from typing import Any, Optional, Tuple
from pathlib import Path
import os
from core.contrib.s3_magika import S3Magika
from core.contrib.inspect import inspector




def test_inspect_file() -> None:

    file_dir = settings.DEMOS_DIR / "cells1.tiff"

    m = Magika()

    assert m.identify_path(file_dir).output.mime_type == "image/tiff"





def test_bucket_creation() -> None:

    file_dir = settings.DEMOS_DIR / "cells1.tiff"


    datalayer = Datalayer()

    filesystem = datalayer.file_system
    s3 = datalayer.s3

    s3.create_bucket(Bucket=settings.FILE_BUCKET)




    s3.upload_file(file_dir, TEST_BUCKET_NAME, "cells1.tiff")


    







