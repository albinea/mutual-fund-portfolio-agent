from app.llm import generate_response
from app.llm import get_llm

prompt = """
You are a mutual-fund research assistant.

Return ONLY valid JSON in exactly this format:

{
  "answer": "string",
  "confidence": 0.0,
  "sources": []
}

Question:
What is a mutual fund?
"""


response = generate_response(prompt)

print("ANSWER:")
print(response.answer)

print("\nCONFIDENCE:")
print(response.confidence)

print("\nSOURCES:")
print(response.sources)