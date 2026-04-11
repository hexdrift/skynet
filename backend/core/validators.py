"""Shared validation functions for the backend.

All validators raise domain ValidationError on failure, never HTTPException.
This allows services to use validation logic without coupling to HTTP layer.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .constants import MODULE_COT, MODULE_PREDICT, OPTIMIZER_GEPA, OPTIMIZER_MIPROV2
from .exceptions import ValidationError


def validate_job_name(name: str | None) -> None:
    """Validate job display name.
    
    Args:
        name: Job name to validate
        
    Raises:
        ValidationError: If name is invalid
    """
    if name is not None:
        if not isinstance(name, str):
            raise ValidationError("Job name must be a string", details={"field": "name"})
        if len(name.strip()) == 0:
            raise ValidationError("Job name cannot be empty", details={"field": "name"})
        if len(name) > 200:
            raise ValidationError("Job name cannot exceed 200 characters", details={"field": "name"})


def validate_optimizer_name(optimizer: str) -> None:
    """Validate optimizer name against allowed optimizers.
    
    Only MIPROv2 and GEPA are permitted.
    
    Args:
        optimizer: Optimizer name to validate
        
    Raises:
        ValidationError: If optimizer is not allowed
    """
    allowed = {OPTIMIZER_MIPROV2, OPTIMIZER_GEPA}
    if optimizer not in allowed:
        raise ValidationError(
            f"Optimizer '{optimizer}' not allowed. Must be one of: {', '.join(sorted(allowed))}",
            details={"field": "optimizer_name", "allowed": sorted(allowed)}
        )


def validate_module_name(module: str) -> None:
    """Validate module name against allowed modules.
    
    Only Predict and ChainOfThought are permitted.
    
    Args:
        module: Module name to validate
        
    Raises:
        ValidationError: If module is not allowed
    """
    allowed = {MODULE_PREDICT, MODULE_COT}
    if module not in allowed:
        raise ValidationError(
            f"Module '{module}' not allowed. Must be one of: {', '.join(sorted(allowed))}",
            details={"field": "module_name", "allowed": sorted(allowed)}
        )


def validate_dataset_file(file_path: str | Path) -> None:
    """Validate that a dataset file exists and is readable.
    
    Args:
        file_path: Path to dataset file
        
    Raises:
        ValidationError: If file doesn't exist or isn't readable
    """
    path = Path(file_path)
    if not path.exists():
        raise ValidationError(f"Dataset file not found: {file_path}", details={"field": "dataset"})
    if not path.is_file():
        raise ValidationError(f"Dataset path is not a file: {file_path}", details={"field": "dataset"})
    if not os.access(path, os.R_OK):
        raise ValidationError(f"Dataset file is not readable: {file_path}", details={"field": "dataset"})


def validate_model_config(config: dict[str, Any]) -> None:
    """Validate model configuration dictionary.
    
    Args:
        config: Model configuration to validate
        
    Raises:
        ValidationError: If configuration is invalid
    """
    if not isinstance(config, dict):
        raise ValidationError("Model config must be a dictionary", details={"field": "model_config"})
    
    if "name" not in config:
        raise ValidationError("Model config must include 'name' field", details={"field": "model_config.name"})
    
    if not isinstance(config["name"], str) or len(config["name"].strip()) == 0:
        raise ValidationError("Model name must be a non-empty string", details={"field": "model_config.name"})
    
    # Validate temperature if present
    if "temperature" in config:
        temp = config["temperature"]
        if not isinstance(temp, (int, float)):
            raise ValidationError("Temperature must be a number", details={"field": "model_config.temperature"})
        if not 0.0 <= temp <= 2.0:
            raise ValidationError(
                "Temperature must be between 0.0 and 2.0",
                details={"field": "model_config.temperature"}
            )
    
    # Validate max_tokens if present
    if "max_tokens" in config:
        max_tok = config["max_tokens"]
        if max_tok is not None:
            if not isinstance(max_tok, int) or max_tok < 1:
                raise ValidationError(
                    "max_tokens must be a positive integer",
                    details={"field": "model_config.max_tokens"}
                )
