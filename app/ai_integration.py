import os
import requests
import json

API_URL = "https://router.huggingface.co/v1/chat/completions"

def _headers():
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN not set in environment")
    return {"Authorization": f"Bearer {token}"}

def _query(payload):
    r = requests.post(API_URL, headers=_headers(), json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def generate_tf_code(prompt: str) -> str:
    """
    Generate ONLY Terraform HCL using a Hugging Face chat-completions compatible endpoint.
    Output contains NO explanations/markdown — only HCL.
    """
    try:
        response = _query({
            "model": "openai/gpt-oss-120b:groq",  # change to another HF router model if desired
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Terraform expert. "
                        "Respond ONLY with valid Terraform HCL. "
                        "No comments, no markdown, no explanations. "
                        "If not Terraform-related, respond with empty string."
                    )
                },
                {"role": "user", "content": f"Write Terraform HCL for: {prompt}"}
            ],
        })

        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            raise RuntimeError(f"No HCL returned. Raw: {json.dumps(response, indent=2)}")
        return content

    except Exception as e:
        raise RuntimeError(f"Hugging Face API error: {e}")
