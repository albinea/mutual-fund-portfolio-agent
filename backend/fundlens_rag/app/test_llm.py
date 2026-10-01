from fundlens_rag.app.llm import generate_response


def main() -> None:
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


if __name__ == "__main__":
    main()
