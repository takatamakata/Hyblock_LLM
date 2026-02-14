import json
import logging
from typing import Dict, Any, Optional, List
from openai import AsyncOpenAI
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.OPENROUTER_API_KEY,
        )
        self.model = config.MODEL_NAME

    async def get_completion(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        json_mode: bool = True
    ) -> Dict[str, Any]:
        """
        Get completion from LLM.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                response_format={"type": "json_object"} if json_mode else None,
                extra_headers={
                    "HTTP-Referer": "https://hyblockcapital.com", # Optional, for OpenRouter rankings
                    "X-Title": "Hyblock Backtester"
                }
            )
            
            content = response.choices[0].message.content
            
            if json_mode:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    # Attempt to clean markdown if present
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].strip()
                    return json.loads(content)
            
            return content

        except Exception as e:
            logger.error(f"LLM Request failed: {e}")
            raise

