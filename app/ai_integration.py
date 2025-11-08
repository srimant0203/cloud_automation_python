import os
import requests
import json

API_URL = "https://router.huggingface.co/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {os.environ['HF_TOKEN']}",
}

def query(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

def generate_tf_code(prompt: str) -> str:
    """
    Generate ONLY Terraform HCL using Hugging Face's openai/gpt-oss-120b:groq model.
    Output will contain NO explanations, markdown, or text other than valid HCL.
    """

    try:
        response = query({
            "model": "openai/gpt-oss-120b:groq",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Terraform expert. "
                        "Respond ONLY with valid Terraform HCL code. "
                        "Do NOT include markdown, explanations, or comments. "
                        "If the user asks for something not related to Terraform, respond with an empty string."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Write Terraform HCL for: {prompt}"
                },
            ],
        })

        message = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not message:
            raise RuntimeError(f"No content returned. Raw response: {json.dumps(response, indent=2)}")

        return message

    except Exception as e:
        raise RuntimeError(f"Hugging Face API error: {e}")
