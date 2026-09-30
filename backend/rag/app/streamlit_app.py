import streamlit as st
from dotenv import load_dotenv

from app.fallback import LLMFallback
from app.llm import generate_response, get_llm
from app.logging_config import logger
from app.prompts import build_prompt


load_dotenv()


st.set_page_config(
    page_title="FundLens RAG",
    page_icon="📊",
    layout="wide",
)


st.title("📊 FundLens RAG")
st.caption(
    "Mutual-fund document research with evidence-backed answers."
)


def generate_answer(
    question: str,
    context: str,
):
    """
    Generate an answer from retrieved RAG context.
    """

    prompt = build_prompt(
        question=question,
        context=context,
        version="v1",
    )

    primary_llm = get_llm()

    fallback = LLMFallback(
        primary=lambda p: generate_response(
            p,
            llm=primary_llm,
        )
    )

    return fallback.invoke(prompt)


# ---------------------------------------------------------
# Sidebar
# ---------------------------------------------------------

with st.sidebar:
    st.header("RAG Settings")

    prompt_version = st.selectbox(
        "Prompt version",
        ["v1"],
    )

    st.divider()

    st.info(
        "The production version will connect this interface "
        "to Qdrant retrieval and the LangGraph agent."
    )


# ---------------------------------------------------------
# Question
# ---------------------------------------------------------

question = st.text_input(
    "Ask a question about a mutual fund document",
    placeholder="Why did the fund increase its exposure to IT?",
)


# ---------------------------------------------------------
# Temporary context input
# ---------------------------------------------------------

st.subheader("Retrieved Context")

context = st.text_area(
    "Paste retrieved document chunks here for now",
    height=250,
    placeholder=(
        "This will later be populated automatically "
        "from Qdrant retrieval."
    ),
)


# ---------------------------------------------------------
# Generate
# ---------------------------------------------------------

if st.button("Ask FundLens", type="primary"):

    if not question.strip():
        st.warning("Please enter a question.")
        st.stop()

    if not context.strip():
        st.warning("Please provide retrieved context.")
        st.stop()

    try:
        with st.spinner("Analyzing documents..."):

            prompt = build_prompt(
                question=question,
                context=context,
                version=prompt_version,
            )

            llm = get_llm()

            response = generate_response(
                prompt=prompt,
                llm=llm,
            )

        st.subheader("Answer")

        st.write(response.answer)

        st.subheader("Confidence")

        st.progress(response.confidence)

        st.write(
            f"{response.confidence:.0%}"
        )

        if response.sources:

            st.subheader("Sources")

            for source in response.sources:

                st.markdown(
                    f"- **{source.document}** — "
                    f"Page {source.page} — "
                    f"[Source]({source.source_url})"
                )

        else:
            st.info(
                "No document citations were returned."
            )

    except Exception as exc:

        logger.exception(
            "Failed to generate RAG response"
        )

        st.error(
            f"Unable to generate response: {exc}"
        )