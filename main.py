"""
Prompt Studio - Main Application Entry Point

A lightweight, offline-first desktop GUI for managing a CSV library of prompt roles,
composing/running prompts against multiple LLM backends, auto-categorizing prompts,
and building runnable drag-and-drop prompt workflows.
"""
import sys
import os
import asyncio
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon

from prompt_studio.ui.main_window import MainWindow
from prompt_studio.models.database import DatabaseManager
from prompt_studio.utils.csv_import import CSVImporter


def setup_application():
    """Setup the QApplication with proper settings"""
    # Enable high DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Prompt Studio")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Prompt Studio")
    app.setOrganizationDomain("promptstudio.local")
    
    # Set application style (optional - can be overridden by settings)
    app.setStyle("Fusion")
    
    return app


def import_initial_data():
    """Import the initial CSV data if database is empty"""
    try:
        db_manager = DatabaseManager()
        db_manager.create_tables()
        
        # Check if we have any prompts
        with db_manager.get_session() as session:
            from sqlmodel import select
            from prompt_studio.models.database import Prompt
            
            existing_count = len(session.exec(select(Prompt)).all())
            
            if existing_count == 0:
                # Import the assets CSV file
                assets_file = project_root / "assets.csv"
                if assets_file.exists():
                    print(f"Importing initial prompts from {assets_file}...")
                    importer = CSVImporter(db_manager)
                    stats = importer.import_prompts(str(assets_file))
                    
                    print(f"Import completed: Created {stats['created']}, Errors: {stats['errors']}")
                    
                    if stats['errors'] > 0:
                        print("Some errors occurred during import, but the application will continue.")
                else:
                    print("Assets CSV file not found, starting with empty database.")
            else:
                print(f"Database already contains {existing_count} prompts.")
                
    except Exception as e:
        print(f"Error during initial data import: {e}")
        print("Application will continue with empty database.")


def main():
    """Main application function"""
    try:
        # Setup QApplication
        app = setup_application()
        
        # Import initial data
        import_initial_data()
        
        # Create and show main window
        main_window = MainWindow()
        main_window.show()
        
        # Handle application exit
        def handle_exit():
            print("Shutting down Prompt Studio...")
            app.quit()
        
        app.aboutToQuit.connect(handle_exit)
        
        # Start the event loop
        print("Starting Prompt Studio...")
        exit_code = app.exec()
        
        print("Prompt Studio closed.")
        return exit_code
        
    except Exception as e:
        print(f"Fatal error: {e}")
        
        # Try to show error dialog if possible
        try:
            if 'app' in locals():
                QMessageBox.critical(
                    None,
                    "Fatal Error",
                    f"A fatal error occurred:\n\n{str(e)}\n\nThe application will now exit."
                )
        except:
            pass
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
