# Sophos AI - RAG-Powered Expert Bot

A sophisticated Retrieval-Augmented Generation (RAG) system designed to answer questions about Axway Secure Transport. This project combines a FastAPI backend with a React frontend, leveraging state-of-the-art machine learning models for intelligent document retrieval and response generation.

## 🌟 Features

- **Intelligent Question Answering**: RAG-based system that retrieves relevant documents and generates accurate answers
- **Streaming Responses**: Real-time streaming of AI responses using Server-Sent Events (SSE)
- **Document Ingestion**: Admin capability to upload and process new knowledge documents
- **User Authentication**: Secure login system with role-based access (admin/user)
- **Feedback System**: Users can report incorrect answers with notifications sent to Microsoft Teams
- **Hybrid Search**: Combines semantic search with TF-IDF for improved retrieval accuracy
- **Reranking**: Advanced cross-encoder model for result refinement
- **Modern UI**: React 19-based frontend with markdown rendering support

## 🏗️ Architecture

### Tech Stack

#### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **Qdrant**: Vector database for storing document embeddings
- **Ollama**: Local LLM deployment (llama3.2:3b)
- **LangChain**: Framework for building LLM applications
- **Transformers**: Hugging Face for ML model management
- **SQLite**: Lightweight database for user management
- **Unstructured**: Document parsing and ingestion

#### Frontend
- **React 19**: Latest version of React
- **React Markdown**: Markdown rendering for AI responses
- **FastAPI Streaming**: Real-time response streaming

#### Machine Learning Models
- **Embedding**: Qwen/Qwen3-Embedding-0.6B (6B parameters)
- **Reranker**: BAAI/bge-reranker-v2-m3 (cross-encoder)
- **LLM**: qwen3:1.7b (via Ollama)

### System Components

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React Frontend│────▶│  FastAPI Backend│────▶│   Ollama LLM    │
│   (Port 3000)   │     │   (Port 8000)   │     │  (Port 11434)   │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                │
                                ▼
                         ┌─────────────────┐
                         │     Qdrant      │
                         │   (Port 6333)   │
                         │  Vector Store   │
                         └─────────────────┘
```

## 📋 Prerequisites

### Required Software

1. **Python 3.9+**
   ```bash
   python --version
   ```

2. **Node.js 18+** (with npm)
   ```bash
   node --version
   npm --version
   ```

3. **Qdrant Vector Database**
   ```bash
   # Using Docker (recommended)
   docker run -p 6333:6333 qdrant/qdrant

   # Or download from: https://qdrant.tech/downloads/
   ```

4. **Ollama**
   ```bash
   # Download from: https://ollama.com/download
   # Or install via script (Linux/macOS):
   curl -fsSL https://ollama.com/install.sh | sh

   # Pull the required model
   ollama pull qwen3:1.7b
   ```

### Environment Variables

Copy the example environment file and configure it:

```bash
cd sophos_ai_backend
cp env.example .env
```

Edit `.env` with your configuration:

```env
# Ollama Configuration
OLLAMA_BASE_URL="http://localhost:11434"

# Qdrant Configuration
QDRANT_URL="http://localhost:6333"
QDRANT_API_KEY=""  # Optional: Only if using Qdrant Cloud

# Teams Webhook (Optional)
TEAMS_WEBHOOK_URL="https://your-company.webhook.office.com/..."
```

## 🚀 Getting Started

### Step 1: Clone the Repository

```bash
git clone https://git-ext.ecd.axway.com/gss-noida/ai/sophos.git
cd Sophos_AI
```

### Step 2: Set Up the Backend

```bash
cd sophos_ai_backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Wait for models to download (first run only - takes several minutes)
# The system will automatically download:
# - Qwen/Qwen3-Embedding-0.6B (~11 GB)
# - BAAI/bge-reranker-v2-m3 (~1.1 GB)
```

### Step 3: Set Up the Frontend

```bash
cd sophos-ai-frontend

# Install dependencies
npm install

# This will install all React dependencies including:
# - react@^19.1.1
# - react-dom@^19.1.1
# - react-markdown@^10.1.0
# - And testing libraries
```

### Step 4: Start External Services

Make sure Qdrant and Ollama are running:

```bash
# Terminal 1: Start Qdrant (if using Docker)
docker run -p 6333:6333 qdrant/qdrant

# Terminal 2: Start Ollama
ollama serve

# Verify Ollama is running
ollama list
# Should show: qwen3:1.7b
```

### Step 5: Run the Application

#### Option A: Development Mode (Recommended for development)

Open three terminals:

**Terminal 1 - Backend:**
```bash
cd sophos_ai_backend
# Activate venv (Windows)
venv\Scripts\activate
# Or (Linux/macOS)
source venv/bin/activate

# Start FastAPI with auto-reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd sophos-ai-frontend

# Start React development server
npm start
```

The application will be available at:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

#### Option B: Production Mode

**Build the Frontend:**
```bash
cd sophos-ai-frontend
npm run build
# This creates an optimized production build in the `build/` directory
```

**Run Backend (Production):**
```bash
cd sophos_ai_backend
# Activate venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/macOS

# Start with production server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Serve Frontend (using a production web server):**
```bash
cd sophos-ai-frontend/build

# Option 1: Using Python's built-in server
python -m http.server 3000

# Option 2: Using serve (npm install -g serve)
serve -s build -l 3000

# Option 3: Using nginx (recommended for production)
# Configure nginx to serve the build/ directory
```

## 🔧 Build Commands Reference

### Backend Commands

```bash
# Navigate to backend directory
cd sophos_ai_backend

# Install dependencies
pip install -r requirements.txt

# Update dependencies
pip install --upgrade -r requirements.txt

# Run in development mode (with auto-reload)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Run in production mode
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Run with specific log level
uvicorn api.main:app --reload --log-level debug

# Check API documentation (interactive)
# Open http://localhost:8000/docs in browser
```

### Frontend Commands

```bash
# Navigate to frontend directory
cd sophos-ai-frontend

# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build

# Run tests
npm test

# Eject from Create React App (not recommended)
npm run eject
```

### Database Management Commands

```bash
# Navigate to backend
cd sophos_ai_backend

# Recreate Qdrant collection (clears all data)
python core/qdrant_recreate.py

# Ingest documents into the knowledge base
python file_upload/one_off_ingest.py

# Test Qdrant connection
python file_upload/test_qdrant.py
```

## 📚 API Documentation

The backend provides interactive API documentation powered by Swagger UI.

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key API Endpoints

#### Public Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API status check |
| POST | `/login` | User authentication |
| GET | `/query` | Ask a question (streaming response) |
| POST | `/report-incorrect` | Report an incorrect answer |

#### Admin Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/admin/upload` | Upload new documents |
| POST | `/admin/clear-database` | Clear vector database |
| GET | `/admin/stats` | Get database statistics |

### Example API Usage

**Login:**
```bash
curl -X POST "http://localhost:8000/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'
```

**Query Question (Streaming):**
```bash
curl "http://localhost:8000/query?question=How%20do%20I%20configure%20SSL?"
```

**Report Incorrect Answer:**
```bash
curl -X POST "http://localhost:8000/report-incorrect" \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "question": "...", "answer": "..."}'
```

## 🗄️ Data Storage

### File Structure

```
sophos_ai_backend/
├── data/                          # Databases and model artifacts
│   ├── users.db                   # User authentication database
│   ├── app_metadata.db            # Application metadata
│   ├── log_codes.db               # Log code references
│   ├── diag_codes.db              # Diagnostic codes
│   └── tfidf_vectorizer.pkl       # TF-IDF vectorizer model
├── file_upload/                   # Document ingestion scripts
│   ├── one_off_ingest.py          # Batch document ingestion
│   └── heading_chunker_ingest.py  # Heading-based chunking
└── uploads/                       # Temporary file storage
```

### Vector Database (Qdrant)

- **Collection Name**: Configured in `core/rag_bot.py`
- **Embedding Model**: Qwen3-Embedding-0.6B (6B parameters)
- **Dimension**: 1536
- **Distance Metric**: Cosine

### User Database (SQLite)

Default users are created on first run:
- **Admin**: username=`admin`, password=`admin123`
- **User**: username=`user`, password=`user123`

## 🧪 Testing

### Backend Testing

```bash
cd sophos_ai_backend

# Run specific test files
python -m pytest tests/

# Run with coverage
python -m pytest --cov=. --cov-report=html
```

### Frontend Testing

```bash
cd sophos-ai-frontend

# Run tests in watch mode
npm test

# Run tests once
npm test -- --watchAll=false

# Generate coverage report
npm test -- --coverage
```

## 📊 Performance Tuning

### Backend Optimization

**Adjust Worker Count:**
```bash
# For production with 4 workers
uvicorn api.main:app --workers 4
```

**Adjust RAG Parameters** (in `core/config.py`):
```python
# Number of documents to retrieve
SEARCH_K = 5

# Similarity threshold for filtering
SIMILARITY_THRESHOLD = 0.6

# Document chunking
CHUNK_SIZE = 2000
CHUNK_OVERLAP = 300
```

### Frontend Optimization

The production build automatically:
- Minifies JavaScript and CSS
- Optimizes images
- Splits code into chunks
- Adds service worker support (PWA ready)

## 🔒 Security Considerations

1. **Environment Variables**: Never commit `.env` files
2. **CORS**: Currently allows all origins (`*`) - restrict in production
3. **Authentication**: Implement JWT tokens for production
4. **Rate Limiting**: Add rate limiting to prevent abuse
5. **Input Validation**: Already implemented with Pydantic schemas

## 🐛 Troubleshooting

### Common Issues

**Issue: Model download fails on first run**
```bash
# Solution: Pre-download models manually
python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
AutoTokenizer.from_pretrained('Qwen/Qwen3-Embedding-0.6B'); \
AutoModelForSequenceClassification.from_pretrained('BAAI/bge-reranker-v2-m3', num_labels=1)"
```

**Issue: Qdrant connection refused**
```bash
# Solution: Ensure Qdrant is running
docker ps | grep qdrant
# Or start it:
docker run -p 6333:6333 qdrant/qdrant
```

**Issue: Ollama model not found**
```bash
# Solution: Pull the required model
ollama pull qwen3:1.7b
ollama list  # Verify it's available
```

**Issue: Port already in use**
```bash
# Solution: Change port or kill the process
# On Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# On Linux/macOS:
lsof -ti:8000 | xargs kill -9
```

**Issue: Frontend can't connect to backend**
```bash
# Solution: Check CORS settings in api/main.py
# Ensure the backend URL is correct in frontend code
```

## 📝 Development Workflow

### Adding New Features

1. **Backend Changes**:
   - Update API in `api/main.py`
   - Add schemas in `api/schemas.py`
   - Implement logic in `core/`
   - Test with Swagger UI at `/docs`

2. **Frontend Changes**:
   - Create components in `src/components/`
   - Update routing in `src/App.js`
   - Add styling in `src/App.css` or component files
   - Test with `npm start`

### Code Style

- **Python**: Follow PEP 8
- **JavaScript/React**: Follow ESLint rules (pre-configured)
- Use meaningful variable names
- Add docstrings to functions
- Comment complex logic

## 🚢 Deployment

### Docker Deployment (Recommended)

**Backend Dockerfile** (create `sophos_ai_backend/Dockerfile`):
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend Dockerfile** (create `sophos-ai-frontend/Dockerfile`):
```dockerfile
FROM node:18-alpine as build
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
```

**Docker Compose** (create `docker-compose.yml`):
```yaml
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant
    ports:
      - "6333:6333"

  backend:
    build: ./sophos_ai_backend
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
    environment:
      - QDRANT_URL=http://qdrant:6333

  frontend:
    build: ./sophos-ai-frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

**Deploy with Docker Compose:**
```bash
docker-compose up -d --build
```

## 📈 Monitoring and Logging

### Backend Logs

FastAPI provides structured logging:
```bash
# View logs in real-time
uvicorn api.main:app --log-level info
```

### Frontend Logs

Check browser console (F12) for client-side errors.

### Performance Monitoring

Consider adding:
- Prometheus for metrics
- Grafana for visualization
- Sentry for error tracking

## 🤝 Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Code Review Guidelines

- Ensure all tests pass
- Follow code style guidelines
- Update documentation as needed
- Add tests for new features

## 📄 License

This project is proprietary software. All rights reserved.

## 📞 Support

For support, please contact:
- **Email**: support@axway.com
- **Issues**: Use the project's issue tracker
- **Documentation**: Check this README and inline code documentation

## 🔗 Related Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Ollama Documentation](https://ollama.com/docs)
- [LangChain Documentation](https://python.langchain.com/)
- [React Documentation](https://react.dev/)
- [RAG Concepts](https://www.anthropic.com/index/retrieval-augmented-generation)

### Version History

- **v1.0.0** (Current)
  - Initial release
  - Basic RAG functionality
  - User authentication
  - Document upload
  - Streaming responses

---

**Built with ❤️ by the Axway AI Team**
