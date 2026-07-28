# WhatsApp AI Assistant

A fast, highly scalable, and fully asynchronous WhatsApp AI assistant powered by Retrieval-Augmented Generation (RAG). This bot allows users to interact with a dynamic, constantly evolving knowledge base through both text and voice notes directly on WhatsApp.

## What It Does

This bot acts as an intelligent, conversational interface to your business data. Unlike rigid rule-based chatbots, it leverages Large Language Models (LLMs) combined with your custom documents to provide accurate, grounded, and context-aware answers. 

**Key Capabilities:**
- **Natural Conversations:** Users can ask questions naturally. The bot remembers the recent conversation history to provide contextual follow-up answers.
- **Voice Note Support:** Users can send WhatsApp voice notes instead of typing. The bot transcribes the audio using OpenAI's Whisper API and processes it as if it were a text message.
- **Zero-Latency Fast Paths:** Common intents (like greetings, "thank you", or asking for human support) are intercepted before hitting the AI, delivering instant, hardcoded responses.
- **Privacy by Design:** All user conversation memory automatically expires and is deleted after 4 hours to keep the database light and respect user privacy.

## How It Works

The system is built on an event-driven architecture using FastAPI and the official Meta Cloud API.

1. **Message Reception:** A user sends a text or voice note via WhatsApp. Meta sends a secure webhook to the application.
2. **Speech-to-Text (Optional):** If the message is a voice note, the audio is downloaded and transcribed into text automatically.
3. **Knowledge Retrieval:** The bot takes the user's message, converts it into a mathematical vector, and performs a similarity search against a local, highly-optimized FAISS vector index. This instantly pulls up the exact paragraphs from your documents that contain the answer.
4. **Answer Generation:** The bot feeds the retrieved knowledge, the user's question, and the recent chat history to an LLM (like GPT-4o). The LLM is strictly instructed to generate an answer *only* based on the provided documents.
5. **Delivery:** The final, grounded answer is sent back to the user on WhatsApp.

## The Knowledge Base Engine

The assistant is powered by a completely dynamic Knowledge Base (KB) that can be updated on the fly without restarting the bot.

An admin can continuously upload new documents (PDFs, Word documents, PowerPoint presentations, Excel spreadsheets, plain text, and even Images). When a document is ingested:
1. The text is extracted (using native parsers or automatic OCR for images and scanned PDFs).
2. The raw text is saved persistently in a PostgreSQL database.
3. The text is chunked into vectors and appended to the live search index instantly.

Because the master copies of all data are kept in the database, the search index can be completely wiped and rebuilt from scratch at any time via simple API endpoints.

### Admin Capabilities (API Endpoints)
The system exposes several secure endpoints (protected by `KB_API_SECRET`) that give the admin full control over the AI's memory and knowledge:

- **Add Files (`POST /kb/ingest`)**: Upload documents (PDF, Word, Excel, Images, etc.) to instantly teach the AI new information without downtime.
- **View Knowledge (`GET /kb/status`)**: List all documents currently stored in the bot's memory, including their IDs and timestamps.
- **Delete Specific File (`DELETE /kb/{id}`)**: Erase a specific document from the database using its ID.
- **Wipe All Knowledge (`DELETE /kb/all`)**: Completely delete all uploaded documents from the database and wipe the vector search index, resetting the bot's domain knowledge to absolute zero.
- **Rebuild Index (`POST /kb/rebuild`)**: Regenerate the FAISS vector index from the database (used after deleting a specific file to update the AI's search cache).
- **Clear User Data & Conversations (`DELETE /kb/messages`)**: Instantly wipe all user conversation histories and chat memories from the database.

## Running Locally

To run this WhatsApp Bot locally, follow the instructions below.

### 1. Prerequisites

- Python 3.9+
- PostgreSQL database
- Ngrok (for local webhook testing)
- Meta Developer Account

### 2. Meta WhatsApp Setup

1. Go to the [Meta for Developers](https://developers.facebook.com/) portal and log in.
2. Click **Create App** and select **Business** as the app type.
3. Once the app is created, scroll down to **Add products to your app** and set up **WhatsApp**.
4. In the left menu, navigate to **WhatsApp > API Setup**. Here you will find your temporary `ACCESS_TOKEN` and your test `PHONE_NUMBER_ID`.
5. Navigate to **App Settings > Basic** to find your `APP_ID` and `APP_SECRET`.
6. To receive messages, you must configure a Webhook. Go to **WhatsApp > Configuration** and set your callback URL (use ngrok if running locally, e.g., `https://your-ngrok-url.ngrok-free.app/webhook`). Enter a custom `VERIFY_TOKEN` (which you will also add to your `.env` file). Subscribe to the `messages` webhook field.

### 3. Environment Variables

Create a `.env` file in the root directory and populate it with the following placeholders:

```env
# Meta WhatsApp Credentials
ACCESS_TOKEN="your_meta_access_token"
APP_ID="your_meta_app_id"
APP_SECRET="your_meta_app_secret"
PHONE_NUMBER_ID="your_whatsapp_phone_number_id"
VERIFY_TOKEN="your_custom_verify_token"

# OpenAI API Key
OPENAI_API_KEY="your_openai_api_key"

# Database Configuration
DATABASE_URL="postgresql://user:password@localhost:5432/dbname"

# Bot Configuration
LLM_MODEL="gpt-4o-mini"
KB_API_SECRET="your_custom_admin_secret"
ENABLE_FILE_LOGGING=false
IP_ADDRESS="0.0.0.0"
PORT="4777"
```

### 4. Installation & Execution

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd WhatsApp_Bot
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the bot:**
   ```bash
   python bot.py
   ```
   The bot will start running on the specified `IP_ADDRESS` and `PORT` (default is 4777). If testing locally, ensure your Ngrok tunnel forwards to this port.
