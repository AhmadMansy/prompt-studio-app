"""
Main application window for Prompt Studio
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QTabWidget,
    QComboBox, QProgressBar, QMenuBar, QMenu, QStatusBar,
    QToolBar, QCheckBox, QSpinBox, QDoubleSpinBox, QScrollArea,
    QGroupBox, QFormLayout, QMessageBox, QFileDialog, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QAction, QIcon, QFont, QKeySequence, QShortcut, QClipboard
import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime
import webbrowser
import urllib.parse

from sqlmodel import select
from ..models.database import DatabaseManager, Prompt, Tag, History
from ..utils.csv_import import CSVImporter
from ..utils.templating import template_engine, prompt_composer, PlaceholderSchema
from ..backends.llm_backends import backend_manager


class ModelLoadWorker(QThread):
    """Worker thread for loading models asynchronously"""
    models_loaded = Signal(list)
    error_occurred = Signal(str)
    
    def __init__(self, backend_name):
        super().__init__()
        self.backend_name = backend_name
    
    def run(self):
        """Load models from backend in thread"""
        try:
            backend = backend_manager.get_backend(self.backend_name)
            if backend:
                # Create an event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    models = loop.run_until_complete(backend.list_models())
                    self.models_loaded.emit(models)
                finally:
                    loop.close()
            else:
                self.error_occurred.emit(f"Backend {self.backend_name} not found")
        except Exception as e:
            self.error_occurred.emit(str(e))


class PromptListWidget(QListWidget):
    """Custom list widget for prompts with enhanced functionality"""
    
    prompt_selected = Signal(str)  # Emits prompt ID
    
    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        
    def add_prompt(self, prompt: Prompt):
        """Add a prompt to the list"""
        item = QListWidgetItem()
        item.setText(prompt.name)
        item.setData(Qt.UserRole, prompt.id)
        item.setToolTip(prompt.description or prompt.content[:100] + "...")
        
        # Add visual indicators
        if prompt.is_favorite:
            item.setText(f"⭐ {prompt.name}")
        
        self.addItem(item)
    
    def clear_prompts(self):
        """Clear all prompts from the list"""
        self.clear()
    
    def get_selected_prompt_ids(self) -> List[str]:
        """Get IDs of selected prompts"""
        selected_ids = []
        for item in self.selectedItems():
            prompt_id = item.data(Qt.UserRole)
            if prompt_id:
                selected_ids.append(prompt_id)
        return selected_ids


class PlaceholderFormWidget(QScrollArea):
    """Widget for filling in prompt placeholders"""
    
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Main container widget
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.setWidget(self.container)
        
        self.form_widgets = {}  # Maps field names to widgets
        
    def set_schema(self, schema: List[Dict[str, Any]]):
        """Set the placeholder schema and create form fields"""
        self.clear_form()
        
        for field in schema:
            self._create_field_widget(field)
    
    def clear_form(self):
        """Clear all form fields"""
        for widget in self.form_widgets.values():
            widget.deleteLater()
        self.form_widgets.clear()
        
        # Clear layout
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
    
    def _create_field_widget(self, field: Dict[str, Any]):
        """Create a widget for a single field"""
        name = field["name"]
        field_type = field.get("type", "str")
        required = field.get("required", False)
        default = field.get("default", "")
        description = field.get("description", "")
        
        # Create group box for the field
        group = QGroupBox()
        label_text = name
        if required:
            label_text += " *"
        group.setTitle(label_text)
        
        form_layout = QFormLayout(group)
        
        # Create appropriate widget based on type
        if field_type == "text":
            widget = QTextEdit()
            widget.setPlainText(str(default))
            widget.setMaximumHeight(100)
        elif field_type == "int":
            widget = QSpinBox()
            widget.setMinimum(-999999)
            widget.setMaximum(999999)
            widget.setValue(int(default) if default else 0)
        elif field_type == "float":
            widget = QDoubleSpinBox()
            widget.setMinimum(-999999.99)
            widget.setMaximum(999999.99)
            widget.setValue(float(default) if default else 0.0)
        elif field_type == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(default))
        elif field_type == "choice":
            widget = QComboBox()
            options = field.get("options", [])
            widget.addItems(options)
            if default in options:
                widget.setCurrentText(str(default))
        elif field_type == "multichoice":
            # For multichoice, we'll use a simple text edit for now
            # In a more complex implementation, you'd use checkboxes
            widget = QTextEdit()
            widget.setMaximumHeight(60)
            options = field.get("options", [])
            widget.setPlaceholderText(f"Options: {', '.join(options)}")
            if isinstance(default, list):
                widget.setPlainText(", ".join(default))
        else:  # str type
            widget = QLineEdit()
            widget.setText(str(default))
        
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: gray; font-size: 10pt;")
            form_layout.addRow(desc_label)
        
        form_layout.addRow(widget)
        
        self.form_widgets[name] = widget
        self.layout.addWidget(group)
    
    def get_values(self) -> Dict[str, Any]:
        """Get current values from all form fields"""
        values = {}
        
        for name, widget in self.form_widgets.items():
            if isinstance(widget, QTextEdit):
                values[name] = widget.toPlainText()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text()
            elif isinstance(widget, QSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                values[name] = widget.value()
            elif isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                values[name] = widget.currentText()
        
        return values


class ConsoleWidget(QTabWidget):
    """Console widget for displaying LLM responses"""
    
    def __init__(self):
        super().__init__()
        self.setTabPosition(QTabWidget.South)
        
        # Output tab
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Monaco", 11))
        self.addTab(self.output_text, "Output")
        
        # Stats tab
        self.stats_text = QTextEdit()
        self.stats_text.setReadOnly(True)
        self.addTab(self.stats_text, "Stats")
        
        # Raw tab
        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.addTab(self.raw_text, "Raw")
    
    def clear_output(self):
        """Clear all console output"""
        self.output_text.clear()
        self.stats_text.clear()
        self.raw_text.clear()
    
    def append_output(self, text: str):
        """Append text to output tab"""
        self.output_text.append(text)
    
    def set_stats(self, stats: Dict[str, Any]):
        """Set statistics information"""
        stats_text = []
        for key, value in stats.items():
            stats_text.append(f"{key}: {value}")
        self.stats_text.setPlainText("\n".join(stats_text))
    
    def set_raw(self, raw_data: str):
        """Set raw response data"""
        self.raw_text.setPlainText(raw_data)


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.db_manager = DatabaseManager()
        self.csv_importer = CSVImporter(self.db_manager)
        
        self.current_prompt: Optional[Prompt] = None
        self.current_values = {}
        
        self.setup_ui()
        self.setup_menu_bar()
        self.setup_toolbar()
        self.setup_status_bar()
        self.setup_shortcuts()
        
        # Initialize database
        self.db_manager.create_tables()
        
        # Load prompts
        self.refresh_prompts()
        
        # Set window properties
        self.setWindowTitle("Prompt Studio")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        
        # Load models for the default backend
        QTimer.singleShot(100, self.update_models)  # Delay to ensure UI is ready
    
    def setup_ui(self):
        """Setup the main UI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main horizontal splitter
        main_splitter = QSplitter(Qt.Horizontal)
        central_layout = QHBoxLayout(central_widget)
        central_layout.addWidget(main_splitter)
        
        # Left sidebar
        self.setup_sidebar(main_splitter)
        
        # Center and right area
        center_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(center_splitter)
        
        # Center prompt list
        self.setup_center_area(center_splitter)
        
        # Right panel
        self.setup_right_panel(center_splitter)
        
        # Bottom drawer (console)
        main_vertical_splitter = QSplitter(Qt.Vertical)
        main_vertical_splitter.addWidget(main_splitter)
        
        self.console = ConsoleWidget()
        self.console.setMinimumHeight(200)
        self.console.setMaximumHeight(300)
        main_vertical_splitter.addWidget(self.console)
        
        # Replace the main layout
        central_layout.removeWidget(main_splitter)
        central_layout.addWidget(main_vertical_splitter)
        
        # Set splitter proportions
        main_splitter.setSizes([250, 800, 350])
        center_splitter.setSizes([400, 400])
        main_vertical_splitter.setSizes([600, 200])
    
    def setup_sidebar(self, parent_splitter):
        """Setup the left sidebar"""
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        
        # Search box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search prompts...")
        self.search_input.textChanged.connect(self.filter_prompts)
        sidebar_layout.addWidget(self.search_input)
        
        # Filters
        filters_group = QGroupBox("Filters")
        filters_layout = QVBoxLayout(filters_group)
        
        # Category filter
        self.category_combo = QComboBox()
        self.category_combo.addItem("All Categories")
        self.category_combo.currentTextChanged.connect(self.filter_prompts)
        filters_layout.addWidget(QLabel("Category:"))
        filters_layout.addWidget(self.category_combo)
        
        # Favorites checkbox
        self.favorites_checkbox = QCheckBox("Show only favorites")
        self.favorites_checkbox.stateChanged.connect(self.filter_prompts)
        filters_layout.addWidget(self.favorites_checkbox)
        
        sidebar_layout.addWidget(filters_group)
        
        # Tags cloud (placeholder)
        tags_group = QGroupBox("Tags")
        tags_layout = QVBoxLayout(tags_group)
        self.tags_list = QListWidget()
        self.tags_list.setMaximumHeight(150)
        tags_layout.addWidget(self.tags_list)
        sidebar_layout.addWidget(tags_group)
        
        sidebar_layout.addStretch()
        parent_splitter.addWidget(sidebar)
    
    def setup_center_area(self, parent_splitter):
        """Setup the center prompt list area"""
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        
        # Prompt list
        self.prompt_list = PromptListWidget()
        self.prompt_list.itemSelectionChanged.connect(self.on_prompt_selected)
        center_layout.addWidget(self.prompt_list)
        
        parent_splitter.addWidget(center_widget)
    
    def setup_right_panel(self, parent_splitter):
        """Setup the right panel"""
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # Prompt details
        details_group = QGroupBox("Prompt Details")
        details_layout = QVBoxLayout(details_group)
        
        self.prompt_name_label = QLabel("Select a prompt")
        self.prompt_name_label.setFont(QFont("Arial", 12, QFont.Bold))
        details_layout.addWidget(self.prompt_name_label)
        
        self.prompt_description_label = QLabel("")
        self.prompt_description_label.setWordWrap(True)
        details_layout.addWidget(self.prompt_description_label)
        
        # Editable template
        template_header = QHBoxLayout()
        template_header.addWidget(QLabel("Template:"))
        
        # Template action buttons
        self.edit_button = QPushButton("Edit")
        self.edit_button.setMaximumWidth(60)
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        self.edit_button.setEnabled(False)
        template_header.addWidget(self.edit_button)
        
        self.copy_template_button = QPushButton("Copy")
        self.copy_template_button.setMaximumWidth(60)
        self.copy_template_button.clicked.connect(self.copy_template)
        self.copy_template_button.setEnabled(False)
        template_header.addWidget(self.copy_template_button)
        
        template_header.addStretch()
        details_layout.addLayout(template_header)
        
        self.prompt_preview = QTextEdit()
        self.prompt_preview.setReadOnly(True)
        self.prompt_preview.setMaximumHeight(150)
        details_layout.addWidget(self.prompt_preview)
        
        # Save/Cancel buttons for edit mode (initially hidden)
        self.edit_controls = QHBoxLayout()
        self.save_edit_button = QPushButton("Save")
        self.save_edit_button.clicked.connect(self.save_edit)
        self.save_edit_button.setVisible(False)
        self.edit_controls.addWidget(self.save_edit_button)
        
        self.cancel_edit_button = QPushButton("Cancel")
        self.cancel_edit_button.clicked.connect(self.cancel_edit)
        self.cancel_edit_button.setVisible(False)
        self.edit_controls.addWidget(self.cancel_edit_button)
        
        self.edit_controls.addStretch()
        details_layout.addLayout(self.edit_controls)
        
        right_layout.addWidget(details_group)
        
        # Placeholder form
        placeholders_group = QGroupBox("Parameters")
        placeholders_layout = QVBoxLayout(placeholders_group)
        
        self.placeholder_form = PlaceholderFormWidget()
        placeholders_layout.addWidget(self.placeholder_form)
        
        right_layout.addWidget(placeholders_group)
        
        # Control buttons
        controls_layout = QHBoxLayout()
        
        # First row of buttons
        run_row = QHBoxLayout()
        
        self.run_button = QPushButton("Run")
        self.run_button.clicked.connect(self.run_prompt)
        self.run_button.setEnabled(False)
        run_row.addWidget(self.run_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_execution)
        self.stop_button.setEnabled(False)
        run_row.addWidget(self.stop_button)
        
        controls_layout.addLayout(run_row)
        right_layout.addLayout(controls_layout)
        
        # Second row of action buttons
        actions_layout = QHBoxLayout()
        
        self.copy_prompt_button = QPushButton("Copy Rendered")
        self.copy_prompt_button.clicked.connect(self.copy_rendered_prompt)
        self.copy_prompt_button.setEnabled(False)
        actions_layout.addWidget(self.copy_prompt_button)
        
        # Create dropdown menu for AI platforms
        from PySide6.QtWidgets import QMenu
        self.browser_button = QPushButton("Open in AI Platform")
        self.browser_button.setEnabled(False)
        
        # Create menu for different AI platforms
        self.browser_menu = QMenu(self)
        
        chatgpt_action = QAction("ChatGPT", self)
        chatgpt_action.triggered.connect(lambda: self.open_in_ai_platform("chatgpt"))
        self.browser_menu.addAction(chatgpt_action)
        
        gemini_action = QAction("Google Gemini", self)
        gemini_action.triggered.connect(lambda: self.open_in_ai_platform("gemini"))
        self.browser_menu.addAction(gemini_action)
        
        claude_action = QAction("Claude", self)
        claude_action.triggered.connect(lambda: self.open_in_ai_platform("claude"))
        self.browser_menu.addAction(claude_action)
        
        deepseek_action = QAction("DeepSeek", self)
        deepseek_action.triggered.connect(lambda: self.open_in_ai_platform("deepseek"))
        self.browser_menu.addAction(deepseek_action)
        
        self.browser_button.setMenu(self.browser_menu)
        actions_layout.addWidget(self.browser_button)
        
        right_layout.addLayout(actions_layout)
        
        # Third row - Copy output button
        output_actions_layout = QHBoxLayout()
        
        self.copy_output_button = QPushButton("Copy Output")
        self.copy_output_button.clicked.connect(self.copy_output)
        self.copy_output_button.setEnabled(False)
        output_actions_layout.addWidget(self.copy_output_button)
        
        output_actions_layout.addStretch()
        right_layout.addLayout(output_actions_layout)
        
        # Track edit mode
        self.edit_mode = False
        self.original_content = ""
        
        parent_splitter.addWidget(right_panel)
    
    def setup_menu_bar(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        import_action = QAction("Import CSV...", self)
        import_action.triggered.connect(self.import_csv)
        file_menu.addAction(import_action)
        
        export_action = QAction("Export Selected...", self)
        export_action.triggered.connect(self.export_prompts)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Edit menu
        edit_menu = menubar.addMenu("Edit")
        
        new_prompt_action = QAction("New Prompt", self)
        new_prompt_action.setShortcut("Ctrl+N")
        edit_menu.addAction(new_prompt_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_prompts)
        view_menu.addAction(refresh_action)
        
        # Tools menu
        tools_menu = menubar.addMenu("Tools")
        
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self.show_settings)
        tools_menu.addAction(settings_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About...", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        credits_action = QAction("Credits...", self)
        credits_action.triggered.connect(self.show_credits)
        help_menu.addAction(credits_action)
    
    def setup_toolbar(self):
        """Setup the toolbar"""
        toolbar = self.addToolBar("Main")
        
        # Backend selector
        toolbar.addWidget(QLabel("Backend:"))
        self.backend_combo = QComboBox()
        self.backend_combo.addItems(backend_manager.list_backends())
        toolbar.addWidget(self.backend_combo)
        
        toolbar.addSeparator()
        
        # Model selector
        toolbar.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        toolbar.addWidget(self.model_combo)
        
        # Update models when backend changes
        self.backend_combo.currentTextChanged.connect(self.update_models)
        
        toolbar.addSeparator()
        
        # Quick run button
        quick_run_action = QAction("Quick Run", self)
        quick_run_action.setShortcut("Ctrl+Return")
        toolbar.addAction(quick_run_action)
    
    def setup_status_bar(self):
        """Setup the status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)
        
        self.status_bar.showMessage("Ready")
    
    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # Quick open shortcut (Ctrl+K)
        quick_open_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        quick_open_shortcut.activated.connect(self.show_quick_open)
        
        # Run shortcut (Ctrl+Return)
        run_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        run_shortcut.activated.connect(self.run_prompt)
        
        # Stop shortcut (Escape)
        stop_shortcut = QShortcut(QKeySequence("Escape"), self)
        stop_shortcut.activated.connect(self.stop_execution)
    
    def refresh_prompts(self):
        """Refresh the prompt list from database"""
        self.prompt_list.clear_prompts()
        
        with self.db_manager.get_session() as session:
            prompts = session.exec(select(Prompt)).all()
            
            for prompt in prompts:
                self.prompt_list.add_prompt(prompt)
        
        self.status_bar.showMessage(f"Loaded {self.prompt_list.count()} prompts")
    
    def filter_prompts(self):
        """Filter prompts based on search and filter criteria"""
        search_text = self.search_input.text().lower()
        category_filter = self.category_combo.currentText()
        show_favorites_only = self.favorites_checkbox.isChecked()
        
        for i in range(self.prompt_list.count()):
            item = self.prompt_list.item(i)
            prompt_name = item.text().lower()
            
            # Apply filters
            show_item = True
            
            if search_text and search_text not in prompt_name:
                show_item = False
            
            # TODO: Add category and favorites filtering
            
            item.setHidden(not show_item)
    
    def on_prompt_selected(self):
        """Handle prompt selection"""
        selected_items = self.prompt_list.selectedItems()
        if not selected_items:
            self.current_prompt = None
            self.prompt_name_label.setText("Select a prompt")
            self.prompt_description_label.setText("")
            self.prompt_preview.clear()
            self.placeholder_form.clear_form()
            self.run_button.setEnabled(False)
            self._enable_prompt_buttons(False)
            return
        
        # Get the first selected item
        item = selected_items[0]
        prompt_id = item.data(Qt.UserRole)
        
        with self.db_manager.get_session() as session:
            prompt = session.get(Prompt, prompt_id)
            if prompt:
                self.current_prompt = prompt
                self.prompt_name_label.setText(prompt.name)
                self.prompt_description_label.setText(prompt.description or "No description")
                self.prompt_preview.setPlainText(prompt.content)
                
                # Setup placeholder form
                schema = prompt.get_placeholders_schema()
                if schema:
                    self.placeholder_form.set_schema(schema)
                    # Get default values
                    self.current_values = prompt_composer.get_default_values(schema)
                else:
                    # Auto-detect placeholders
                    placeholders = template_engine.extract_placeholders(prompt.content)
                    if placeholders:
                        auto_schema = PlaceholderSchema.create_schema_from_placeholders(placeholders)
                        self.placeholder_form.set_schema(auto_schema)
                        self.current_values = prompt_composer.get_default_values(auto_schema)
                    else:
                        self.placeholder_form.clear_form()
                        self.current_values = {}
                
                self._enable_prompt_buttons(True)
    
    def _enable_prompt_buttons(self, enabled: bool):
        """Enable/disable prompt-related buttons"""
        self.run_button.setEnabled(enabled)
        self.edit_button.setEnabled(enabled)
        self.copy_template_button.setEnabled(enabled)
        self.copy_prompt_button.setEnabled(enabled)
        self.browser_button.setEnabled(enabled)
        # Output button stays disabled until there's output
    
    def toggle_edit_mode(self):
        """Toggle between edit and read-only mode for prompt"""
        if not self.current_prompt:
            return
            
        if not self.edit_mode:
            # Enter edit mode
            self.edit_mode = True
            self.original_content = self.prompt_preview.toPlainText()
            self.prompt_preview.setReadOnly(False)
            self.edit_button.setText("Editing...")
            self.edit_button.setEnabled(False)
            
            # Show save/cancel buttons
            self.save_edit_button.setVisible(True)
            self.cancel_edit_button.setVisible(True)
        
    def save_edit(self):
        """Save the edited prompt"""
        if not self.current_prompt or not self.edit_mode:
            return
            
        new_content = self.prompt_preview.toPlainText()
        
        # Update in database
        with self.db_manager.get_session() as session:
            prompt = session.get(Prompt, self.current_prompt.id)
            if prompt:
                prompt.content = new_content
                prompt.updated_at = datetime.utcnow()
                session.commit()
                
                # Update current prompt object
                self.current_prompt.content = new_content
                
                # Re-analyze placeholders
                placeholders = template_engine.extract_placeholders(new_content)
                if placeholders:
                    auto_schema = PlaceholderSchema.create_schema_from_placeholders(placeholders)
                    self.placeholder_form.set_schema(auto_schema)
                    self.current_values = prompt_composer.get_default_values(auto_schema)
                else:
                    self.placeholder_form.clear_form()
                    self.current_values = {}
        
        # Exit edit mode
        self._exit_edit_mode()
        self.status_bar.showMessage("Prompt saved successfully", 2000)
    
    def cancel_edit(self):
        """Cancel editing and restore original content"""
        if not self.edit_mode:
            return
            
        # Restore original content
        self.prompt_preview.setPlainText(self.original_content)
        self._exit_edit_mode()
    
    def _exit_edit_mode(self):
        """Exit edit mode and restore read-only state"""
        self.edit_mode = False
        self.prompt_preview.setReadOnly(True)
        self.edit_button.setText("Edit")
        self.edit_button.setEnabled(True)
        
        # Hide save/cancel buttons
        self.save_edit_button.setVisible(False)
        self.cancel_edit_button.setVisible(False)
    
    def copy_template(self):
        """Copy the template to clipboard"""
        if not self.current_prompt:
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(self.prompt_preview.toPlainText())
        self.status_bar.showMessage("Template copied to clipboard", 2000)
    
    def copy_rendered_prompt(self):
        """Copy the rendered prompt to clipboard"""
        if not self.current_prompt:
            return
            
        # Get values from form and render
        values = self.placeholder_form.get_values()
        schema = self.current_prompt.get_placeholders_schema()
        
        result = prompt_composer.compose_prompt(
            self.current_prompt.content,
            values,
            schema
        )
        
        if result['errors'] or result['missing_required']:
            QMessageBox.warning(self, "Cannot Copy", "Please fill in all required parameters first")
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(result['rendered'])
        self.status_bar.showMessage("Rendered prompt copied to clipboard", 2000)
    
    def open_in_ai_platform(self, platform: str):
        """Open the rendered prompt in specified AI platform"""
        if not self.current_prompt:
            return
            
        # Get values from form and render
        values = self.placeholder_form.get_values()
        schema = self.current_prompt.get_placeholders_schema()
        
        result = prompt_composer.compose_prompt(
            self.current_prompt.content,
            values,
            schema
        )
        
        if result['errors'] or result['missing_required']:
            QMessageBox.warning(self, "Cannot Open", "Please fill in all required parameters first")
            return
            
        # URL encode the prompt
        encoded_prompt = urllib.parse.quote(result['rendered'])
        
        platform_names = {
            "chatgpt": "ChatGPT",
            "gemini": "Google Gemini", 
            "claude": "Claude",
            "deepseek": "DeepSeek"
        }
        
        platform_name = platform_names.get(platform, platform)
        
        # Different strategies for different platforms
        if platform == "chatgpt":
            # ChatGPT supports URL parameters
            url = f"https://chat.openai.com/?q={encoded_prompt}"
            try:
                webbrowser.open(url)
                self.status_bar.showMessage(f"Opening {platform_name} with prompt...", 2000)
            except Exception as e:
                QMessageBox.critical(self, "Browser Error", f"Could not open browser: {str(e)}")
                
        elif platform == "gemini":
            # Try Gemini with URL parameter, fallback to clipboard
            url = f"https://gemini.google.com/app?q={encoded_prompt}"
            try:
                webbrowser.open(url)
                self.status_bar.showMessage(f"Opening {platform_name} with prompt...", 2000)
            except Exception as e:
                self._fallback_clipboard_open("https://gemini.google.com/app", platform_name, result['rendered'])
                
        elif platform == "claude":
            # Claude - copy to clipboard and open
            clipboard = QApplication.clipboard()
            clipboard.setText(result['rendered'])
            try:
                webbrowser.open("https://claude.ai/chat")
                self._show_clipboard_message(platform_name)
            except Exception as e:
                QMessageBox.critical(self, "Browser Error", f"Could not open browser: {str(e)}")
                
        elif platform == "deepseek":
            # DeepSeek - copy to clipboard and open
            clipboard = QApplication.clipboard()
            clipboard.setText(result['rendered'])
            try:
                webbrowser.open("https://chat.deepseek.com/")
                self._show_clipboard_message(platform_name)
            except Exception as e:
                QMessageBox.critical(self, "Browser Error", f"Could not open browser: {str(e)}")
        else:
            QMessageBox.warning(self, "Unknown Platform", f"Platform '{platform}' is not supported")
    
    def _fallback_clipboard_open(self, url: str, platform_name: str, prompt_text: str):
        """Fallback method: copy to clipboard and open platform"""
        clipboard = QApplication.clipboard()
        clipboard.setText(prompt_text)
        try:
            webbrowser.open(url)
            self._show_clipboard_message(platform_name)
        except Exception as e:
            QMessageBox.critical(self, "Browser Error", f"Could not open browser: {str(e)}")
    
    def _show_clipboard_message(self, platform_name: str):
        """Show clipboard instruction message"""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Prompt Copied")
        msg.setText(f"Opening {platform_name} in your browser...")
        msg.setInformativeText("Your prompt has been copied to the clipboard. Paste it (Ctrl+V/Cmd+V) in the chat window.")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        
        # Auto-close after 4 seconds
        QTimer.singleShot(4000, msg.close)
        msg.show()
        
        self.status_bar.showMessage(f"Prompt copied and opening {platform_name}...", 3000)
    
    def copy_output(self):
        """Copy the console output to clipboard"""
        output_text = self.console.output_text.toPlainText()
        if not output_text.strip():
            QMessageBox.information(self, "No Output", "No output to copy")
            return
            
        clipboard = QApplication.clipboard()
        clipboard.setText(output_text)
        self.status_bar.showMessage("Output copied to clipboard", 2000)
    
    def run_prompt(self):
        """Run the current prompt"""
        if not self.current_prompt:
            QMessageBox.warning(self, "Warning", "Please select a prompt first")
            return
        
        # Get values from form
        self.current_values = self.placeholder_form.get_values()
        
        # Compose the prompt
        schema = self.current_prompt.get_placeholders_schema()
        result = prompt_composer.compose_prompt(
            self.current_prompt.content,
            self.current_values,
            schema
        )
        
        if result['errors'] or result['missing_required']:
            error_msg = "Cannot run prompt:\n"
            if result['missing_required']:
                error_msg += f"Missing required fields: {', '.join(result['missing_required'])}\n"
            if result['errors']:
                error_msg += f"Errors: {', '.join(result['errors'])}"
            QMessageBox.warning(self, "Validation Error", error_msg)
            return
        
        # Clear console and show rendered prompt
        self.console.clear_output()
        self.console.append_output("Running prompt...\n")
        self.console.append_output("=" * 50)
        self.console.append_output(result['rendered'])
        self.console.append_output("=" * 50)
        
        # TODO: Actually execute with selected backend
        self.console.append_output("\nThis would execute with the selected backend...")
        self.console.append_output("\nNote: LLM execution will be implemented in the next version.")
        
        self.run_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        # Enable copy output button since we now have output
        self.copy_output_button.setEnabled(True)
    
    def stop_execution(self):
        """Stop the current execution"""
        self.run_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.console.append_output("\n\nExecution stopped by user.")
    
    def update_models(self):
        """Update model list when backend changes"""
        backend_name = self.backend_combo.currentText()
        if not backend_name:
            return
            
        self.model_combo.clear()
        self.model_combo.addItem("Loading models...")
        self.model_combo.setEnabled(False)
        
        # Create and start the worker thread
        self.model_worker = ModelLoadWorker(backend_name)
        self.model_worker.models_loaded.connect(self.on_models_loaded)
        self.model_worker.error_occurred.connect(self.on_model_load_error)
        self.model_worker.start()
    
    def on_models_loaded(self, models: List[str]):
        """Handle successful model loading"""
        self.model_combo.clear()
        self.model_combo.setEnabled(True)
        
        if models:
            self.model_combo.addItems(models)
            self.status_bar.showMessage(f"Loaded {len(models)} models", 2000)
        else:
            self.model_combo.addItem("No models available")
            self.status_bar.showMessage("No models found", 2000)
    
    def on_model_load_error(self, error_msg: str):
        """Handle model loading errors"""
        self.model_combo.clear()
        self.model_combo.addItem("Failed to load models")
        self.model_combo.setEnabled(True)
        self.status_bar.showMessage(f"Model load error: {error_msg}", 5000)
    
    def import_csv(self):
        """Import prompts from CSV file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Import CSV File", 
            "", 
            "CSV Files (*.csv)"
        )
        
        if file_path:
            try:
                stats = self.csv_importer.import_prompts(file_path, update_existing=False)
                message = f"Import completed:\n"
                message += f"Created: {stats['created']}\n"
                message += f"Updated: {stats['updated']}\n"
                message += f"Skipped: {stats['skipped']}\n"
                message += f"Errors: {stats['errors']}"
                
                QMessageBox.information(self, "Import Results", message)
                self.refresh_prompts()
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import CSV: {str(e)}")
    
    def export_prompts(self):
        """Export selected prompts"""
        # TODO: Implement export functionality
        QMessageBox.information(self, "Export", "Export functionality not yet implemented")
    
    def show_settings(self):
        """Show settings dialog"""
        # TODO: Implement settings dialog
        QMessageBox.information(self, "Settings", "Settings dialog not yet implemented")
    
    def show_quick_open(self):
        """Show quick open dialog"""
        # TODO: Implement quick open functionality
        QMessageBox.information(self, "Quick Open", "Quick open functionality not yet implemented")
    
    def show_about(self):
        """Show About dialog"""
        about_text = """<h2>Prompt Studio</h2>
        <p><b>Version:</b> 1.0.0</p>
        <p><b>Description:</b> A lightweight, offline-first desktop GUI for managing prompt templates and composing/running prompts against multiple LLM backends.</p>
        
        <p><b>Features:</b></p>
        <ul>
        <li>Prompt Manager & Launcher with CSV import</li>
        <li>Smart Prompt Composer with dynamic placeholders</li>
        <li>Multi-backend API connector (OpenAI, Ollama, LM Studio)</li>
        <li>Cross-platform support (macOS, Windows)</li>
        </ul>
        
        <p><b>License:</b> MIT License</p>
        <p><b>Built with:</b> Python, PySide6, SQLModel</p>
        """
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("About Prompt Studio")
        msg.setText(about_text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
    
    def show_credits(self):
        """Show Credits dialog"""
        credits_text = """<h2>Credits and Attributions</h2>
        
        <h3>Sample Prompts Dataset</h3>
        <p>The included sample prompts are sourced from the <b>Awesome ChatGPT Prompts</b> dataset:</p>
        <p><b>Author:</b> <a href="https://huggingface.co/fka">fka</a><br>
        <b>Source:</b> <a href="https://huggingface.co/datasets/fka/awesome-chatgpt-prompts">Hugging Face Datasets</a><br>
        <b>License:</b> CC0-1.0 (Creative Commons Zero - Public Domain)</p>
        
        <h3>Open Source Dependencies</h3>
        <p>This application is built using various open source libraries:</p>
        <ul>
        <li><b>PySide6:</b> Qt for Python GUI framework</li>
        <li><b>SQLModel:</b> SQL database ORM by Sebastián Ramírez</li>
        <li><b>Jinja2:</b> Templating engine by the Pallets Team</li>
        <li><b>httpx:</b> HTTP client library</li>
        <li><b>keyring:</b> Secure credential storage</li>
        </ul>
        
        <p>For a complete list of dependencies and licenses, see the CREDITS.md file.</p>
        
        <p><b>License Compatibility:</b> MIT License (application code) + CC0-1.0 (sample data)<br>
        This combination ensures free use, modification, and distribution.</p>
        """
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Credits - Prompt Studio")
        msg.setText(credits_text)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()
    
    def closeEvent(self, event):
        """Handle application close"""
        event.accept()
