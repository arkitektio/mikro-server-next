from contextvars import ContextVar
from functools import cached_property
import boto3
from django.conf import settings
import dataclasses
from strawberry.extensions import SchemaExtension
from s3fs import S3FileSystem
from typing import Any, Optional, Tuple, Generator



datalayer: ContextVar["Datalayer"] = ContextVar("datalayer")


class Datalayer:

    @cached_property
    def s3(self) -> boto3.Session:
        """ Get a boto3 session for S3 without s3v4 signature"""
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,  # region does not matter when using MinIO
        )

    @cached_property
    def s3v4(self) -> boto3.Session:
        """ Get a boto3 session for S3 with s3v4 signature"""
        return boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=None,
            config=boto3.session.Config(signature_version="s3v4"),
            verify=False,
        )
    
    @cached_property
    def sts(self) -> boto3.Session:
        """ Get a boto3 session for STS with s3v4 signature"""
        return boto3.client(
            "sts",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=None,
            config=boto3.session.Config(signature_version="s3v4"),
            verify=False,
        )
    
    @cached_property
    def file_system(self) -> S3FileSystem:
        return S3FileSystem(
            key=settings.AWS_ACCESS_KEY_ID,
            secret=settings.AWS_SECRET_ACCESS_KEY,
            client_kwargs={
                "endpoint_url": settings.AWS_S3_ENDPOINT_URL,
                "region_name": settings.AWS_S3_REGION_NAME,
            },
        )







def get_current_datalayer() -> Datalayer:
    try:
        return datalayer.get()
    except LookupError:
        raise ValueError("No datalayer set")
    


class DatalayerExtension(SchemaExtension):

    def on_operation(self) -> Generator[None, None, None]:
        t1 = datalayer.set(
            Datalayer()
        )
        
        yield
        datalayer.reset(t1)

        print("GraphQL operation end")
