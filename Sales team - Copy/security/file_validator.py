import os
import hashlib
import mimetypes
from typing import Dict, Any, Tuple, Optional

# Default allowed extensions for CogNet document processing
DEFAULT_ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".txt", ".msg", ".eml", ".json", ".xml"
}

# Maximum file size allowed by default (50 MB)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024

class FileValidator:
    """
    Validates uploaded files for size, extension, MIME type, structural basic checks,
    and generates SHA-256 checksums for audit tracking and duplicate detection.
    """
    
    def __init__(self, allowed_extensions: Optional[set] = None, max_size_bytes: int = MAX_FILE_SIZE_BYTES):
        self.allowed_extensions = allowed_extensions if allowed_extensions is not None else DEFAULT_ALLOWED_EXTENSIONS
        self.max_size_bytes = max_size_bytes

    def calculate_sha256(self, file_content: bytes) -> str:
        """Generate SHA-256 hash string for file content bytes."""
        hasher = hashlib.sha256()
        hasher.update(file_content)
        return hasher.hexdigest()

    def calculate_sha256_from_path(self, file_path: str) -> str:
        """Generate SHA-256 hash string from a file path on disk."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def validate_file(self, filename: str, file_content: bytes) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate file extension, size, MIME type, and generate metadata.
        
        Returns:
            Tuple[is_valid (bool), error_message (str), metadata (dict)]
        """
        file_size = len(file_content)
        sha256_hash = self.calculate_sha256(file_content)
        ext = os.path.splitext(filename)[1].lower()
        
        mime_type, _ = mimetypes.guess_type(filename)
        mime_type = mime_type or "application/octet-stream"

        metadata = {
            "filename": filename,
            "extension": ext,
            "size_bytes": file_size,
            "mime_type": mime_type,
            "sha256": sha256_hash
        }

        # 1. Empty file check
        if file_size == 0:
            return False, "File is empty (0 bytes).", metadata

        # 2. File size limit check
        if file_size > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            return False, f"File size ({actual_mb:.2f} MB) exceeds maximum allowed limit ({max_mb:.2f} MB).", metadata

        # 3. Extension check
        if ext not in self.allowed_extensions:
            return False, f"File extension '{ext}' is not permitted for document processing.", metadata

        # Basic validation succeeded
        return True, "File validation successful.", metadata
