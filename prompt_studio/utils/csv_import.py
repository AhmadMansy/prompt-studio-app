"""
CSV Import functionality for Prompt Studio

Note: Sample prompts are sourced from the Awesome ChatGPT Prompts dataset
by fka on Hugging Face (CC0-1.0 license):
https://huggingface.co/datasets/fka/awesome-chatgpt-prompts
"""
import csv
import json
from typing import List, Dict, Optional
from datetime import datetime
from sqlmodel import Session, select

from ..models.database import Prompt, Tag, PromptTagLink, DatabaseManager


class CSVImporter:
    """Handles importing prompts from CSV files"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        
    def parse_csv(self, file_path: str) -> List[Dict]:
        """Parse CSV file and return list of prompt dictionaries"""
        prompts = []
        
        with open(file_path, 'r', encoding='utf-8') as file:
            # Use csv.Sniffer to detect delimiter
            sample = file.read(1024)
            file.seek(0)
            sniffer = csv.Sniffer()
            delimiter = sniffer.sniff(sample).delimiter
            
            reader = csv.DictReader(file, delimiter=delimiter)
            
            for row in reader:
                # Map CSV columns to our expected format
                prompt_data = self._map_csv_row(row)
                if prompt_data:
                    prompts.append(prompt_data)
                    
        return prompts
    
    def _map_csv_row(self, row: Dict[str, str]) -> Optional[Dict]:
        """Map CSV row to prompt dictionary with flexible column mapping"""
        # Try to find required columns with flexible naming
        name = None
        content = None
        
        # Look for name column
        for key in row.keys():
            if key.lower() in ['name', 'title', 'act', 'role']:
                name = row[key].strip()
                break
                
        # Look for content column
        for key in row.keys():
            if key.lower() in ['content', 'prompt', 'description', 'text']:
                content = row[key].strip()
                break
                
        if not name or not content:
            return None
            
        # Extract other fields with flexible mapping
        category = None
        tags_str = ""
        description = None
        placeholders_schema = None
        
        for key, value in row.items():
            key_lower = key.lower()
            if key_lower == 'category':
                category = value.strip() if value else None
            elif key_lower in ['tags', 'tag']:
                tags_str = value.strip() if value else ""
            elif key_lower in ['description', 'desc'] and key.lower() != 'content':
                description = value.strip() if value else None
            elif key_lower in ['placeholders_schema', 'schema', 'placeholders']:
                if value and value.strip():
                    try:
                        # Try to parse JSON schema
                        placeholders_schema = json.loads(value.strip())
                    except json.JSONDecodeError:
                        # If not valid JSON, ignore
                        pass
        
        # Parse tags
        tags = []
        if tags_str:
            tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            
        return {
            'name': name,
            'content': content,
            'category': category,
            'tags': tags,
            'description': description,
            'placeholders_schema': placeholders_schema
        }
    
    def import_prompts(self, file_path: str, update_existing: bool = False) -> Dict[str, int]:
        """Import prompts from CSV file
        
        Args:
            file_path: Path to CSV file
            update_existing: Whether to update existing prompts or skip them
            
        Returns:
            Dictionary with counts of created, updated, and skipped prompts
        """
        stats = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
        
        try:
            prompt_data_list = self.parse_csv(file_path)
            
            with self.db_manager.get_session() as session:
                for prompt_data in prompt_data_list:
                    try:
                        result = self._import_single_prompt(session, prompt_data, update_existing)
                        stats[result] += 1
                    except Exception as e:
                        print(f"Error importing prompt {prompt_data.get('name', 'Unknown')}: {e}")
                        stats['errors'] += 1
                        
                session.commit()
                        
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            stats['errors'] += 1
            
        return stats
    
    def _import_single_prompt(self, session: Session, prompt_data: Dict, update_existing: bool = False) -> str:
        """Import a single prompt into the database"""
        # Check if prompt already exists
        existing_prompt = session.exec(
            select(Prompt).where(Prompt.name == prompt_data['name'])
        ).first()
        
        if existing_prompt:
            if update_existing:
                # Update existing prompt
                existing_prompt.content = prompt_data['content']
                existing_prompt.description = prompt_data.get('description')
                existing_prompt.category = prompt_data.get('category')
                existing_prompt.updated_at = datetime.utcnow()
                
                if prompt_data.get('placeholders_schema'):
                    existing_prompt.set_placeholders_schema(prompt_data['placeholders_schema'])
                
                # Update tags
                self._update_prompt_tags(session, existing_prompt, prompt_data.get('tags', []))
                
                return 'updated'
            else:
                return 'skipped'
        else:
            # Create new prompt
            new_prompt = Prompt(
                name=prompt_data['name'],
                content=prompt_data['content'],
                description=prompt_data.get('description'),
                category=prompt_data.get('category')
            )
            
            if prompt_data.get('placeholders_schema'):
                new_prompt.set_placeholders_schema(prompt_data['placeholders_schema'])
                
            session.add(new_prompt)
            session.flush()  # Flush to get the ID
            
            # Add tags
            self._update_prompt_tags(session, new_prompt, prompt_data.get('tags', []))
            
            return 'created'
    
    def _update_prompt_tags(self, session: Session, prompt: Prompt, tag_names: List[str]):
        """Update tags for a prompt"""
        if not tag_names:
            return
            
        # Remove existing tags
        session.exec(
            select(PromptTagLink).where(PromptTagLink.prompt_id == prompt.id)
        ).all()
        for link in session.exec(select(PromptTagLink).where(PromptTagLink.prompt_id == prompt.id)):
            session.delete(link)
        
        # Add new tags
        for tag_name in tag_names:
            tag_name = tag_name.strip()
            if not tag_name:
                continue
                
            # Find or create tag
            existing_tag = session.exec(
                select(Tag).where(Tag.name == tag_name)
            ).first()
            
            if not existing_tag:
                existing_tag = Tag(name=tag_name)
                session.add(existing_tag)
                session.flush()  # Flush to get the ID
            
            # Create link
            link = PromptTagLink(prompt_id=prompt.id, tag_id=existing_tag.id)
            session.add(link)
    
    def preview_import(self, file_path: str, max_rows: int = 10) -> Dict:
        """Preview the first few rows of CSV import
        
        Args:
            file_path: Path to CSV file
            max_rows: Maximum number of rows to preview
            
        Returns:
            Dictionary with preview data and column mapping info
        """
        try:
            prompt_data_list = self.parse_csv(file_path)
            
            preview_data = {
                'total_rows': len(prompt_data_list),
                'preview_rows': prompt_data_list[:max_rows],
                'columns_found': [],
                'valid_prompts': 0
            }
            
            # Count valid prompts
            valid_count = 0
            for prompt_data in prompt_data_list:
                if prompt_data and prompt_data.get('name') and prompt_data.get('content'):
                    valid_count += 1
                    
            preview_data['valid_prompts'] = valid_count
            
            # Identify columns found
            if prompt_data_list:
                sample_prompt = prompt_data_list[0]
                columns = []
                if sample_prompt.get('name'):
                    columns.append('name')
                if sample_prompt.get('content'):
                    columns.append('content')
                if sample_prompt.get('category'):
                    columns.append('category')
                if sample_prompt.get('tags'):
                    columns.append('tags')
                if sample_prompt.get('description'):
                    columns.append('description')
                if sample_prompt.get('placeholders_schema'):
                    columns.append('placeholders_schema')
                    
                preview_data['columns_found'] = columns
                
            return preview_data
            
        except Exception as e:
            return {
                'error': str(e),
                'total_rows': 0,
                'preview_rows': [],
                'columns_found': [],
                'valid_prompts': 0
            }
