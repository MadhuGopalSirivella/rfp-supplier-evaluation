from openai import OpenAI


def validate_api_key_and_list_models(api_key: str) -> list[str]:
    client = OpenAI(api_key=api_key, timeout=20, max_retries=0)
    available = client.models.list()
    model_ids = sorted({item.id for item in available.data})
    chat_models = [
        model_id for model_id in model_ids
        if model_id.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))
        and not any(token in model_id.lower() for token in (
            "audio", "realtime", "transcribe", "tts", "embedding", "whisper", "dall-e"
        ))
    ]
    if not chat_models:
        raise ValueError("The key is valid, but no supported chat models were returned for this account.")
    return chat_models