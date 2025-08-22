"""
Templating system for Prompt Studio using Jinja2
"""
import re
import json
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
import jinja2
from jinja2.sandbox import SandboxedEnvironment


class TemplateEngine:
    """Jinja2-based template engine for prompt rendering"""
    
    def __init__(self):
        self.env = SandboxedEnvironment(
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True
        )
        
        # Add custom filters
        self.env.filters['default'] = self._default_filter
        
    def _default_filter(self, value, default=""):
        """Custom default filter that handles None and empty strings"""
        if value is None or value == "":
            return default
        return value
    
    def render_template(self, template_str: str, context: Dict[str, Any]) -> str:
        """Render a template with given context"""
        try:
            # Add metadata to context
            enhanced_context = self._enhance_context(context)
            
            template = self.env.from_string(template_str)
            return template.render(**enhanced_context)
        except Exception as e:
            return f"Template Error: {str(e)}"
    
    def _enhance_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Add metadata and utility variables to context"""
        enhanced = context.copy()
        
        # Add metadata
        enhanced.update({
            'now': datetime.now(),
            'user': 'User',  # Could be customized in settings
            'app': 'Prompt Studio'
        })
        
        return enhanced
    
    def extract_placeholders(self, template_str: str) -> List[str]:
        """Extract all placeholder variables from a template"""
        try:
            template = self.env.from_string(template_str)
            undeclared_vars = jinja2.meta.find_undeclared_variables(template.environment.parse(template_str))
            
            # Filter out built-in variables
            builtins = {'now', 'user', 'app', 'range', 'dict', 'list'}
            placeholders = [var for var in undeclared_vars if var not in builtins]
            
            return sorted(list(set(placeholders)))
        except Exception:
            # Fallback to regex if Jinja2 parsing fails
            return self._extract_placeholders_regex(template_str)
    
    def _extract_placeholders_regex(self, template_str: str) -> List[str]:
        """Fallback regex-based placeholder extraction"""
        # Find {{ variable }} patterns
        pattern = r'\{\{\s*(\w+)(?:\s*\|\s*\w+)?\s*\}\}'
        matches = re.findall(pattern, template_str)
        
        # Filter out common Jinja2 built-ins
        builtins = {'now', 'user', 'app', 'range', 'dict', 'list'}
        placeholders = [match for match in matches if match not in builtins]
        
        return sorted(list(set(placeholders)))


class PlaceholderSchema:
    """Manages placeholder schemas for prompts"""
    
    SUPPORTED_TYPES = [
        "str",      # Short string input
        "text",     # Long text input (textarea)
        "int",      # Integer input
        "float",    # Float input
        "bool",     # Boolean checkbox
        "choice",   # Single choice dropdown
        "multichoice"  # Multiple choice checkboxes
    ]
    
    @staticmethod
    def create_schema_from_placeholders(placeholders: List[str]) -> List[Dict[str, Any]]:
        """Create a basic schema from placeholder names"""
        schema = []
        for placeholder in placeholders:
            schema.append({
                "name": placeholder,
                "type": "str",
                "required": True,
                "default": "",
                "description": f"Value for {placeholder}"
            })
        return schema
    
    @staticmethod
    def validate_schema(schema: List[Dict[str, Any]]) -> List[str]:
        """Validate a placeholder schema and return list of errors"""
        errors = []
        
        if not isinstance(schema, list):
            errors.append("Schema must be a list")
            return errors
        
        seen_names = set()
        
        for i, field in enumerate(schema):
            if not isinstance(field, dict):
                errors.append(f"Field {i} must be a dictionary")
                continue
                
            # Check required fields
            if "name" not in field:
                errors.append(f"Field {i} missing required 'name' field")
                continue
                
            name = field["name"]
            
            # Check for duplicate names
            if name in seen_names:
                errors.append(f"Duplicate field name: {name}")
            seen_names.add(name)
            
            # Validate name format
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
                errors.append(f"Invalid field name '{name}': must be a valid identifier")
            
            # Check type
            field_type = field.get("type", "str")
            if field_type not in PlaceholderSchema.SUPPORTED_TYPES:
                errors.append(f"Unsupported type '{field_type}' for field '{name}'")
            
            # Validate choice options
            if field_type in ["choice", "multichoice"]:
                options = field.get("options", [])
                if not isinstance(options, list) or not options:
                    errors.append(f"Field '{name}' with type '{field_type}' must have non-empty 'options' list")
        
        return errors
    
    @staticmethod
    def merge_schema_with_placeholders(
        existing_schema: List[Dict[str, Any]], 
        placeholders: List[str]
    ) -> List[Dict[str, Any]]:
        """Merge existing schema with new placeholders found in template"""
        # Create mapping of existing schema fields
        existing_fields = {field["name"]: field for field in existing_schema}
        
        merged_schema = []
        
        # Add existing fields that are still in placeholders
        for placeholder in placeholders:
            if placeholder in existing_fields:
                merged_schema.append(existing_fields[placeholder])
            else:
                # Add new placeholder with default config
                merged_schema.append({
                    "name": placeholder,
                    "type": "str",
                    "required": True,
                    "default": "",
                    "description": f"Value for {placeholder}"
                })
        
        return merged_schema


class PromptComposer:
    """Composes prompts by filling in placeholders"""
    
    def __init__(self):
        self.template_engine = TemplateEngine()
    
    def compose_prompt(
        self, 
        template: str, 
        values: Dict[str, Any],
        schema: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Compose a prompt by filling placeholders
        
        Returns:
            Dict with 'rendered', 'errors', and 'missing_required' keys
        """
        result = {
            'rendered': '',
            'errors': [],
            'missing_required': []
        }
        
        try:
            # Extract placeholders from template
            placeholders = self.template_engine.extract_placeholders(template)
            
            # If schema is provided, validate values against it
            if schema:
                validation_result = self._validate_values_against_schema(values, schema)
                result['errors'].extend(validation_result['errors'])
                result['missing_required'].extend(validation_result['missing_required'])
                
                # Don't render if there are missing required fields
                if result['missing_required']:
                    return result
            else:
                # Check for missing placeholders
                missing = [p for p in placeholders if p not in values or values[p] is None]
                if missing:
                    result['missing_required'] = missing
                    return result
            
            # Render the template
            result['rendered'] = self.template_engine.render_template(template, values)
            
        except Exception as e:
            result['errors'].append(str(e))
        
        return result
    
    def _validate_values_against_schema(
        self, 
        values: Dict[str, Any], 
        schema: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Validate provided values against schema"""
        errors = []
        missing_required = []
        
        for field in schema:
            name = field["name"]
            field_type = field.get("type", "str")
            required = field.get("required", False)
            
            value = values.get(name)
            
            # Check required fields
            if required and (value is None or value == ""):
                missing_required.append(name)
                continue
            
            # Skip validation for empty optional fields
            if value is None or value == "":
                continue
            
            # Type validation
            try:
                if field_type == "int":
                    int(value)
                elif field_type == "float":
                    float(value)
                elif field_type == "bool":
                    # Accept various boolean representations
                    if isinstance(value, str):
                        if value.lower() not in ["true", "false", "1", "0", "yes", "no"]:
                            errors.append(f"Invalid boolean value for '{name}': {value}")
                elif field_type == "choice":
                    options = field.get("options", [])
                    if value not in options:
                        errors.append(f"Invalid choice for '{name}': {value}. Options: {options}")
                elif field_type == "multichoice":
                    options = field.get("options", [])
                    if isinstance(value, list):
                        invalid_choices = [v for v in value if v not in options]
                        if invalid_choices:
                            errors.append(f"Invalid choices for '{name}': {invalid_choices}. Options: {options}")
                    else:
                        errors.append(f"Multichoice field '{name}' must be a list")
            except (ValueError, TypeError) as e:
                errors.append(f"Type validation error for '{name}': {str(e)}")
        
        return {
            'errors': errors,
            'missing_required': missing_required
        }
    
    def get_default_values(self, schema: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get default values from schema"""
        defaults = {}
        
        for field in schema:
            name = field["name"]
            default = field.get("default")
            
            if default is not None:
                defaults[name] = default
            else:
                # Provide type-appropriate defaults
                field_type = field.get("type", "str")
                if field_type == "int":
                    defaults[name] = 0
                elif field_type == "float":
                    defaults[name] = 0.0
                elif field_type == "bool":
                    defaults[name] = False
                elif field_type in ["choice", "multichoice"]:
                    options = field.get("options", [])
                    if options:
                        defaults[name] = options[0] if field_type == "choice" else [options[0]]
                    else:
                        defaults[name] = "" if field_type == "choice" else []
                else:
                    defaults[name] = ""
        
        return defaults


# Global instances
template_engine = TemplateEngine()
prompt_composer = PromptComposer()
