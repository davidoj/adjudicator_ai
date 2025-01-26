from django import template
import re

register = template.Library()

@register.filter
def split_section(text, section_header):
    """Extract content between a section header and the next section"""
    if section_header == "For P1:":
        pattern = r'<p1_advice>(.*?)</p1_advice>'
    elif section_header == "For P2:":
        pattern = r'<p2_advice>(.*?)</p2_advice>'
    else:
        pattern = f"{section_header}(.*?)(?=\n\w+:|$)"
        
    match = re.search(pattern, text, re.DOTALL)
    if match:
        content = match.group(1).strip()
        # Extract items from list if present
        items = re.findall(r'<item>(.*?)</item>', content)
        if items:
            return items
        return content
    return ""

@register.filter
def is_list(value):
    """Check if value is a list"""
    return isinstance(value, (list, tuple)) 