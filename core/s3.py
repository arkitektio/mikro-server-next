import boto3
from django.conf import settings

sts = boto3.client(
    "sts",
    endpoint_url=settings.AWS_S3_ENDPOINT_URL,
    region_name="us-east-1",
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    aws_session_token=None,
    config=boto3.session.Config(signature_version="s3v4"),
    verify=False,
)
