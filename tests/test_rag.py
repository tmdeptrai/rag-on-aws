import os
import sys
import json
import pytest
import re
from google import genai
from google.genai import types
from google.auth import default
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    ContextualPrecisionMetric
)
from deepeval.models.base_model import DeepEvalBaseLLM
from dotenv import load_dotenv

# --- 1. SETUP & IMPORTS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

load_dotenv()

from backend.query.query import lambda_handler as query_handler

# --- 2. ROBUST JUDGE CLASS (Vertex AI) ---
class GeminiDeepEvalLLM(DeepEvalBaseLLM):
    def __init__(self, model_name="gemini-2.0-flash"):
        self.model_name = model_name
        try:
            credentials, project_id = default()
            self.client = genai.Client(
                vertexai=True, 
                project=project_id, 
                location="europe-west1"
            )
        except Exception as e:
            print(f"Vertex Auth Failed: {e}")
            self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

    def load_model(self):
        return self.client

    def _clean_json(self, text: str) -> str:
        text = text.replace("```json", "").replace("```", "").strip()
        invalid_escape_pattern = r'\\(?![\\"/bfnrtu])'
        return re.sub(invalid_escape_pattern, r'\\\\', text)

    def generate(self, prompt: str) -> str:
        config = types.GenerateContentConfig(temperature=0)
        if "json" in prompt.lower() or "output format" in prompt.lower():
            config.response_mime_type = "application/json"

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return self._clean_json(response.text)
        except Exception:
            return '{"reason": "Rate limit or Error", "score": 0, "success": false}'

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self):
        return self.model_name

gemini_judge = GeminiDeepEvalLLM()

def run_rag_locally(question, user_email="minhduongqo@gmail.com"):
    mock_event = {
        "body": json.dumps({
            "query": question, 
            "question": question,
            "user_email": user_email
        })
    }
    response = query_handler(mock_event, None)
    
    if response.get('statusCode') != 200:
        return "Error", []

    try:
        body = json.loads(response['body'])
        actual_answer = body.get('answer', "")
        raw_refs = body.get('references', [])
        
        # Format context for DeepEval
        if raw_refs and isinstance(raw_refs[0], dict):
            retrieval_context = [str(r.get('content', r)) for r in raw_refs]
        else:
            retrieval_context = [str(r) for r in raw_refs]
            
        return actual_answer, retrieval_context
    except:
        return "Error", []

# Load Goldens from JSON
dataset_path = os.path.join(current_dir, "golden_dataset.json")
goldens_list = []

if os.path.exists(dataset_path):
    with open(dataset_path, "r") as f:
        data = json.load(f)
        for entry in data:
            goldens_list.append(
                Golden(input=entry["input"], expected_output=entry["expected_output"])
            )

# Create EvaluationDataset (Used for parametrization)
dataset = EvaluationDataset(goldens=goldens_list)

# --- THE PYTEST FUNCTION ---
@pytest.mark.parametrize("golden", dataset.goldens)
def test_rag(golden: Golden):
    # 1. Run the RAG Pipeline "Live"
    actual_output, retrieval_context = run_rag_locally(golden.input)

    # 2. Create the Test Case
    test_case = LLMTestCase(
        input=golden.input,
        actual_output=actual_output,
        expected_output=golden.expected_output,
        retrieval_context=retrieval_context
    )

    # 3. Define Metrics (Judge)
    metrics = [
        FaithfulnessMetric(threshold=0.7, model=gemini_judge, include_reason=True, async_mode=True),
        AnswerRelevancyMetric(threshold=0.7, model=gemini_judge, include_reason=True, async_mode=True),
        ContextualPrecisionMetric(threshold=0.7, model=gemini_judge, include_reason=True, async_mode=True)
    ]

    # 4. Assert (This runs the evaluation)
    assert_test(test_case, metrics)