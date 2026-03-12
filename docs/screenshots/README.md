# Screenshots

This directory contains screenshots for the Local-Review-Critic application documentation.

## Required Screenshots

### 1. main-interface.png
**Description:** The main split-pane interface showing:
- Left pane: Chat interface with LM Studio configuration header
- Right pane: Code viewer with syntax highlighting
- Application header with "Local Review Critic" title

**How to capture:**
1. Run the application with `npm run dev` (frontend) and `uvicorn main:app --reload` (backend)
2. Navigate to `http://localhost:5173`
3. Take a full window screenshot

### 2. code-generation-flow.png
**Description:** Example of the multi-agent workflow in action showing:
- User prompt in chat
- Generator agent response
- Critic agent review comments
- Generated code in the right pane with syntax highlighting

**How to capture:**
1. Enter a sample prompt like "Create a Python function to calculate fibonacci numbers"
2. Wait for the pipeline to complete
3. Take a screenshot showing the full conversation and generated code

### 3. loading-states.png
**Description:** The application during the code generation pipeline showing:
- Phase indicators (🔄 Generating code... / 🔍 Reviewing code... / ✨ Applying feedback...)
- Active chat conversation
- Loading state in the right pane

**How to capture:**
1. Enter a prompt and immediately take a screenshot during processing
2. Capture the loading indicator at the top of the right pane

### 4. lm-studio-config.png
**Description:** The LM Studio configuration panel showing:
- Connection status indicator (● Connected / ● Disconnected)
- LM Studio URL input field
- Model selection dropdown
- Test connection button

**How to capture:**
1. Focus on the top configuration bar
2. Show both connected and disconnected states if possible

## Image Specifications

- **Format:** PNG (preferred) or JPEG
- **Resolution:** At least 1920x1080 for full screenshots, or appropriately sized for component screenshots
- **Quality:** High quality, clear text rendering
- **Dark mode:** Ensure the dark theme (slate/blue colors) is clearly visible

## Notes

- Screenshots should show realistic usage examples
- Ensure no sensitive information (API keys, personal data) is visible
- Use clear, professional example code (e.g., fibonacci, sorting algorithms)
- Keep browser UI minimal or cropped out when appropriate
