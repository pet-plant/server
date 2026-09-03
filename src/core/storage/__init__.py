"""Object storage (MinIO / S3) — shared client and bucket helpers.

Other contexts obtain the client either by direct import::

    from core.storage import get_minio_client

    get_minio_client().put_object(bucket, key, data, length)

or via FastAPI dependency injection in their own ``api.py``::

    from core.storage import ObjectStorage

    @router.post("/captures")
    def upload(storage: ObjectStorage) -> ...:
        storage.put_object(...)

Bucket names are configured on :class:`core.config.Settings` (``minio_bucket_*``)
and surfaced through :func:`bucket_names`.
"""

from core.storage.client import (
    ObjectStorage,
    bucket_names,
    ensure_bucket,
    get_minio_client,
    get_object_storage,
)

__all__ = [
    "ObjectStorage",
    "bucket_names",
    "ensure_bucket",
    "get_minio_client",
    "get_object_storage",
]
