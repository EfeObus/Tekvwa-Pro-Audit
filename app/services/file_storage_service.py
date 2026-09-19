"""
TekVwarho ProAudit - File Storage Service

File storage service for document management.

Supports:
- Google Cloud Storage (production, GCP)
- Azure Blob Storage (legacy production, kept for read compatibility during migration)
- Local file storage (development)

File Types:
- Receipts and invoices
- Supporting documents
- Tax certificates
- Audit reports
"""

import os
import uuid
import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from enum import Enum

from app.config import settings


class StorageProvider(str, Enum):
    """Storage provider types."""
    AZURE_BLOB = "azure"
    GCS = "gcs"
    LOCAL = "local"


class FileCategory(str, Enum):
    """File category types."""
    RECEIPT = "receipt"
    INVOICE = "invoice"
    TAX_CERTIFICATE = "tax_certificate"
    SUPPORTING_DOC = "supporting_doc"
    REPORT = "report"
    OTHER = "other"


class FileStorageService:
    """
    File storage service for document management.
    
    Uses Azure Blob Storage in production,
    falls back to local storage for development.
    """
    
    def __init__(self):
        self.azure_connection_string = getattr(settings, 'azure_storage_connection_string', None)
        self.azure_container = getattr(settings, 'azure_storage_container', 'documents')
        self.gcs_bucket_name = getattr(settings, 'gcs_bucket_name', None)
        self.gcs_project_id = getattr(settings, 'gcs_project_id', None)
        self.local_storage_path = Path("uploads")
        self.provider = self._determine_provider()

        # Ensure local storage directory exists
        if self.provider == StorageProvider.LOCAL:
            self.local_storage_path.mkdir(parents=True, exist_ok=True)

    def _determine_provider(self) -> StorageProvider:
        """Determine which storage provider to use."""
        if self.gcs_bucket_name:
            return StorageProvider.GCS
        if self.azure_connection_string:
            return StorageProvider.AZURE_BLOB
        return StorageProvider.LOCAL
    
    def _generate_blob_name(
        self,
        entity_id: uuid.UUID,
        category: FileCategory,
        original_filename: str,
    ) -> str:
        """
        Generate a unique blob name with organized path structure.
        
        Format: entity_id/category/year/month/unique_id_filename
        """
        now = datetime.utcnow()
        file_id = uuid.uuid4().hex[:12]
        
        # Sanitize filename
        safe_filename = "".join(
            c if c.isalnum() or c in ".-_" else "_"
            for c in original_filename
        )
        
        return f"{entity_id}/{category.value}/{now.year}/{now.month:02d}/{file_id}_{safe_filename}"
    
    async def upload_file(
        self,
        entity_id: uuid.UUID,
        file_content: bytes,
        filename: str,
        content_type: str,
        category: FileCategory = FileCategory.OTHER,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to storage.
        
        Args:
            entity_id: Business entity ID
            file_content: Raw file bytes
            filename: Original filename
            content_type: MIME type
            category: File category
            metadata: Additional metadata
            
        Returns:
            Dict with file_id, url, and metadata
        """
        blob_name = self._generate_blob_name(entity_id, category, filename)
        file_hash = hashlib.md5(file_content).hexdigest()
        file_size = len(file_content)
        
        if self.provider == StorageProvider.GCS:
            url = await self._upload_to_gcs(
                blob_name, file_content, content_type, metadata
            )
        elif self.provider == StorageProvider.AZURE_BLOB:
            url = await self._upload_to_azure(
                blob_name, file_content, content_type, metadata
            )
        else:
            url = await self._upload_to_local(
                blob_name, file_content, content_type
            )
        
        return {
            "file_id": blob_name,
            "url": url,
            "filename": filename,
            "content_type": content_type,
            "size": file_size,
            "hash": file_hash,
            "category": category.value,
            "provider": self.provider.value,
            "uploaded_at": datetime.utcnow().isoformat(),
        }
    
    async def _upload_to_azure(
        self,
        blob_name: str,
        file_content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload file to Azure Blob Storage."""
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
            
            blob_service = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            container_client = blob_service.get_container_client(self.azure_container)
            
            # Ensure container exists
            if not container_client.exists():
                container_client.create_container()
            
            blob_client = container_client.get_blob_client(blob_name)
            
            content_settings = ContentSettings(content_type=content_type)
            
            blob_client.upload_blob(
                file_content,
                content_settings=content_settings,
                metadata=metadata,
                overwrite=True,
            )
            
            return blob_client.url
            
        except ImportError:
            # Azure SDK not installed, fall back to local
            return await self._upload_to_local(blob_name, file_content, content_type)
        except Exception as e:
            print(f"Azure upload error: {e}")
            raise

    async def _upload_to_gcs(
        self,
        blob_name: str,
        file_content: bytes,
        content_type: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload file to Google Cloud Storage."""
        try:
            from google.cloud import storage as gcs_storage

            client = gcs_storage.Client(project=self.gcs_project_id)
            bucket = client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(blob_name)

            if metadata:
                blob.metadata = metadata

            blob.upload_from_string(file_content, content_type=content_type)

            return f"gs://{self.gcs_bucket_name}/{blob_name}"

        except ImportError:
            # google-cloud-storage not installed, fall back to local
            return await self._upload_to_local(blob_name, file_content, content_type)
        except Exception as e:
            print(f"GCS upload error: {e}")
            raise

    async def _upload_to_local(
        self,
        blob_name: str,
        file_content: bytes,
        content_type: str,
    ) -> str:
        """Upload file to local storage."""
        file_path = self.local_storage_path / blob_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(file_content)
        
        # Return local URL (for development)
        return f"/uploads/{blob_name}"
    
    async def download_file(
        self,
        file_id: str,
    ) -> Tuple[bytes, str]:
        """
        Download a file from storage.
        
        Args:
            file_id: The file ID (blob name)
            
        Returns:
            Tuple of (file_content, content_type)
        """
        if self.provider == StorageProvider.GCS:
            return await self._download_from_gcs(file_id)
        elif self.provider == StorageProvider.AZURE_BLOB:
            return await self._download_from_azure(file_id)
        else:
            return await self._download_from_local(file_id)
    
    async def _download_from_azure(
        self,
        blob_name: str,
    ) -> Tuple[bytes, str]:
        """Download file from Azure Blob Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
            
            blob_service = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            blob_client = blob_service.get_blob_client(
                container=self.azure_container,
                blob=blob_name,
            )
            
            download = blob_client.download_blob()
            content = download.readall()
            properties = blob_client.get_blob_properties()
            content_type = properties.content_settings.content_type
            
            return content, content_type
            
        except Exception as e:
            print(f"Azure download error: {e}")
            raise

    async def _download_from_gcs(
        self,
        blob_name: str,
    ) -> Tuple[bytes, str]:
        """Download file from Google Cloud Storage."""
        from google.cloud import storage as gcs_storage

        client = gcs_storage.Client(project=self.gcs_project_id)
        bucket = client.bucket(self.gcs_bucket_name)
        blob = bucket.blob(blob_name)

        if not blob.exists():
            raise FileNotFoundError(f"File not found: {blob_name}")

        content = blob.download_as_bytes()
        blob.reload()
        content_type = blob.content_type or "application/octet-stream"

        return content, content_type

    async def _download_from_local(
        self,
        blob_name: str,
    ) -> Tuple[bytes, str]:
        """Download file from local storage."""
        file_path = self.local_storage_path / blob_name
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {blob_name}")
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        # Guess content type from extension
        import mimetypes
        content_type, _ = mimetypes.guess_type(str(file_path))
        content_type = content_type or "application/octet-stream"
        
        return content, content_type
    
    async def delete_file(
        self,
        file_id: str,
    ) -> bool:
        """
        Delete a file from storage.
        
        Args:
            file_id: The file ID (blob name)
            
        Returns:
            True if deleted successfully
        """
        if self.provider == StorageProvider.GCS:
            return await self._delete_from_gcs(file_id)
        elif self.provider == StorageProvider.AZURE_BLOB:
            return await self._delete_from_azure(file_id)
        else:
            return await self._delete_from_local(file_id)
    
    async def _delete_from_azure(
        self,
        blob_name: str,
    ) -> bool:
        """Delete file from Azure Blob Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
            
            blob_service = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            blob_client = blob_service.get_blob_client(
                container=self.azure_container,
                blob=blob_name,
            )
            
            blob_client.delete_blob()
            return True
            
        except Exception as e:
            print(f"Azure delete error: {e}")
            return False

    async def _delete_from_gcs(
        self,
        blob_name: str,
    ) -> bool:
        """Delete file from Google Cloud Storage."""
        try:
            from google.cloud import storage as gcs_storage

            client = gcs_storage.Client(project=self.gcs_project_id)
            bucket = client.bucket(self.gcs_bucket_name)
            blob = bucket.blob(blob_name)
            blob.delete()
            return True

        except Exception as e:
            print(f"GCS delete error: {e}")
            return False

    async def _delete_from_local(
        self,
        blob_name: str,
    ) -> bool:
        """Delete file from local storage."""
        file_path = self.local_storage_path / blob_name
        
        if file_path.exists():
            file_path.unlink()
            return True
        
        return False
    
    async def list_files(
        self,
        entity_id: uuid.UUID,
        category: Optional[FileCategory] = None,
        prefix: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List files for an entity.
        
        Args:
            entity_id: Business entity ID
            category: Optional category filter
            prefix: Optional path prefix filter
            
        Returns:
            List of file metadata
        """
        search_prefix = f"{entity_id}/"
        if category:
            search_prefix += f"{category.value}/"
        if prefix:
            search_prefix += prefix
        
        if self.provider == StorageProvider.GCS:
            return await self._list_gcs_files(search_prefix)
        elif self.provider == StorageProvider.AZURE_BLOB:
            return await self._list_azure_files(search_prefix)
        else:
            return await self._list_local_files(search_prefix)
    
    async def _list_azure_files(
        self,
        prefix: str,
    ) -> List[Dict[str, Any]]:
        """List files in Azure Blob Storage."""
        try:
            from azure.storage.blob import BlobServiceClient
            
            blob_service = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            container_client = blob_service.get_container_client(self.azure_container)
            
            files = []
            for blob in container_client.list_blobs(name_starts_with=prefix):
                files.append({
                    "file_id": blob.name,
                    "url": f"{container_client.url}/{blob.name}",
                    "size": blob.size,
                    "created_at": blob.creation_time.isoformat() if blob.creation_time else None,
                    "content_type": blob.content_settings.content_type if blob.content_settings else None,
                })
            
            return files
            
        except Exception as e:
            print(f"Azure list error: {e}")
            return []

    async def _list_gcs_files(
        self,
        prefix: str,
    ) -> List[Dict[str, Any]]:
        """List files in Google Cloud Storage."""
        try:
            from google.cloud import storage as gcs_storage

            client = gcs_storage.Client(project=self.gcs_project_id)
            bucket = client.bucket(self.gcs_bucket_name)

            files = []
            for blob in client.list_blobs(bucket, prefix=prefix):
                files.append({
                    "file_id": blob.name,
                    "url": f"gs://{self.gcs_bucket_name}/{blob.name}",
                    "size": blob.size,
                    "created_at": blob.time_created.isoformat() if blob.time_created else None,
                    "content_type": blob.content_type,
                })

            return files

        except Exception as e:
            print(f"GCS list error: {e}")
            return []

    async def _list_local_files(
        self,
        prefix: str,
    ) -> List[Dict[str, Any]]:
        """List files in local storage."""
        search_path = self.local_storage_path / prefix
        
        if not search_path.exists():
            return []
        
        files = []
        for file_path in search_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.local_storage_path)
                stat = file_path.stat()
                
                import mimetypes
                content_type, _ = mimetypes.guess_type(str(file_path))
                
                files.append({
                    "file_id": str(rel_path),
                    "url": f"/uploads/{rel_path}",
                    "size": stat.st_size,
                    "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    "content_type": content_type,
                })
        
        return files
    
    def get_signed_url(
        self,
        file_id: str,
        expiry_hours: int = 1,
    ) -> Optional[str]:
        """
        Generate a signed URL for temporary access.
        
        Applicable for Azure Blob Storage and Google Cloud Storage.
        """
        if self.provider == StorageProvider.GCS:
            try:
                from google.cloud import storage as gcs_storage
                from datetime import timedelta

                client = gcs_storage.Client(project=self.gcs_project_id)
                bucket = client.bucket(self.gcs_bucket_name)
                blob = bucket.blob(file_id)

                return blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(hours=expiry_hours),
                    method="GET",
                )
            except Exception as e:
                print(f"GCS signed URL error: {e}")
                return None

        if self.provider != StorageProvider.AZURE_BLOB:
            return f"/uploads/{file_id}"

        try:
            from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
            from datetime import timedelta
            
            blob_service = BlobServiceClient.from_connection_string(
                self.azure_connection_string
            )
            
            # Parse account key from connection string
            account_name = None
            account_key = None
            for part in self.azure_connection_string.split(";"):
                if part.startswith("AccountName="):
                    account_name = part.split("=", 1)[1]
                elif part.startswith("AccountKey="):
                    account_key = part.split("=", 1)[1]
            
            if not account_name or not account_key:
                return None
            
            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=self.azure_container,
                blob_name=file_id,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
            )
            
            blob_client = blob_service.get_blob_client(
                container=self.azure_container,
                blob=file_id,
            )
            
            return f"{blob_client.url}?{sas_token}"
            
        except Exception as e:
            print(f"SAS generation error: {e}")
            return None
