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

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

        # 2. PaddlePaddle CUDA inspection (safe probe to prevent pybind11 type collision with PyTorch)
        try:
            if "torch" in sys.modules:
                try:
                    import importlib.metadata
                    installed = {d.metadata["Name"].lower() for d in importlib.metadata.distributions()}
                    self.paddle_cuda_available = "paddlepaddle-gpu" in installed
                except Exception:
                    self.paddle_cuda_available = self.has_cuda
            else:
                import paddle
                self.paddle_cuda_available = bool(
                    hasattr(paddle, "is_compiled_with_cuda") and paddle.is_compiled_with_cuda()
                )
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
        Returns a crash-safe SafePaddleOCREngine instance.
        Delegates to shared GPU worker pool (GPU) or isolated subprocess,
        preventing pybind11 symbol collisions with PyTorch on Windows.
        """
        cache_key = f"{lang}_{use_angle_cls}"
        if cache_key not in self._paddle_ocr_models:
            use_gpu = self.has_cuda and self.paddle_cuda_available
            logger.info(
                "[GPU ENGINE] Initializing Safe PaddleOCR Engine (lang='%s', use_gpu=%s)...",
                lang,
                use_gpu,
            )
            self._paddle_ocr_models[cache_key] = SafePaddleOCREngine(
                lang=lang,
                use_angle_cls=use_angle_cls,
                use_gpu=use_gpu,
                **extra_kwargs,
            )

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


class SafePaddleOCREngine:
    """
    Crash-safe, cross-process PaddleOCR engine wrapper.
    On Windows, when PyTorch is loaded, direct in-process imports of PaddleOCR fail due to
    pybind11 _gpuDeviceProperties symbol clashes. This wrapper delegates inference to the
    shared persistent GPU worker pool (Gpu_server/GPU) or an isolated subprocess worker.
    """

    def __init__(
        self,
        lang: str = "en",
        use_angle_cls: bool = True,
        use_gpu: bool = True,
        **extra_kwargs: Any,
    ) -> None:
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self.use_gpu = use_gpu
        self.extra_kwargs = extra_kwargs
        self._in_process_engine = None

        # Only attempt in-process PaddleOCR if PyTorch has not been loaded in this process
        if "torch" not in sys.modules:
            try:
                from paddleocr import PaddleOCR
                kwargs = {
                    "lang": lang,
                    "use_angle_cls": use_angle_cls,
                    "use_gpu": use_gpu,
                    **extra_kwargs,
                }
                try:
                    self._in_process_engine = PaddleOCR(**kwargs)
                except TypeError:
                    kwargs.pop("use_gpu", None)
                    self._in_process_engine = PaddleOCR(**kwargs)
            except Exception as e:
                logger.debug("In-process PaddleOCR init bypassed: %s", e)
                self._in_process_engine = None

    def ocr(self, img: Any, det: bool = True, rec: bool = True, cls: bool = True) -> List[Any]:
        """
        Runs OCR on a single image (numpy array, PIL Image, or file path).
        Returns raw PaddleOCR result structure: [ [ [box, (text, conf)], ... ] ]
        """
        if self._in_process_engine is not None:
            return self._in_process_engine.ocr(img, det=det, rec=rec, cls=cls)

        temp_file = None
        if isinstance(img, (str, Path)):
            img_path = str(img)
        elif hasattr(img, "__array__"):
            from PIL import Image
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                temp_file = tf.name
            Image.fromarray(img).save(temp_file)
            img_path = temp_file
        elif hasattr(img, "save"):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                temp_file = tf.name
            img.save(temp_file)
            img_path = temp_file
        else:
            raise ValueError(f"Unsupported image type for PaddleOCR: {type(img)}")

        try:
            # 1. Try shared persistent GPU pool first
            if self.use_gpu:
                try:
                    gpu_server_dir = str(Path(__file__).resolve().parent / "Gpu_server")
                    if gpu_server_dir not in sys.path:
                        sys.path.insert(0, gpu_server_dir)
                    import GPU
                    if GPU.gpu_ocr_available():
                        profile = {
                            "kind": "basic",
                            "cls": cls,
                            "kwargs": {
                                "use_angle_cls": self.use_angle_cls,
                                "lang": self.lang,
                                **self.extra_kwargs,
                            },
                        }
                        raw_results = GPU.ocr_images_parallel([img_path], profile)
                        if raw_results and raw_results[0] is not None:
                            return raw_results[0]
                except Exception as exc:
                    logger.warning("[GPU ENGINE] Shared GPU pool OCR fallback: %s", exc)

            # 2. Fallback: isolated subprocess worker
            return self._run_isolated_subprocess(img_path, cls=cls)

        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    def ocr_batch(self, images: List[Any], cls: bool = True) -> List[Any]:
        """
        Runs OCR on a list of images in parallel across available GPU workers.
        Returns a list of raw PaddleOCR outputs, one per image.
        """
        if not images:
            return []

        temp_files: List[Optional[str]] = []
        img_paths: List[str] = []

        try:
            for img in images:
                if isinstance(img, (str, Path)):
                    img_paths.append(str(img))
                    temp_files.append(None)
                elif hasattr(img, "__array__"):
                    from PIL import Image
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                        t_name = tf.name
                    Image.fromarray(img).save(t_name)
                    img_paths.append(t_name)
                    temp_files.append(t_name)
                elif hasattr(img, "save"):
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                        t_name = tf.name
                    img.save(t_name)
                    img_paths.append(t_name)
                    temp_files.append(t_name)
                else:
                    raise ValueError(f"Unsupported image type: {type(img)}")

            if self.use_gpu:
                try:
                    gpu_server_dir = str(Path(__file__).resolve().parent / "Gpu_server")
                    if gpu_server_dir not in sys.path:
                        sys.path.insert(0, gpu_server_dir)
                    import GPU
                    if GPU.gpu_ocr_available():
                        profile = {
                            "kind": "basic",
                            "cls": cls,
                            "kwargs": {
                                "use_angle_cls": self.use_angle_cls,
                                "lang": self.lang,
                                **self.extra_kwargs,
                            },
                        }
                        raw_results = GPU.ocr_images_parallel(img_paths, profile)
                        if raw_results and len(raw_results) == len(images):
                            return raw_results
                except Exception as exc:
                    logger.warning("[GPU ENGINE] Shared GPU pool batch fallback: %s", exc)

            # Fallback: sequential single-image OCR
            return [self.ocr(p, cls=cls) for p in img_paths]

        finally:
            for tf in temp_files:
                if tf and os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except Exception:
                        pass

    def _run_isolated_subprocess(self, img_path: str, cls: bool = True) -> List[Any]:
        """Runs PaddleOCR inside an isolated child process to avoid DLL/pybind11 collisions."""
        worker_script = Path(__file__).resolve()
        cmd = [
            sys.executable,
            str(worker_script),
            "--paddle-ocr-worker",
            img_path,
            self.lang,
            str(self.use_angle_cls),
            str(self.use_gpu),
            str(cls),
        ]
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        if res.returncode != 0:
            err = res.stderr.strip() or f"exit code {res.returncode}"
            logger.error("[PaddleOCR Subprocess] Failed: %s", err)
            raise RuntimeError(f"PaddleOCR subprocess error: {err}")

        stdout = res.stdout.strip()
        start_tag = "__PADDLE_JSON_START__"
        end_tag = "__PADDLE_JSON_END__"
        if start_tag in stdout and end_tag in stdout:
            json_str = stdout.split(start_tag)[1].split(end_tag)[0].strip()
            return json.loads(json_str)

        raise RuntimeError(f"PaddleOCR subprocess returned invalid output: {stdout[:200]}")


def _paddle_ocr_worker_main() -> None:
    """CLI worker entrypoint for isolated PaddleOCR inference."""
    if len(sys.argv) < 7 or sys.argv[1] != "--paddle-ocr-worker":
        return

    img_path = sys.argv[2]
    lang = sys.argv[3]
    use_angle_cls = sys.argv[4].lower() == "true"
    use_gpu = sys.argv[5].lower() == "true"
    cls_flag = sys.argv[6].lower() == "true"

    try:
        import numpy as np
        from PIL import Image
        from paddleocr import PaddleOCR

        im = Image.open(img_path).convert("RGB")
        img_arr = np.array(im)

        ocr = PaddleOCR(
            lang=lang,
            use_angle_cls=use_angle_cls,
            use_gpu=use_gpu,
            show_log=False,
        )
        raw = ocr.ocr(img_arr, cls=cls_flag)

        def _to_json_safe(o):
            if isinstance(o, np.ndarray):
                return o.tolist()
            if isinstance(o, (np.floating, float)):
                return float(o)
            if isinstance(o, (np.integer, int)):
                return int(o)
            if isinstance(o, (list, tuple)):
                return [_to_json_safe(x) for x in o]
            if isinstance(o, dict):
                return {k: _to_json_safe(v) for k, v in o.items()}
            return o

        safe_raw = _to_json_safe(raw)
        print("__PADDLE_JSON_START__" + json.dumps(safe_raw) + "__PADDLE_JSON_END__")
        sys.exit(0)
    except Exception as e:
        sys.stderr.write(f"Worker error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--paddle-ocr-worker":
        _paddle_ocr_worker_main()

