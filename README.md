# ⚡ Real Estate Voice Agent (Sarvam AI STT + FAISS RAG Edition)

**Real Estate Voice Agent** is a performance-optimized outbound voice assistant for **Real Estate Management**. It features a robust **FAISS RAG** system and is heavily optimized for ultra-low latency interactions using **Sarvam AI STT** and **TTS**.

## 🚀 Key Features
- **Ultra-Low Latency**: Target < 1.5s total turnaround time.
- **Sarvam AI Integration**: High-quality Indian language support (Gujarati).
- **FAISS RAG**: Vector search for property listings.
- **Render Ready**: Optimized for deployment on Render.

## 🛠️ Tech Stack
- **Backend**: FastAPI (Python)
- **Frontend**: React (Vite + Tailwind CSS)
- **AI**: OpenAI GPT-4o-mini, Sarvam AI STT/TTS
- **Database**: SQLite + FAISS (Vector DB)

## 📦 Deployment on Render
1. Connect this GitHub repository to your Render account.
2. Render will automatically detect the `render.yaml` blueprint.
3. Set the following environment variables in the Render dashboard:
   - `VOBIZ_AUTH_ID`
   - `VOBIZ_AUTH_TOKEN`
   - `VOBIZ_FROM_NUMBER`
   - `OPENAI_API_KEY`
   - `SARVAM_API_KEY`
   - `BASE_URL` (Set to your Render app URL)

## 💻 Local Development
1. Clone the repository.
2. Install dependencies: `pip install -r requirements.txt && npm install`.
3. Run the development environment: `./run_gunivox.sh`.