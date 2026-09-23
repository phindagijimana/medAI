"""
Med42 Model Service Module
Handles model loading, inference, and resource management
"""

import os
import time
import uuid
import logging
import traceback
from queue import Queue
from datetime import datetime
from typing import Dict, Any, Optional

# Optional imports - keep service alive even if missing
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    torch = None
    AutoTokenizer = AutoModelForCausalLM = None
    TRANSFORMERS_AVAILABLE = False

logger = logging.getLogger(__name__)


class Med42ModelService:
    """Med42 model loading and inference service"""

    def __init__(self, config):
        self.config = config
        self.model = None
        self.tokenizer = None
        # Auto-detect GPU, fallback to CPU
        if torch and torch.cuda.is_available():
            self.device = "cuda"
            logger.info(f"GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            self.device = "cpu"
            logger.info("No GPU detected, using CPU")
        self.model_name = config.model_name
        self.model_loaded = False
        self.load_error = None
        self.request_queue = Queue(maxsize=config.max_concurrent_users)
        self.stats = {
            "requests": 0,
            "successes": 0,
            "avg_time": 0,
            "model_load_time": None,
            "last_request": None
        }

    def load_model(self) -> bool:
        """Load the Med42 model with optimized settings"""
        if self.model_loaded:
            return True

        if not TRANSFORMERS_AVAILABLE:
            self.load_error = "PyTorch/Transformers not available"
            logger.error(self.load_error)
            return False

        try:
            start_time = time.time()
            logger.info(f"Loading Med42-8B model: {self.model_name}")
            logger.info(f"Device: {self.device}")
            logger.info(f"Cache directory: {self.config.model_cache_dir}")

            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                padding_side="left",
                cache_dir=self.config.model_cache_dir
            )

            if not self.tokenizer.pad_token:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            # Load model with optimized settings.
            # dtype: bf16 on CUDA (Med42-8B fits ~16 GB in bf16, needed for L40S 24 GB
            # slices); fp32 on CPU for numerical stability.
            model_dtype = torch.bfloat16 if (torch.cuda.is_available()) else torch.float32
            logger.info(f"Model dtype: {model_dtype}")
            model_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": model_dtype,
                "cache_dir": self.config.model_cache_dir,
                "low_cpu_mem_usage": True
            }

            # Force loading on CPU only to avoid device conflicts
            # model_kwargs["device_map"] = None

            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                **model_kwargs
            )

            # Ensure model is properly loaded on the specified device
            if self.device == "cuda" and torch.cuda.is_available():
                # Move model to CUDA and ensure ALL parameters and buffers are on CUDA
                self.model = self.model.cuda()
                # Force all parameters to be on CUDA
                for param in self.model.parameters():
                    param.data = param.data.cuda()
                # Also move buffers (like embeddings) to CUDA
                for buffer in self.model.buffers():
                    buffer.data = buffer.data.cuda()
                logger.info(f"Model fully loaded on CUDA: {next(self.model.parameters()).device}")
            else:
                self.model = self.model.cpu()
                logger.info(f"Model loaded on CPU: {next(self.model.parameters()).device}")

            self.model.eval()
            self.model_loaded = True

            load_time = time.time() - start_time
            self.stats["model_load_time"] = load_time

            logger.info(".2f")
            return True

        except Exception as e:
            self.load_error = str(e)
            logger.error(f"Med42 model loading failed: {e}")
            logger.error(traceback.format_exc())
            return False

    def analyze(self, prompt: str, text: str, analysis_type: str = "custom",
                user_id: Optional[str] = None, tabular_data: Optional[Dict] = None,
                specialty: Optional[str] = None, prompt_engine=None) -> Dict[str, Any]:
        """Perform Med42 analysis with optimized prompting"""

        if not self.model_loaded:
            raise RuntimeError(f"Med42 model not available: {self.load_error or 'not loaded'}")

        req_id = uuid.uuid4().hex[:8]
        t0 = time.time()

        try:
            # Queue management
            if self.request_queue.full():
                raise RuntimeError("Med42 service at capacity. Try again later.")
            self.request_queue.put(req_id, timeout=1)

            logger.info(f"[{req_id}] Med42 analysis started - Type: {analysis_type}, Text: {len(text)} chars")

            # Check tabular data
            is_tabular = tabular_data is not None and tabular_data.get("is_tabular", False)
            if is_tabular:
                logger.info(f"[{req_id}] Med42 tabular data analysis - Shape: {tabular_data['dataframe'].shape}")

            # Validate input
            if not text or not text.strip():
                raise ValueError("No text content provided for Med42 analysis")

            # Get optimized Med42 system prompt
            system_prompt = prompt_engine.get_med42_system_prompts(
                analysis_type,
                is_tabular=is_tabular,
                specialty=specialty
            )

            # Optimize text length
            max_text_chars = 4000
            if len(text) > max_text_chars:
                truncated = text[:max_text_chars]
                last_period = truncated.rfind('.')
                if last_period > max_text_chars * 0.8:
                    truncated = truncated[:last_period + 1]
                text = truncated + "\n\n[Note: Text truncated for Med42 processing]"
                logger.info(f"[{req_id}] Text truncated to {len(text)} characters")

            # Construct prompt
            final_prompt = prompt_engine.construct_med42_prompt(
                system_prompt=system_prompt,
                user_prompt=prompt,
                medical_data=text,
                is_tabular=is_tabular,
                analysis_type=analysis_type
            )

            logger.info(f"[{req_id}] Med42 prompt constructed - Total length: {len(final_prompt)} chars")

            # Tokenization
            max_model_context = 4096
            max_input_tokens = 3200

            toks = self.tokenizer(
                final_prompt,
                return_tensors="pt",
                truncation=True,
                max_length=max_input_tokens
            )

            input_token_count = toks["input_ids"].shape[1]
            logger.info(f"[{req_id}] Med42 tokenized - Input tokens: {input_token_count}, Device before move: {toks['input_ids'].device}")

            # Ensure all tensors are on the correct device
            if self.device == "cuda":
                for k, v in toks.items():
                    if hasattr(v, 'to'):
                        toks[k] = v.to(self.device)
                logger.info(f"[{req_id}] Tensors moved to device: {toks['input_ids'].device}")
                # Double-check all tensors are on the same device
                for k, v in toks.items():
                    if hasattr(v, 'device'):
                        logger.info(f"[{req_id}] {k} device: {v.device}")

            # Generate response
            logger.info(f"[{req_id}] Generating Med42 response...")
            logger.info(f"[{req_id}] Model device: {next(self.model.parameters()).device}")
            logger.info(f"[{req_id}] Input tensor device: {toks['input_ids'].device}")

            # Final device check - ensure all tensors match model device
            model_device = next(self.model.parameters()).device
            for k in toks:
                if toks[k].device != model_device:
                    logger.warning(f"[{req_id}] Moving {k} from {toks[k].device} to {model_device}")
                    toks[k] = toks[k].to(model_device)

            with torch.no_grad():
                outputs = self.model.generate(
                    toks["input_ids"],
                    attention_mask=toks.get("attention_mask"),
                    max_new_tokens=512,
                    min_new_tokens=30,
                    temperature=0.3,
                    top_p=0.85,
                    do_sample=True,
                    repetition_penalty=1.05,
                    pad_token_id=self.tokenizer.eos_token_id,
                    eos_token_id=self.tokenizer.eos_token_id,
                    early_stopping=True
                )

            generated_text = self.tokenizer.decode(
                outputs[0][input_token_count:],
                skip_special_tokens=True
            ).strip()

            dt = time.time() - t0
            tokens_generated = outputs.shape[1] - input_token_count

            logger.info(f"[{req_id}] Med42 response generated: {tokens_generated} tokens in {dt:.2f}s")

            # Process tabular output if applicable
            tabular_output = None
            if is_tabular and tabular_data.get("dataframe") is not None:
                try:
                    from .file_processor import generate_tabular_output
                    result_with_analysis = {"analysis": generated_text}
                    tabular_output = generate_tabular_output(
                        result_with_analysis,
                        tabular_data["dataframe"],
                        analysis_type
                    )
                    logger.info(f"[{req_id}] Med42 tabular output generated with shape: {tabular_output.shape}")
                except Exception as e:
                    logger.error(f"[{req_id}] Med42 tabular output generation failed: {e}")

            # Validation notes
            validation_notes = ""
            if tokens_generated < 30:
                validation_notes = "Med42 validation: Very short response - consider more specific medical context"

            # Update stats
            self._update_stats(dt, True)

            # Clear GPU cache
            if self.device == "cuda":
                torch.cuda.empty_cache()

            result = {
                "request_id": req_id,
                "analysis": generated_text,
                "execution_time": dt,
                "tokens_generated": int(tokens_generated),
                "input_tokens": input_token_count,
                "text_length_original": len(text),
                "model_used": f"{self.model_name}-Optimized",
                "prompt_version": "Med42-8B-Enhanced",
                "timestamp": datetime.now().isoformat(),
                "is_tabular": is_tabular,
                "validation_notes": validation_notes
            }

            if tabular_output is not None:
                result["tabular_output"] = {
                    "csv": tabular_output.to_csv(index=False),
                    "html": tabular_output.to_html(index=False, table_id="results-table", classes="table table-striped"),
                    "json": tabular_output.to_json(orient="records"),
                    "shape": tabular_output.shape,
                    "columns": list(tabular_output.columns)
                }

            return result

        except Exception as e:
            dt = time.time() - t0
            self._update_stats(dt, False)
            logger.error(f"[{req_id}] Med42 analysis failed: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            try:
                self.request_queue.get_nowait()
            except Exception:
                pass

    def _update_stats(self, dt: float, success: bool):
        """Update service statistics"""
        self.stats["requests"] += 1
        self.stats["last_request"] = datetime.now().isoformat()
        if success:
            self.stats["successes"] += 1
        # Running average
        n = self.stats["requests"]
        self.stats["avg_time"] = ((n-1) * self.stats["avg_time"] + dt) / n

    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        gpu_info = {}
        if TRANSFORMERS_AVAILABLE and torch and torch.cuda.is_available():
            try:
                gpu_info = {
                    "gpu_count": torch.cuda.device_count(),
                    "current_device": torch.cuda.current_device(),
                    "gpu_name": torch.cuda.get_device_name(0),
                    "gpu_memory_total_GB": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2)
                }
            except Exception:
                gpu_info = {"error": "unavailable"}

        return {
            "model_loaded": self.model_loaded,
            "load_error": self.load_error,
            "device": self.device,
            "gpu_available": bool(torch and torch.cuda.is_available()) if TRANSFORMERS_AVAILABLE else False,
            "gpu_info": gpu_info,
            "queue_size": self.request_queue.qsize(),
            "max_queue_size": self.request_queue.maxsize,
            "stats": self.stats,
            "dependencies": {
                "torch": TRANSFORMERS_AVAILABLE,
                "transformers": TRANSFORMERS_AVAILABLE
            }
        }

    def unload_model(self):
        """Unload model to free memory"""
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        self.model_loaded = False

        if TRANSFORMERS_AVAILABLE and torch and self.device == "cuda":
            torch.cuda.empty_cache()

        logger.info("Med42 model unloaded")


