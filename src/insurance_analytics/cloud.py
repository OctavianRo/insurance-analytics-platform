"""Batch entry point: write a complete run under a unique S3 prefix, manifest last."""

import os
import tempfile
from pathlib import Path
from uuid import uuid4

from .demo import run


def main():
    import boto3

    bucket = os.environ["ARTIFACT_BUCKET"]
    prefix = f"runs/{uuid4()}"
    with tempfile.TemporaryDirectory() as directory:
        run(directory)
        files = sorted(Path(directory).iterdir(), key=lambda p: p.name == "manifest.json")
        s3 = boto3.client("s3")
        for path in files:
            s3.upload_file(
                str(path),
                bucket,
                f"{prefix}/{path.name}",
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
    print(f"Completed s3://{bucket}/{prefix}/manifest.json")


if __name__ == "__main__":
    main()
