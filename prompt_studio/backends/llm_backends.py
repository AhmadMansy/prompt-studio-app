"""
LLM Backend connectors for Prompt Studio
"""
import asyncio
import json
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional, Dict, Any
import httpx
import keyring
from datetime import datetime
import time


class LLMBackend(ABC):
    """Abstract base class for LLM backends"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name"""
        pass
    
    @abstractmethod
    async def list_models(self) -> List[str]:
        """List available models"""
        pass
    
    @abstractmethod
    async def complete(
        self, 
        *,
        system: Optional[str] = None,
        prompt: str,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> AsyncIterator[str]:
        """Complete a prompt and return response"""
        pass


class OpenAIBackend(LLMBackend):
    """OpenAI-compatible backend (works with OpenAI, Azure OpenAI, etc.)"""
    
    def __init__(
        self, 
        base_url: str = "https://api.openai.com/v1",
        api_key: Optional[str] = None,
        default_model: str = "gpt-4o-mini",
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key or self._get_api_key()
        self.default_model = default_model
        self.timeout = timeout
        self._client = None
    
    @property
    def name(self) -> str:
        return "openai"
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from keyring or environment"""
        try:
            return keyring.get_password("PromptStudio", "openai_api_key")
        except Exception:
            return None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with proper headers"""
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        return httpx.AsyncClient(
            headers=headers,
            timeout=self.timeout,
            base_url=self.base_url
        )
    
    async def list_models(self) -> List[str]:
        """List available models"""
        client = None
        try:
            client = self._get_client()
            response = await client.get("/models")
            response.raise_for_status()
            
            data = response.json()
            models = [model["id"] for model in data.get("data", [])]
            return sorted(models)
        except Exception as e:
            print(f"Error listing OpenAI models: {e}")
            return [self.default_model]
        finally:
            if client:
                await client.aclose()
    
    async def complete(
        self,
        *,
        system: Optional[str] = None,
        prompt: str,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> AsyncIterator[str]:
        """Complete a prompt using OpenAI API"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        
        client = self._get_client()
        
        try:
            if stream:
                async with client.stream(
                    "POST", "/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                content = chunk["choices"][0]["delta"].get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, KeyError):
                                continue
            else:
                response = await client.post("/chat/completions", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                yield content
                
        except Exception as e:
            yield f"Error: {str(e)}"


class OllamaBackend(LLMBackend):
    """Ollama backend for local LLMs"""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:11434",
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client = None
    
    @property
    def name(self) -> str:
        return "ollama"
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client"""
        return httpx.AsyncClient(
            timeout=self.timeout,
            base_url=self.base_url
        )
    
    async def list_models(self) -> List[str]:
        """List available Ollama models"""
        client = None
        try:
            client = self._get_client()
            response = await client.get("/api/tags")
            response.raise_for_status()
            
            data = response.json()
            models = [model["name"] for model in data.get("models", [])]
            return sorted(models)
        except Exception as e:
            print(f"Error listing Ollama models: {e}")
            return []
        finally:
            if client:
                await client.aclose()
    
    async def complete(
        self,
        *,
        system: Optional[str] = None,
        prompt: str,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> AsyncIterator[str]:
        """Complete a prompt using Ollama API"""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream
        }
        
        if system:
            payload["system"] = system
        if temperature is not None:
            payload["options"] = payload.get("options", {})
            payload["options"]["temperature"] = temperature
        if max_tokens is not None:
            payload["options"] = payload.get("options", {})
            payload["options"]["num_predict"] = max_tokens
        
        client = self._get_client()
        
        try:
            if stream:
                async with client.stream(
                    "POST", "/api/generate", json=payload
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        try:
                            chunk = json.loads(line)
                            content = chunk.get("response", "")
                            if content:
                                yield content
                            if chunk.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
            else:
                response = await client.post("/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                content = data.get("response", "")
                yield content
                
        except Exception as e:
            yield f"Error: {str(e)}"


class LMStudioBackend(OpenAIBackend):
    """LM Studio backend (OpenAI-compatible)"""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:1234/v1",
        timeout: int = 60
    ):
        super().__init__(
            base_url=base_url,
            api_key="lm-studio",  # LM Studio uses dummy key
            timeout=timeout
        )
    
    @property
    def name(self) -> str:
        return "lmstudio"
    
    def _get_api_key(self) -> str:
        """LM Studio uses dummy API key"""
        return "lm-studio"


class CustomHTTPBackend(LLMBackend):
    """Custom HTTP backend with user-defined payload template"""
    
    def __init__(
        self,
        base_url: str,
        payload_template: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 60
    ):
        self.base_url = base_url
        self.payload_template = payload_template
        self.headers = headers or {}
        self.timeout = timeout
        self._client = None
    
    @property
    def name(self) -> str:
        return "custom"
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client"""
        if not self._client:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=self.timeout
            )
        return self._client
    
    async def list_models(self) -> List[str]:
        """Custom backends don't have model listing"""
        return ["default"]
    
    async def complete(
        self,
        *,
        system: Optional[str] = None,
        prompt: str,
        model: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> AsyncIterator[str]:
        """Complete using custom HTTP endpoint"""
        try:
            # Replace placeholders in payload template
            payload_str = self.payload_template.replace("{prompt}", prompt)
            if system:
                payload_str = payload_str.replace("{system}", system)
            if temperature is not None:
                payload_str = payload_str.replace("{temperature}", str(temperature))
            if max_tokens is not None:
                payload_str = payload_str.replace("{max_tokens}", str(max_tokens))
            
            payload = json.loads(payload_str)
            
            client = self._get_client()
            response = await client.post(self.base_url, json=payload)
            response.raise_for_status()
            
            # Try to extract text from response
            data = response.json()
            content = str(data)  # Basic fallback
            
            # Try common response formats
            if isinstance(data, dict):
                for key in ["text", "response", "content", "output"]:
                    if key in data:
                        content = data[key]
                        break
            
            yield content
            
        except Exception as e:
            yield f"Error: {str(e)}"


class BackendManager:
    """Manages multiple LLM backends"""
    
    def __init__(self):
        self.backends: Dict[str, LLMBackend] = {}
        self._setup_default_backends()
    
    def _setup_default_backends(self):
        """Setup default backends"""
        self.backends["openai"] = OpenAIBackend()
        self.backends["ollama"] = OllamaBackend()
        self.backends["lmstudio"] = LMStudioBackend()
    
    def get_backend(self, name: str) -> Optional[LLMBackend]:
        """Get backend by name"""
        return self.backends.get(name)
    
    def add_backend(self, backend: LLMBackend):
        """Add a custom backend"""
        self.backends[backend.name] = backend
    
    def list_backends(self) -> List[str]:
        """List all available backends"""
        return list(self.backends.keys())
    
    async def test_backend(self, name: str, test_prompt: str = "Hello") -> Dict[str, Any]:
        """Test a backend with a simple prompt"""
        backend = self.get_backend(name)
        if not backend:
            return {"success": False, "error": f"Backend {name} not found"}
        
        start_time = time.time()
        try:
            models = await backend.list_models()
            if not models:
                return {"success": False, "error": "No models available"}
            
            model = models[0]
            response_parts = []
            
            async for chunk in backend.complete(
                prompt=test_prompt,
                model=model,
                stream=False
            ):
                response_parts.append(chunk)
            
            response = "".join(response_parts)
            duration = int((time.time() - start_time) * 1000)
            
            return {
                "success": True,
                "response": response,
                "duration_ms": duration,
                "models": models
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# Global backend manager instance
backend_manager = BackendManager()
