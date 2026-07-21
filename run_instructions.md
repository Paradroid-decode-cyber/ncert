# How to set up and run the NCERT Personalized Engine

This guide will walk you through setting up and running the backend FastAPI application locally.

## 1. Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/).
*   **pip**: Python's package installer (usually comes with Python).
*   **Node.js and npm/yarn** (Optional, only if you plan to run the frontend part of the application. The backend can run independently.)

## 2. Project Setup

1.  **Navigate to the project directory**:
    Open your terminal or command prompt and change your current directory to the `ncert_personal_engine` folder:

    ```bash
    cd ncert_personal_engine
    ```

2.  **Create a virtual environment (recommended)**:
    A virtual environment helps manage project dependencies separately.

    ```bash
    python -m venv venv
    source venv/bin/activate # On Windows, use `venv\Scripts\activate`
    source venv/Scripts/activate
    ```

3.  **Install Python dependencies**:
    Install all required Python packages using pip:

    ```bash
    pip install -r requirements.txt
    ```

## 3. Environment Variables Configuration


The application uses                        environment variables for sensitive information and configuration settings. You'll need to create a `.env` file in the root of the `ncert_personal_engine` directory.
=======
The application uses environment variables for sensitive information and configuration settings. You'll need to create a `.env` file in the root of the `ncert_personal_engine` directory.


**Create a file named `.env`** in the `ncert_personal_engine` directory with the following content. **Replace the placeholder values** with your actual API keys and desired settings.

```dotenv
# --- Database Configuration ---
# Path to your SQLite database file.
# The application will create a 'db' directory and 'ncert_tutor.db' inside it if they don't exist.
DATABASE_URL="./db/ncert_tutor.db"

# --- JWT (JSON Web Token) Configuration for Authentication ---
# IMPORTANT: Change this to a strong, random, and secret key in production!
JWT_SECRET="your_strong_random_jwt_secret_here"
# Expiration time for JWT tokens in hours.
JWT_EXP_HOURS="24"


# --- LLM (Large Language Model) Configuration ---
# This acts as a marker to switch between different LLM setups.
# Set to "local" to use a local/internal LLM endpoint.
# Set to "cloud" to use external cloud-based LLM services (like OpenAI, Groq).
LLM_MODEL_TYPE="cloud" # Options: "local", "cloud"

# If LLM_MODEL_TYPE is "cloud", specify the preferred provider.
# This will determine which cloud LLM service is used.
LLM_PROVIDER_NAME="openai" # Options: "openai", "groq"

# API key for OpenAI's services (if LLM_PROVIDER_NAME="openai")
OPENAI_API_KEY="your_openai_api_key_here"
# API key for Groq's services (if LLM_PROVIDER_NAME="groq")
GROQ_API_KEY="your_groq_api_key_here"

# API key for the local/internal LLM endpoint (if LLM_MODEL_TYPE="local")
API_KEY="your_internal_llm_api_key_here"

# --- Web Search Fallback Configuration (Optional) ---
# Set to "true" to enable web search when RAG retrieval is insufficient.
# Set to "false" to disable web search entirely.
WEB_SEARCH_ENABLED="true" # Options: "true", "false"

# API key for Tavily (a web search API), used if WEB_SEARCH_ENABLED is "true".
TAVILY_API_KEY="your_tavily_api_key_here"
```

*   **Note on `DATABASE_URL`**: The default `DATABASE_URL="./db/ncert_tutor.db"` expects a `db/` subdirectory in your project root. You might need to create this directory manually (`mkdir db`) or adjust the path in your `.env` file if you prefer a different location for your SQLite database.

## 4. Run the FastAPI Application

Once all dependencies are installed and your `.env` file is configured, you can start the backend server:

```bash
 
```

*   `uvicorn main:app`: Tells Uvicorn to run the `app` instance found in `main.py`.
*   `--reload`: Automatically restarts the server whenever code changes are detected, which is useful during development.
*   `--port 8000`: Specifies that the server should run on port 8000.

## 5. Access the API

After the server starts successfully, you can access the API at:

*   **Interactive API Documentation (Swagger UI)**: `http://127.0.0.1:8000/docs`
    This interface allows you to view all available endpoints, their expected parameters, and test them directly from your browser.

*   **Health Check**: `http://127.0.0.1:8000/health`
    You can check if the service and its dependencies (like the LLM and database) are running correctly by visiting this endpoint.



### How to Provide `user_id` for Personalized Interactions

Since JWT authentication has been removed, the `user_id` for personalized interactions should now be provided as a **query parameter** in your API requests. For example:

*   `GET /profile?user_id=some_user_id`
*   `PUT /profile?user_id=some_user_id`
*   `POST /chat?user_id=some_user_id` (along with the request body)


---

### Code Syntax and Flow Confirmation

The codebase has been thoroughly analyzed:

*   **Imports and Structure**: All identified incorrect import paths have been corrected. The project's modular structure (e.g., separate files for BKT, style, interest engines, retriever, LLM config) promotes maintainability.
*   **Logical Flow**: The core logic is orchestrated through a `LangGraph` pipeline (`pipeline.py`), ensuring a clear, step-by-step process for handling student queries, retrieving information, applying personalization, and generating responses.
*   **Personalization**: The system effectively integrates Bayesian Knowledge Tracing (BKT) for mastery tracking, a style engine for adaptive communication, and an interest engine for understanding student engagement, all of which dynamically influence the LLM's responses.
*   **LLM Flexibility**: The `llm/llm_config.py` now includes a robust mechanism to switch between local and various cloud LLM providers via environment variables (`LLM_MODEL_TYPE`, `LLM_PROVIDER_NAME`), providing significant flexibility.

The code's structure and flow are well-defined and appear robust for implementing a personalized NCERT answering engine.