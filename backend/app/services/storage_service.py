"""S3-compatible Storage service using boto3."""

from typing import BinaryIO, Optional
from pathlib import Path
from uuid import UUID
import mimetypes
from loguru import logger
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from app.core.config import settings


class StorageService:
    """Service for managing document storage using S3-compatible storage (boto3)."""

    def __init__(self):
        """Initialize S3 client with boto3."""
        # Configure boto3 for S3-compatible storage (Supabase Storage)
        self.s3_client = boto3.client(
            's3',
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            )
        )
        self.bucket_name = settings.S3_BUCKET
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create storage bucket if it doesn't exist."""
        try:
            # Try to check if bucket exists
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket '{self.bucket_name}' already exists")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Create bucket if it doesn't exist
                try:
                    self.s3_client.create_bucket(
                        Bucket=self.bucket_name,
                        CreateBucketConfiguration={
                            'LocationConstraint': settings.S3_REGION
                        } if settings.S3_REGION != 'us-east-1' else {}
                    )
                    logger.info(f"Created S3 bucket: {self.bucket_name}")
                except Exception as create_error:
                    logger.error(f"Error creating S3 bucket: {create_error}")
                    raise
            else:
                logger.warning(f"Error checking bucket: {e}")

    def upload_file(
        self,
        file: BinaryIO,
        filename: str,
        project_id: UUID,
        content_type: Optional[str] = None
    ) -> str:
        """
        Upload file to S3 storage.

        Args:
            file: File object to upload
            filename: Original filename
            project_id: Project UUID for organization
            content_type: MIME type of the file

        Returns:
            Storage path of uploaded file
        """
        try:
            # Generate storage path: projects/{project_id}/{filename}
            storage_path = f"projects/{str(project_id)}/{filename}"

            # Detect content type if not provided
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = "application/octet-stream"

            # Read file data
            file_data = file.read()

            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_path,
                Body=file_data,
                ContentType=content_type,
                Metadata={
                    'project_id': str(project_id),
                    'original_filename': filename
                }
            )

            logger.info(f"Uploaded file to S3 storage: {storage_path}")
            return storage_path

        except Exception as e:
            logger.error(f"Error uploading file to S3 storage: {e}")
            raise

    def download_file(self, storage_path: str) -> bytes:
        """
        Download file from S3 storage.

        Args:
            storage_path: Path to file in storage

        Returns:
            File content as bytes
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=storage_path
            )
            file_data = response['Body'].read()
            logger.info(f"Downloaded file from S3 storage: {storage_path}")
            return file_data

        except Exception as e:
            logger.error(f"Error downloading file from S3 storage: {e}")
            raise

    def get_public_url(self, storage_path: str) -> str:
        """
        Get public URL for a file (if bucket is public).

        Args:
            storage_path: Path to file in storage

        Returns:
            Public URL
        """
        try:
            # Construct public URL
            url = f"{settings.S3_ENDPOINT}/{self.bucket_name}/{storage_path}"
            return url

        except Exception as e:
            logger.error(f"Error getting public URL: {e}")
            raise

    def get_signed_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """
        Get signed URL for temporary file access.

        Args:
            storage_path: Path to file in storage
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Signed URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': storage_path
                },
                ExpiresIn=expires_in
            )
            return url

        except Exception as e:
            logger.error(f"Error creating signed URL: {e}")
            raise

    def delete_file(self, storage_path: str):
        """
        Delete file from S3 storage.

        Args:
            storage_path: Path to file in storage
        """
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=storage_path
            )
            logger.info(f"Deleted file from S3 storage: {storage_path}")

        except Exception as e:
            logger.error(f"Error deleting file from S3 storage: {e}")
            raise

    def delete_project_files(self, project_id: UUID):
        """
        Delete all files for a project.

        Args:
            project_id: Project UUID
        """
        try:
            # List all files in project folder
            project_path = f"projects/{str(project_id)}/"

            # List objects with prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=project_path
            )

            # Delete all files
            if 'Contents' in response:
                objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
                if objects_to_delete:
                    self.s3_client.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={'Objects': objects_to_delete}
                    )
                    logger.info(f"Deleted all files for project {project_id}")

        except Exception as e:
            logger.error(f"Error deleting project files: {e}")
            raise

    def list_project_files(self, project_id: UUID) -> list:
        """
        List all files for a project.

        Args:
            project_id: Project UUID

        Returns:
            List of file metadata
        """
        try:
            project_path = f"projects/{str(project_id)}/"

            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=project_path
            )

            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        'name': obj['Key'].split('/')[-1],
                        'key': obj['Key'],
                        'size': obj['Size'],
                        'last_modified': obj['LastModified'].isoformat(),
                        'etag': obj['ETag']
                    })

            return files

        except Exception as e:
            logger.error(f"Error listing project files: {e}")
            raise

    def get_file_info(self, storage_path: str) -> dict:
        """
        Get file metadata.

        Args:
            storage_path: Path to file in storage

        Returns:
            File metadata
        """
        try:
            response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=storage_path
            )

            return {
                'name': storage_path.split('/')[-1],
                'key': storage_path,
                'size': response['ContentLength'],
                'content_type': response.get('ContentType', 'application/octet-stream'),
                'last_modified': response['LastModified'].isoformat(),
                'etag': response['ETag'],
                'metadata': response.get('Metadata', {})
            }

        except Exception as e:
            logger.error(f"Error getting file info: {e}")
            raise


# Singleton instance
storage_service = StorageService()
