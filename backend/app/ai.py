from openai import OpenAI
from .config import settings

client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None


def generate_reply(user_input: str) -> str:
    if not user_input:
        return "Could you please repeat that?"

    lowered = user_input.lower()

    if "appointment" in lowered or "book" in lowered or "schedule" in lowered:
        return "Sure. I can help with scheduling. Please tell me your preferred day and time, and the best callback number."

    if "hours" in lowered or "open" in lowered or "close" in lowered:
        return f"Our business hours are {settings.business_hours}. What else can I help you with?"

    if client is None:
        return f"I heard you say {user_input}. How else can I help you today?"

    system_prompt = (
        f"You are a friendly and concise receptionist for {settings.business_name}. "
        f"Keep answers short, natural, and business-appropriate. "
        f"If someone wants to book an appointment, ask for day, time, and callback number. "
        f"Business hours are: {settings.business_hours}."
    )

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ],
        temperature=0.4,
    )
    return response.choices[0].message.content or "How can I help you today?"
