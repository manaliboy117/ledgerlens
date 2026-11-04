import streamlit as st

st.set_page_config(
    page_title="LedgerLens",
    page_icon="📚",
    layout="wide"
)

st.title("📚 LedgerLens")
st.subheader("AI-powered Tax Research Assistant")

st.info(
    "Ask questions about your trusted tax documents. "
    "Answers will be grounded in retrieved sources."
)

question = st.text_input("Enter your tax question")

if st.button("Search") and question:
    st.warning(
        "Document retrieval will be added in the next step."
    )
