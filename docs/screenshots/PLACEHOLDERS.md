# Screenshot Placeholders

This directory contains placeholder SVG files for documentation screenshots.

## To Replace Placeholders with Real Screenshots:

1. **Run the application locally:**
   ```bash
   # Terminal 1 - Backend
   cd backend
   source venv/bin/activate
   uvicorn main:app --reload

   # Terminal 2 - Frontend
   cd frontend
   npm run dev
   ```

2. **Capture screenshots according to the specifications in README.md**

3. **Replace the SVG files with PNG screenshots:**
   - `main-interface.png` - Replace main-interface.svg
   - `code-generation-flow.png` - Replace code-generation-flow.svg
   - `loading-states.png` - Replace loading-states.svg
   - `lm-studio-config.png` - Replace lm-studio-config.svg

4. **Update image references in README.md if changing file extensions**

## Current Files

- `main-interface.svg` - Placeholder for main application interface
- `code-generation-flow.svg` - Placeholder for workflow demonstration
- `loading-states.svg` - Placeholder for loading state UI
- `lm-studio-config.svg` - Placeholder for configuration panel

The SVG placeholders provide a visual representation of what the screenshots should contain, but should be replaced with actual application screenshots for production documentation.
