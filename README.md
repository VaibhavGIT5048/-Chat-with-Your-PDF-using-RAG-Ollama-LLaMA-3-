
# 📘 Chat with Your PDF using RAG + Ollama (LLaMA 3) / Semantic Question Answering over Large PDFs
using Retrieval-Augmented Generation (RAG)

This project allows you to upload any PDF and interact with it using a local LLM (LLaMA 3 via Ollama) combined with Retrieval-Augmented Generation (RAG). It uses LangChain, FAISS, HuggingFace embeddings, and Streamlit.

## 🛠️ Features

- Upload and analyze any PDF
- Ask natural language questions
- Uses FAISS vector search
- LLM-powered responses using locally hosted `llama3` model via Ollama
- Lightweight, browser-based UI via Streamlit

---

## ⚙️ Installation

1. **Set up Ollama with LLaMA 3**  
   Make sure Ollama is installed and LLaMA 3 is available:

   ```bash
   brew install ollama
   ollama pull llama3
   ollama run llama3


AI:ML/
├── rag_ui.py              # Main Streamlit app
├── ag_streamlit.py        # (Optional) Additional streamlit variant
├── temp.pdf               # Temporarily saved PDF (uploaded by user)
├── README.md              # Documentation (see below)
└── requirements.txt       # All dependencies

pip install -r requirements.txt
streamlit
langchain
langchain-community
faiss-cpu
sentence-transformers


