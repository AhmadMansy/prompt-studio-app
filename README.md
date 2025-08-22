# Prompt Studio

A lightweight, offline-first desktop GUI for managing a CSV library of prompt "roles", composing/running prompts against multiple LLM backends (OpenAI API, Ollama, LM Studio), auto-categorizing prompts, and building runnable drag-and-drop prompt workflows.
![alt text]([https://github.com/[username]/[reponame]/blob/[branch]/image.jpg](https://github.com/AhmadMansy/prompt-studio-app/blob/main/prompt_studio_screenshot.png)?raw=true)
## Features

- **Prompt Manager & Launcher**: Import from CSV, browse with categories/tags, search/filter, CRUD operations, favorites, and history
- **Smart Prompt Composer**: Dynamic placeholders with types and defaults, parameter presets, template preview
- **API Connector**: Pluggable connectors for OpenAI API, Ollama, LM Studio with streaming support
- **Auto-Categorization**: LLM-powered prompt analysis and category/tag suggestions
- **Workflow Builder**: Drag-and-drop node editor for building prompt pipelines (planned)
- **Cross-platform**: Works on macOS and Windows

## Installation

1. **Prerequisites**: Python 3.11 or higher

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**:
   ```bash
   python main.py
   ```

## Initial Setup

On first launch, the application will automatically import the sample prompts from `assets.csv`. The database file `prompt_studio.db` will be created in the application directory.

### Sample Prompts Dataset

The included sample prompts are sourced from the **Awesome ChatGPT Prompts** dataset by [fka](https://huggingface.co/fka) on Hugging Face, available at: https://huggingface.co/datasets/fka/awesome-chatgpt-prompts

This dataset is licensed under [CC0-1.0](https://creativecommons.org/publicdomain/zero/1.0/) (Creative Commons Zero), making it freely available for any use.

## Usage

### Importing Prompts

1. Go to **File → Import CSV...**
2. Select your CSV file with the following expected columns:
   - `name` (required): The prompt name/title
   - `content` or `prompt` (required): The actual prompt text
   - `category` (optional): Category for organization
   - `tags` (optional): Comma-separated tags
   - `description` (optional): Prompt description
   - `placeholders_schema` (optional): JSON schema for dynamic placeholders

### Using Prompts

1. **Select a prompt** from the center list
2. **Fill in parameters** in the right panel (if the prompt has placeholders)
3. **Choose a backend** from the toolbar (OpenAI, Ollama, LM Studio)
4. **Select a model** for the chosen backend
5. **Click Run** or press `Ctrl+Enter`

### Keyboard Shortcuts

- `Ctrl+K`: Quick open (fuzzy search prompts)
- `Ctrl+Enter`: Run current prompt
- `Escape`: Stop execution
- `F5`: Refresh prompt list
- `Ctrl+N`: New prompt (planned)

### Placeholders and Templates

Prompts support Jinja2 templating with dynamic placeholders:

```jinja2
Act as a {{ expertise }} and help me with {{ task }}.
Constraints: {{ constraints or "none" }}
```

Supported placeholder types:
- `str`: Short text input
- `text`: Long text (textarea)
- `int`: Integer input
- `float`: Float input
- `bool`: Boolean checkbox
- `choice`: Single choice dropdown
- `multichoice`: Multiple choice checkboxes

## Configuration

### API Keys

API keys are stored securely using the system keyring:

- **OpenAI**: Stored under service "PromptStudio", account "openai_api_key"
- **Other backends**: Local servers (Ollama, LM Studio) don't require API keys

You can set API keys programmatically:
```python
import keyring
keyring.set_password("PromptStudio", "openai_api_key", "your_api_key_here")
```

### Backend Configuration

- **OpenAI API**: Default endpoint is `https://api.openai.com/v1`
- **Ollama**: Default endpoint is `http://localhost:11434`
- **LM Studio**: Default endpoint is `http://localhost:1234/v1`

Settings can be modified through the Settings dialog (planned) or directly in the database.

## Development

### Project Structure

```
prompt_studio/
├── models/          # Database models and ORM
├── ui/              # PySide6 user interface components
├── backends/        # LLM backend connectors
├── utils/           # Utilities (CSV import, templating)
└── __init__.py

main.py              # Application entry point
requirements.txt     # Python dependencies
assets.csv          # Sample prompts data
```

### Adding New Backends

To add a new LLM backend:

1. Implement the `LLMBackend` protocol in `backends/llm_backends.py`
2. Add your backend to the `BackendManager`
3. The UI will automatically detect and include it

### Building for Distribution

Use PyInstaller to create standalone executables:

```bash
# For current platform
pyinstaller --windowed --onefile main.py

# For macOS app bundle
pyinstaller --windowed --onefile --name "Prompt Studio" main.py
```

## TODO / Planned Features

- [ ] Settings dialog with API key management
- [ ] Quick open fuzzy search dialog
- [ ] Export functionality (JSON, CSV)
- [ ] Workflow builder with drag-and-drop nodes
- [ ] Auto-categorization using LLMs
- [ ] History search and filtering
- [ ] Dark/light theme toggle
- [ ] Plugin system for custom backends
- [ ] Prompt templates marketplace
- [ ] Batch processing capabilities

## License

This project is open source. See LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
