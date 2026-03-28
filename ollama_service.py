"""Ollama service module for local LLM inference."""

import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class OllamaService:
    """Service for interacting with Ollama local LLM API."""

    def generate_image(self, prompt: str, model: str = "x/z-image-turbo", timeout: int | None = None) -> tuple[bool, Optional[bytes], Optional[str]]:
        """Generate an image using Ollama's image API.
        Args:
            prompt: The image prompt to send.
            model: The image model to use (default: x/z-image-turbo).
            timeout: Request timeout in seconds.
        Returns:
            Tuple of (success, image bytes or None, error message or None)
        """
        timeout = timeout if timeout is not None else self.timeout
        api_url = f"{self.base_url}/api/generate"
        try:
            response = requests.post(
                api_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "format": "png"
                },
                timeout=timeout
            )
            if response.status_code != 200:
                # Check for RAM error in response text
                if response.text and "requires" in response.text and "but only" in response.text and "are available" in response.text:
                    logger.error("Ollama image generation failed: Not enough RAM for model. Response: %s", response.text)
                    return False, None, "Not enough RAM for image model. See Ollama logs."
                return False, None, response.text
            return True, response.content, None
        except Exception as e:
            logger.warning(f"Ollama image generation failed: {e}")
            return False, None, str(e)
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral", timeout: int = 120):
        """Initialize Ollama service.
        
        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Model name to use (default: mistral)
            timeout: Request timeout in seconds for generation calls (default: 120)
        """
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
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
    
    def generate_text(self, prompt: str, timeout: int | None = None) -> tuple[bool, str]:
        """Generate text using Ollama.
        
        Args:
            prompt: Input prompt
            timeout: Request timeout in seconds (defaults to self.timeout)
        
        Returns:
            Tuple of (success, response_text)
        """
        timeout = timeout if timeout is not None else self.timeout
        try:
            response = requests.post(
                self.api_url,
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
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
    
    def generate_json(self, prompt: str, timeout: int | None = None) -> tuple[bool, Optional[dict]]:
        """Generate JSON response using Ollama.
        
        Args:
            prompt: Input prompt
            timeout: Request timeout in seconds (defaults to self.timeout)
        
        Returns:
            Tuple of (success, json_object or None)
        """
        timeout = timeout if timeout is not None else self.timeout
        success, response_text = self.generate_text(prompt, timeout)
        
        if not success:
            return False, None
        
        try:
            json_obj = json.loads(response_text)
            return True, json_obj
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Ollama response: %r", response_text)
            return False, None
