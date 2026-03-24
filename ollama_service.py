"""Ollama service module for local LLM inference."""

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for interacting with Ollama local LLM API."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        """Initialize Ollama service.
        
        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Model name to use (default: mistral)
        """
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/api/chat"
        self.tags_url = f"{base_url}/api/tags"
    
    def is_running(self) -> bool:
        """Check if Ollama service is running."""
        try:
            response = requests.get(self.tags_url, timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def get_models(self) -> list[str]:
        """Get list of available models."""
        try:
            response = requests.get(self.tags_url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                return models
            return []
        except requests.exceptions.RequestException:
            return []
    
    def model_exists(self) -> bool:
        """Check if configured model is available."""
        models = self.get_models()
        return self.model in models or any(self.model in model for model in models)
    
    def generate_text(self, prompt: str, timeout: int = 60) -> tuple[bool, str]:
        """Generate text using Ollama.
        
        Args:
            prompt: Input prompt
            timeout: Request timeout in seconds
        
        Returns:
            Tuple of (success, response_text)
        """
        if not self.is_running():
            return False, "Ollama service is not running. Start with: ollama serve"
        
        if not self.model_exists():
            return False, f"Model '{self.model}' not found. Pull with: ollama pull {self.model}"
        
        try:
            response = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=timeout
            )
            
            if response.status_code != 200:
                return False, f"Ollama API error: {response.status_code}"
            
            response_data = response.json()
            response_text = response_data.get("message", {}).get("content", "")
            return True, response_text
        
        except requests.exceptions.Timeout:
            return False, "Request timeout. Model may be slow or busy."
        except requests.exceptions.ConnectionError:
            return False, "Connection refused. Is Ollama running?"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def generate_json(self, prompt: str, timeout: int = 60) -> tuple[bool, Optional[dict]]:
        """Generate JSON response using Ollama.
        
        Args:
            prompt: Input prompt
            timeout: Request timeout in seconds
        
        Returns:
            Tuple of (success, json_object or None)
        """
        success, response_text = self.generate_text(prompt, timeout)
        
        if not success:
            return False, None
        
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                json_obj = json.loads(json_str)
                return True, json_obj
            else:
                json_obj = json.loads(response_text)
                return True, json_obj
        except json.JSONDecodeError:
            return False, None
