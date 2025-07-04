from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA

# Load and split PDF
loader = PyPDFLoader("/Users/vaibhavgupta7047/Documents/Vscode/AI:ML/WEF_Travel_and_Tourism_at_a_Turning_Point_2025.pdf")
documents = loader.load()

splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
chunks = splitter.split_documents(documents)

# Embed chunks
embedding = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vectorstore = FAISS.from_documents(chunks, embedding)
retriever = vectorstore.as_retriever()

# Connect to Ollama model
llm = Ollama(model="llama3")

# Set up RetrievalQA
query = """
You are an expert analyst. Read the following extracted content from a PDF report and provide:
1. A detailed summary of the key insights and findings.
2. A bullet-point list of the most important recommendations.
3. Any trends, statistics, or figures mentioned.
4. The general tone or purpose of the document.

Respond in markdown format.
"""

qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever)
result = qa_chain.invoke(query)


# Ask question
query = "Summarize the key ideas in this PDF."
result = qa_chain.run(query)

print("\n📄 Answer:\n", result)
