import streamlit as st
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
import os

def main():
    st.set_page_config(page_title="📄 RAG PDF Chat", layout="centered")
    st.title("📘 Chat with your PDF using RAG + Ollama")

    uploaded_file = st.file_uploader("Upload a PDF", type="pdf")

    if uploaded_file is not None:
        with open("temp.pdf", "wb") as f:
            f.write(uploaded_file.read())
        
        st.success("✅ PDF uploaded successfully. Initializing RAG pipeline...")

        with st.spinner("📚 Reading & indexing the PDF..."):
            loader = PyPDFLoader("temp.pdf")
            documents = loader.load()

            splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
            chunks = splitter.split_documents(documents)

            embedding = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            vectorstore = FAISS.from_documents(chunks, embedding)
            retriever = vectorstore.as_retriever()

            llm = Ollama(model="llama3")
            qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)

        st.success("✅ RAG pipeline ready! Ask questions below:")

        question = st.text_input("Ask something about the PDF:")

        if question:
            with st.spinner("💬 Thinking..."):
                try:
                    answer = qa_chain.run(question)
                    st.markdown("### 💡 Answer")
                    st.markdown(answer)
                except Exception as e:
                    st.error(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
