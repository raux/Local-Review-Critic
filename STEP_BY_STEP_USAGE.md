# Step-by-Step Usage Guide

This guide explains how to use the new button-controlled agent interaction feature.

## New Features

### 1. Button-Controlled Workflow

The agent interaction has been broken down into three separate steps, each controlled by a button click:

1. **Generate** - Creates initial code from your prompt
2. **Review Code** - Critic reviews the generated code
3. **Apply Changes** - Synthesizes final code incorporating feedback

### 2. Thinking Model Support

If you're using a reasoning/thinking model (like OpenAI's o1 models), the model's internal reasoning will be displayed in the chat UI with a purple "🤔 Thinking" label.

## How to Use

### Step 1: Submit Your Request

1. Enter your coding request in the text area
2. Click the "Send" button or press Enter
3. Wait for the Generator to create initial code

**What happens:**
- Your message appears in the chat
- Loading indicator shows "Generator is drafting..."
- Generated code appears in both the chat and the code viewer
- A "🔍 Review Code" button appears

### Step 2: Review the Code

1. Review the generated code in the right panel
2. Click the "🔍 Review Code" button when ready

**What happens:**
- Loading indicator shows "Critic is reviewing..."
- Critic's feedback appears in the chat
- An "✨ Apply Changes" button appears

### Step 3: Apply Improvements

1. Review the critic's feedback in the chat
2. Click the "✨ Apply Changes" button when ready

**What happens:**
- Loading indicator shows "Applying fixes..."
- Final improved code appears in the chat and code viewer
- A "Pipeline Complete" message appears with "Start New Request" button

### Step 4: Start a New Request

1. Click "Start New Request" to reset the interface
2. The input field is re-enabled for your next request

## API Endpoints

### New Endpoints

The following new endpoints have been added for step-by-step execution:

#### POST /generate
Generate initial code from user prompt.

**Request:**
```json
{
  "prompt": "Create a Python function to calculate fibonacci numbers",
  "lm_studio_url": "http://localhost:1234",  // Optional
  "model": "model-name"                       // Optional
}
```

**Response:**
```json
{
  "content": "def fibonacci(n):\n    ...",
  "reasoning": "First, I'll consider..."     // Optional, from thinking models
}
```

#### POST /critique
Critique the draft code.

**Request:**
```json
{
  "draft_code": "def fibonacci(n):\n    ...",
  "lm_studio_url": "http://localhost:1234",  // Optional
  "model": "model-name"                       // Optional
}
```

**Response:**
```json
{
  "content": "The code has the following issues...",
  "reasoning": "Let me analyze..."           // Optional, from thinking models
}
```

#### POST /synthesize
Synthesize final code incorporating critic feedback.

**Request:**
```json
{
  "prompt": "Create a Python function to calculate fibonacci numbers",
  "draft_code": "def fibonacci(n):\n    ...",
  "critic_comments": "The code has the following issues...",
  "lm_studio_url": "http://localhost:1234",  // Optional
  "model": "model-name"                       // Optional
}
```

**Response:**
```json
{
  "content": "def fibonacci(n):\n    # Improved version...",
  "reasoning": "Based on the feedback...",   // Optional, from thinking models
  "final_code": "def fibonacci(n):\n    # Improved version..."  // Code without markdown
}
```

### Existing Endpoint (Backward Compatible)

#### POST /chat
Run the complete pipeline in one request (original behavior).

**Request:**
```json
{
  "prompt": "Create a Python function to calculate fibonacci numbers",
  "lm_studio_url": "http://localhost:1234",  // Optional
  "model": "model-name"                       // Optional
}
```

**Response:**
```json
{
  "chat_history": [
    {"role": "generator", "content": "..."},
    {"role": "critic", "content": "..."},
    {"role": "generator", "content": "..."}
  ],
  "critic_comments": "The code has the following issues...",
  "final_code": "def fibonacci(n):\n    ..."
}
```

## Testing the Implementation

### Manual Testing Steps

1. **Start LM Studio**
   - Open LM Studio
   - Load a model (e.g., Llama 3, Mistral, etc.)
   - Start the local server (default: http://localhost:1234)

2. **Start the Backend**
   ```bash
   cd backend
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Start the Frontend**
   ```bash
   cd frontend
   npm run dev
   ```

4. **Test the Flow**
   - Open http://localhost:5173 in your browser
   - Enter a prompt like "Create a Python function to sort a list"
   - Click Send
   - Wait for generation to complete
   - Click "🔍 Review Code"
   - Wait for critique to complete
   - Click "✨ Apply Changes"
   - Wait for synthesis to complete
   - Verify the final code is displayed
   - Click "Start New Request"
   - Verify the interface resets

### Testing with cURL

You can also test the individual endpoints with cURL:

```bash
# Test generate endpoint
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a Python hello world function"}'

# Test critique endpoint
curl -X POST http://localhost:8000/critique \
  -H "Content-Type: application/json" \
  -d '{"draft_code": "def hello():\n    print(\"Hello, World!\")"}'

# Test synthesize endpoint
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a Python hello world function",
    "draft_code": "def hello():\n    print(\"Hello, World!\")",
    "critic_comments": "Add a docstring and parameter for name"
  }'
```

## Thinking Model Integration

If you're using a reasoning model that provides thinking/reasoning output (like OpenAI's o1 models):

1. The reasoning will be captured by the backend
2. Displayed in the chat UI with a "🤔 Thinking" label
3. Shown in purple to distinguish it from regular messages

This allows you to see the model's internal reasoning process, which can be helpful for understanding how it arrived at its conclusions.

## Benefits of Step-by-Step Control

1. **Review Before Proceeding** - Examine each stage's output before moving to the next
2. **Stop Early** - Skip critique or synthesis if the initial generation is sufficient
3. **Understand the Process** - See how each agent contributes to the final result
4. **Transparency** - View thinking model reasoning at each step
5. **User Control** - Proceed at your own pace through the pipeline

## Backward Compatibility

The original `/chat` endpoint still works for users who prefer the automatic pipeline execution. The frontend uses the new step-by-step endpoints by default for better user control.
