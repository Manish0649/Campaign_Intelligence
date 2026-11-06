
from backend.app.config import settings
from google import genai

client = genai.Client(api_key=settings.gemini_api_key)

print("Testing model:", settings.gemini_generation_model)

try:
    response = client.models.generate_content(
        model=settings.gemini_generation_model,
        contents="Say hello in one sentence."
    )

    print("Gemini response:", response.text)

except Exception as exc:
    print("Error type:", type(exc).__name__)
    print("Error details:", str(exc))
