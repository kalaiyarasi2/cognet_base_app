"""
core_gpu.py - Centralized GPU Engine, Model Singleton & Hardware Audit Logger

Features:
  1. Universal Hardware Detection:
     - Automatically probes PyTorch CUDA and PaddlePaddle CUDA.
     - Gracefully identifies CPU / Intel integrated graphics.
  2. Singleton Warm Model Cache:
     - Keeps OCR models (PaddleOCR, DocTR) warm in memory to avoid repeated cold-start loads.
  3. Crash-Safe VRAM Guard:
     - Thread-safe Semaphore to limit concurrent GPU executions.
     - Automatic CUDA memory cleanup.
  4. Standardized Audit Logger:
     - Emits consistent [OCR AUDIT] messages across all modules.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("GPU_ENGINE")


class GPUEngine:
    """Singleton GPU Management & Warm Model Runtime."""

    _instance: Optional["GPUEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "GPUEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GPUEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._initialized = True
        self.device = "cpu"
        self.device_name = "CPU"
        self.total_vram_gb = 0.0
        self.has_cuda = False
        self.torch_available = False
        self.paddle_cuda_available = False

        # VRAM / Concurrency lock
        self._execution_lock = threading.Semaphore(4)

        # Model singletons
        self._paddle_ocr_models: Dict[str, Any] = {}
        self._doctr_model = None

        self._probe_hardware()

    def _probe_hardware(self) -> None:
        """Inspects physical and driver hardware capabilities."""
        # 1. PyTorch CUDA inspection
        try:
            import torch
            self.torch_available = True
            if torch.cuda.is_available():
                self.has_cuda = True
                self.device = "cuda"
                self.device_name = torch.cuda.get_device_name(0)
                props = torch.cuda.get_device_properties(0)
                self.total_vram_gb = round(props.total_memory / (1024 ** 3), 2)
            else:
                self._detect_cpu_brand()
        except Exception:
            self._detect_cpu_brand()

        # 2. PaddlePaddle CUDA inspection
        try:
            import paddle
            self.paddle_cuda_available = bool(
                hasattr(paddle, "is_compiled_with_cuda") and paddle.is_compiled_with_cuda()
            )
            # Paddle GPU build + visible device => enable GPU even if torch is CPU-only
            if (
                not self.has_cuda
                and self.paddle_cuda_available
                and paddle.device.cuda.device_count() > 0
            ):
                self.has_cuda = True
                self.device = "cuda"
                try:
                    self.device_name = paddle.device.cuda.get_device_name(0)
                except Exception:
                    self.device_name = "NVIDIA GPU (Paddle)"
        except Exception:
            self.paddle_cuda_available = False

        if self.has_cuda:
            logger.info(
                "[GPU ENGINE] Dedicated GPU Active: %s (%.2f GB VRAM)",
                self.device_name,
                self.total_vram_gb,
            )
        else:
            logger.info(
                "[GPU ENGINE] Running in Optimized CPU Mode: %s (CUDA unavailable)",
                self.device_name,
            )

    def _detect_cpu_brand(self) -> None:
        """Finds integrated GPU / CPU name on Windows for clear audit reporting."""
        self.device = "cpu"
        self.has_cuda = False
        # Try to identify Intel Iris / CPU processor name
        try:
            if sys.platform == "win32":
                import subprocess
                cmd = "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
                res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=3)
                names = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                if names:
                    self.device_name = f"CPU / {names[0]}"
                    return
        except Exception:
            pass
        self.device_name = "CPU"

    def is_cuda_available(self) -> bool:
        """Returns True if NVIDIA CUDA acceleration is active."""
        return self.has_cuda

    def get_device_string(self) -> str:
        """Human-readable device summary for logs."""
        if self.has_cuda:
            return f"GPU ({self.device_name})"
        return f"CPU ({self.device_name} / No CUDA)"

    def get_vram_usage_mb(self) -> float:
        """Returns currently allocated CUDA VRAM in MB, or 0.0 on CPU."""
        if self.has_cuda:
            try:
                import torch
                return round(torch.cuda.memory_allocated(0) / (1024 ** 2), 1)
            except Exception:
                pass
        return 0.0

    def empty_cache(self) -> None:
        """Frees unused cached VRAM memory."""
        if self.has_cuda:
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass

    def log_ocr_audit(
        self,
        module_name: str,
        engine_name: str,
        page_idx: Optional[int] = None,
        total_pages: Optional[int] = None,
        elapsed_sec: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Emits a standardized [OCR AUDIT] log message."""
        parts = [f"[OCR AUDIT] Module: {module_name}"]

        if page_idx is not None:
            if total_pages is not None:
                parts.append(f"Page: {page_idx}/{total_pages}")
            else:
                parts.append(f"Page: {page_idx}")

        parts.append(f"Engine: {engine_name}")
        parts.append(f"Device: {self.get_device_string()}")

        if self.has_cuda:
            vram_mb = self.get_vram_usage_mb()
            parts.append(f"VRAM: {vram_mb:.0f}MB")

        if elapsed_sec is not None:
            parts.append(f"Time: {elapsed_sec:.2f}s")

        if notes:
            parts.append(f"Note: {notes}")

        msg = " | ".join(parts)
        logger.info(msg)
        # Also print to stdout so terminal output always captures it directly
        print(msg, flush=True)

    def get_paddle_ocr(
        self,
        lang: str = "en",
        use_angle_cls: bool = True,
        **extra_kwargs: Any,
    ) -> Any:
        """
        Returns a warm, singleton PaddleOCR instance.
        Loads once into memory and reuses across calls.
        """
        cache_key = f"{lang}_{use_angle_cls}"
        if cache_key not in self._paddle_ocr_models:
            from paddleocr import PaddleOCR
            use_gpu = self.has_cuda and self.paddle_cuda_available
            logger.info(
                "[GPU ENGINE] Initializing Warm PaddleOCR (lang='%s', use_gpu=%s)...",
                lang,
                use_gpu,
            )
            kwargs = {
                "lang": lang,
                "use_angle_cls": use_angle_cls,
                "use_gpu": use_gpu,
                **extra_kwargs,
            }
            try:
                self._paddle_ocr_models[cache_key] = PaddleOCR(**kwargs)
            except TypeError:
                # Some newer versions of paddleocr deprecate use_gpu in kwargs
                kwargs.pop("use_gpu", None)
                self._paddle_ocr_models[cache_key] = PaddleOCR(**kwargs)

        return self._paddle_ocr_models[cache_key]

    def get_doctr_model(
        self,
        det_arch: str = "db_resnet50",
        reco_arch: str = "crnn_vgg16_bn",
        pretrained: bool = True,
    ) -> Any:
        """Returns a warm DocTR predictor model loaded on the active device."""
        if self._doctr_model is None:
            from doctr.models import ocr_predictor
            import torch

            device = torch.device("cuda" if self.has_cuda else "cpu")
            logger.info("[GPU ENGINE] Initializing Warm DocTR on %s...", device)
            model = ocr_predictor(
                det_arch=det_arch,
                reco_arch=reco_arch,
                pretrained=pretrained,
            )
            model = model.to(device)
            self._doctr_model = model
        return self._doctr_model


# Global singleton instance
gpu_engine = GPUEngine()


# Helper shortcuts
def get_gpu_engine() -> GPUEngine:
    return gpu_engine


def log_ocr_audit(
    module_name: str,
    engine_name: str,
    page_idx: Optional[int] = None,
    total_pages: Optional[int] = None,
    elapsed_sec: Optional[float] = None,
    notes: Optional[str] = None,
) -> None:
    gpu_engine.log_ocr_audit(
        module_name=module_name,
        engine_name=engine_name,
        page_idx=page_idx,
        total_pages=total_pages,
        elapsed_sec=elapsed_sec,
        notes=notes,
    )


def get_hardware_device_string() -> str:
    return gpu_engine.get_device_string()
