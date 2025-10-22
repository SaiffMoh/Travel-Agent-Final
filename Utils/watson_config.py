import requests
import os
from dotenv import load_dotenv
from enum import Enum

load_dotenv()


class ModelType(Enum):
    """Enum for different model types and their optimal use cases."""
    EXTRACTION = "meta-llama/llama-3-3-70b-instruct"  # Best for CV extraction & screening
    CLASSIFICATION = "mistralai/mistral-small-3-1-24b-instruct-2503"  # Best for routing & intent
    GENERIC = "mistralai/mistral-small-3-1-24b-instruct-2503"  # Best for general Q&A


class WatsonxLLM:
    """
    Multi-model Watson LLM configuration.
    Routes requests to optimal models based on task type.
    """
    
    def __init__(
        self,
        default_model: ModelType = ModelType.CLASSIFICATION,
        temperature: float = 0,
        max_tokens: int = 8192,
        project_id: str = None
    ):
        """
        Initialize multi-model Watson LLM.
        
        Args:
            default_model: Default model to use (can be overridden per request)
            temperature: Temperature for generation (0-1)
            max_tokens: Maximum tokens in the response
            project_id: IBM Watson project ID (defaults to env variable)
        """
        self.default_model = default_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.project_id = project_id or os.getenv("PROJECT_ID")
        self.url = "https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29"
        
        # Get initial token
        self._token = None
        self._refresh_token()
    
    def _get_iam_token(self) -> str:
        """Get IBM Cloud IAM authentication token."""
        token_url = "https://iam.cloud.ibm.com/identity/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": os.getenv('WATSON_APIKEY')
        }
        resp = requests.post(token_url, headers=headers, data=data)
        resp.raise_for_status()
        token_json = resp.json()
        return token_json["access_token"]
    
    def _refresh_token(self):
        """Refresh the authentication token."""
        self._token = self._get_iam_token()
    
    def generate(
        self, 
        prompt: str, 
        model_type: ModelType = None,
        params: dict = None
    ) -> dict:
        """
        Generate a response from the model given a prompt.
        Routes to appropriate model based on task type.
        
        Args:
            prompt: The complete prompt string
            model_type: Override default model (uses default if None)
            params: Optional parameters to override instance defaults
            
        Returns:
            Dictionary in ModelInference format:
            {
                'results': [{
                    'generated_text': str,
                    'generated_token_count': int,
                    'input_token_count': int,
                    'stop_reason': str
                }]
            }
        """
        # Determine which model to use
        selected_model = model_type or self.default_model
        model_id = selected_model.value
        
        # Adjust temperature based on model type for consistency
        temperature = params.get('temperature', self.temperature) if params else self.temperature
        
        # Classification and generic tasks benefit from slightly higher temperature for better accuracy
        if selected_model in [ModelType.CLASSIFICATION, ModelType.GENERIC]:
            temperature = min(temperature + 0.1, 1.0) if temperature < 1.0 else temperature
        
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "project_id": self.project_id,
            "model_id": model_id,
            "frequency_penalty": 0,
            "max_tokens": params.get('max_tokens', self.max_tokens) if params else self.max_tokens,
            "presence_penalty": 0,
            "temperature": temperature,
            "top_p": 1
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self._token
        }
        
        print(f"🤖 Using model: {model_id}")
        
        # Make request
        response = requests.post(self.url, headers=headers, json=body)
        
        # If token expired, refresh and retry
        if response.status_code == 401:
            self._refresh_token()
            headers["Authorization"] = "Bearer " + self._token
            response = requests.post(self.url, headers=headers, json=body)
        
        if response.status_code != 200:
            raise Exception(f"Non-200 response ({response.status_code}): {response.text}")
        
        data = response.json()
        choice = data['choices'][0]
        usage = data.get('usage', {})
        
        return {
            'results': [{
                'generated_text': choice['message']['content'],
                'generated_token_count': usage.get('completion_tokens', 0),
                'input_token_count': usage.get('prompt_tokens', 0),
                'stop_reason': choice.get('finish_reason', 'completed')
            }]
        }
    
    def update_params(self, **kwargs):
        """
        Update generation parameters.
        
        Args:
            **kwargs: Parameter names and values to update
        """
        if 'temperature' in kwargs:
            self.temperature = kwargs['temperature']
        if 'max_tokens' in kwargs:
            self.max_tokens = kwargs['max_tokens']


# ============================================================================
# TASK-SPECIFIC INSTANCES
# ============================================================================

# For classification and routing - fast and accurate
llm_classification = WatsonxLLM(
    default_model=ModelType.CLASSIFICATION,
    temperature=0,
    max_tokens=100  # Classification only needs short responses
)

# For CV extraction and screening - detailed analysis required
llm_extraction = WatsonxLLM(
    default_model=ModelType.EXTRACTION,
    temperature=0,
    max_tokens=8192  # Extraction needs detailed JSON output
)

# For generic Q&A and user interactions - balanced
llm_generic = WatsonxLLM(
    default_model=ModelType.GENERIC,
    temperature=0.1,
    max_tokens=2048  # General responses need reasonable length
)

# Default instance using Llama 3.3 70B for backward compatibility
# Used by other nodes that haven't been migrated yet
llm = WatsonxLLM(
    default_model=ModelType.EXTRACTION,
    temperature=0,
    max_tokens=8192
)


if __name__ == "__main__":
    # Test different models
    test_prompt = "Classify this: User wants to screen candidates"
    
    print("\n=== Testing Classification Model ===")
    response = llm_classification.generate(test_prompt)
    print(f"Response: {response['results'][0]['generated_text']}")
    
    print("\n=== Testing Extraction Model ===")
    response = llm_extraction.generate(test_prompt)
    print(f"Response: {response['results'][0]['generated_text']}")
    
    print("\n=== Testing Generic Model ===")
    response = llm_generic.generate(test_prompt)
    print(f"Response: {response['results'][0]['generated_text']}")